import json
import logging
from datetime import datetime
import time
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.agents import RunStatus
from app.db.postgres.models.published_apps import PublishedAppDraftDevSessionStatus, PublishedAppRevision
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.db.postgres.session import get_db
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_capabilities import (
    build_published_app_coding_agent_capabilities,
)
from app.services.published_app_draft_dev_runtime import (
    PublishedAppDraftDevRuntimeDisabled,
    PublishedAppDraftDevRuntimeService,
)

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _create_draft_revision_snapshot,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _get_revision_for_app,
    _resolve_tenant_admin_context,
)
from .published_apps_admin_files import _filter_builder_snapshot_files
from .published_apps_admin_shared import PublishedAppRevisionResponse, _revision_to_response, router


class CodingAgentCreateRunRequest(BaseModel):
    input: str
    base_revision_id: Optional[UUID] = None
    messages: Optional[List[Dict[str, str]]] = None
    model_id: Optional[UUID] = None
    engine: Optional[Literal["native", "opencode"]] = None
    chat_session_id: Optional[UUID] = None


class CodingAgentResumeRunRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


class CodingAgentRestoreCheckpointRequest(BaseModel):
    run_id: Optional[UUID] = None


class CodingAgentRunResponse(BaseModel):
    run_id: str
    status: str
    execution_engine: Literal["native", "opencode"]
    chat_session_id: Optional[str] = None
    surface: Optional[str] = None
    published_app_id: Optional[str] = None
    base_revision_id: Optional[str] = None
    result_revision_id: Optional[str] = None
    checkpoint_revision_id: Optional[str] = None
    requested_model_id: Optional[str] = None
    resolved_model_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sandbox_id: Optional[str] = None
    sandbox_status: Optional[str] = None
    sandbox_started_at: Optional[datetime] = None


class CodingAgentCheckpointResponse(BaseModel):
    checkpoint_id: str
    run_id: str
    app_id: str
    revision_id: Optional[str] = None
    created_at: datetime


class CodingAgentRestoreCheckpointResponse(BaseModel):
    checkpoint_id: str
    revision: PublishedAppRevisionResponse
    run_id: Optional[str] = None


class CodingAgentChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class CodingAgentChatMessageResponse(BaseModel):
    id: str
    run_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class CodingAgentChatSessionDetailResponse(BaseModel):
    session: CodingAgentChatSessionResponse
    messages: List[CodingAgentChatMessageResponse] = Field(default_factory=list)


class CodingAgentCapabilityToolResponse(BaseModel):
    name: str
    slug: str
    function_name: str


class CodingAgentOpenCodePolicyResponse(BaseModel):
    tooling_mode: str
    repo_tool_allowlist_configured: bool
    workspace_permission_model: str
    summary: str


class CodingAgentCapabilitiesResponse(BaseModel):
    app_id: str
    default_engine: Literal["native", "opencode"]
    native_enabled: bool
    native_tool_count: int
    native_tools: List[CodingAgentCapabilityToolResponse] = Field(default_factory=list)
    opencode_policy: CodingAgentOpenCodePolicyResponse


logger = logging.getLogger(__name__)


def _run_to_response(service: PublishedAppCodingAgentRuntimeService, run) -> CodingAgentRunResponse:
    return CodingAgentRunResponse(**service.serialize_run(run))


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _refresh_draft_from_active_builder_sandbox(
    *,
    db: AsyncSession,
    app,
    draft: PublishedAppRevision,
    actor_id: UUID | None,
) -> PublishedAppRevision:
    if actor_id is None:
        return draft
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.get_session(app_id=app.id, user_id=actor_id)
    except PublishedAppDraftDevRuntimeDisabled:
        return draft
    if (
        session is None
        or not session.sandbox_id
        or session.status not in {PublishedAppDraftDevSessionStatus.running, PublishedAppDraftDevSessionStatus.starting}
    ):
        return draft

    try:
        snapshot_payload = await runtime_service.client.snapshot_files(sandbox_id=session.sandbox_id)
    except Exception as exc:
        logger.warning(
            "Skipping builder sandbox snapshot before coding run app_id=%s user_id=%s session_id=%s: %s",
            app.id,
            actor_id,
            session.id,
            exc,
        )
        return draft

    files_payload = snapshot_payload.get("files")
    if not isinstance(files_payload, dict):
        return draft
    normalized_files = _filter_builder_snapshot_files(files_payload)
    if not normalized_files:
        return draft

    refreshed = await _create_draft_revision_snapshot(
        db=db,
        app=app,
        current=draft,
        actor_id=actor_id,
        files=normalized_files,
        entry_file=draft.entry_file,
    )
    if session.revision_id != refreshed.id:
        session.revision_id = refreshed.id
    return refreshed


@router.post("/{app_id}/coding-agent/runs", response_model=CodingAgentRunResponse)
async def create_coding_agent_run(
    app_id: UUID,
    payload: CodingAgentCreateRunRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    create_run_api_started_at = time.monotonic()
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    draft = await _ensure_current_draft_revision(db, app, actor_id)

    if payload.base_revision_id and str(payload.base_revision_id) != str(draft.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(draft.id),
                "latest_updated_at": draft.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )
    draft = await _refresh_draft_from_active_builder_sandbox(
        db=db,
        app=app,
        draft=draft,
        actor_id=actor_id,
    )

    user_prompt = (payload.input or "").strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="input is required")

    service = PublishedAppCodingAgentRuntimeService(db)
    run_messages: list[dict[str, str]] = []
    for raw_message in payload.messages or []:
        if not isinstance(raw_message, dict):
            continue
        role = str(raw_message.get("role") or "").strip().lower()
        content = str(raw_message.get("content") or "").strip()
        if role not in {"user", "assistant", "system"}:
            continue
        if not content:
            continue
        run_messages.append({"role": role, "content": content})
    history_service = PublishedAppCodingChatHistoryService(db)
    chat_session_id: UUID | None = None
    if actor_id is not None:
        session = await history_service.resolve_or_create_session(
            app_id=app.id,
            user_id=actor_id,
            user_prompt=user_prompt,
            session_id=payload.chat_session_id,
        )
        chat_session_id = session.id
        run_messages = await history_service.build_run_messages(
            session_id=session.id,
            current_user_prompt=user_prompt,
        )

    run = await service.create_run(
        app=app,
        base_revision=draft,
        actor_id=actor_id,
        user_prompt=user_prompt,
        messages=run_messages or None,
        requested_model_id=payload.model_id,
        execution_engine=payload.engine,
        chat_session_id=chat_session_id,
    )
    create_run_api_ms = max(0, int((time.monotonic() - create_run_api_started_at) * 1000))
    run_input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
    raw_run_context = run_input_params.get("context")
    run_context = dict(raw_run_context) if isinstance(raw_run_context, dict) else {}
    timing_metrics = run_context.get("timing_metrics_ms")
    if not isinstance(timing_metrics, dict):
        timing_metrics = {}
        run_context["timing_metrics_ms"] = timing_metrics
    timing_metrics["create_run_api"] = create_run_api_ms
    run_input_params["context"] = run_context
    run.input_params = run_input_params
    logger.info(
        "CODING_AGENT_TIMING run_id=%s app_id=%s phase=create_run_api duration_ms=%s",
        run.id,
        app.id,
        create_run_api_ms,
    )
    if chat_session_id is not None and actor_id is not None:
        await history_service.persist_user_message(
            session_id=chat_session_id,
            run_id=run.id,
            content=user_prompt,
        )
    else:
        await db.commit()
    return _run_to_response(service, run)


@router.get("/{app_id}/coding-agent/chat-sessions", response_model=List[CodingAgentChatSessionResponse])
async def list_coding_agent_chat_sessions(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        return []

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    history_service = PublishedAppCodingChatHistoryService(db)
    sessions = await history_service.list_sessions(app_id=app.id, user_id=actor_id, limit=limit)
    return [CodingAgentChatSessionResponse(**history_service.serialize_session(session)) for session in sessions]


@router.get(
    "/{app_id}/coding-agent/chat-sessions/{session_id}",
    response_model=CodingAgentChatSessionDetailResponse,
)
async def get_coding_agent_chat_session(
    app_id: UUID,
    session_id: UUID,
    request: Request,
    limit: int = Query(default=200, ge=1, le=400),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat history")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    history_service = PublishedAppCodingChatHistoryService(db)
    session = await history_service.get_session_for_user(
        app_id=app.id,
        user_id=actor_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Coding-agent chat session not found")
    messages = await history_service.list_messages(session_id=session.id, limit=limit)
    return CodingAgentChatSessionDetailResponse(
        session=CodingAgentChatSessionResponse(**history_service.serialize_session(session)),
        messages=[CodingAgentChatMessageResponse(**history_service.serialize_message(item)) for item in messages],
    )


@router.get(
    "/{app_id}/coding-agent/capabilities",
    response_model=CodingAgentCapabilitiesResponse,
)
async def get_coding_agent_capabilities(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    payload = build_published_app_coding_agent_capabilities()
    payload["app_id"] = str(app.id)
    return CodingAgentCapabilitiesResponse(**payload)


@router.get("/{app_id}/coding-agent/runs", response_model=List[CodingAgentRunResponse])
async def list_coding_agent_runs(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    runs = await service.list_runs(app_id=app.id, limit=limit)
    return [_run_to_response(service, run) for run in runs]


@router.get("/{app_id}/coding-agent/runs/{run_id}", response_model=CodingAgentRunResponse)
async def get_coding_agent_run(
    app_id: UUID,
    run_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    run = await service.get_run_for_app(app_id=app.id, run_id=run_id)
    return _run_to_response(service, run)


@router.get("/{app_id}/coding-agent/runs/{run_id}/stream")
async def stream_coding_agent_run(
    app_id: UUID,
    run_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    run = await service.get_run_for_app(app_id=app.id, run_id=run_id)

    async def event_generator():
        yield ": " + (" " * 2048) + "\n\n"
        async for payload in service.stream_run_events(app=app, run=run):
            yield _sse(payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{app_id}/coding-agent/runs/{run_id}/resume", response_model=CodingAgentRunResponse)
async def resume_coding_agent_run(
    app_id: UUID,
    run_id: UUID,
    payload: CodingAgentResumeRunRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    run = await service.get_run_for_app(app_id=app.id, run_id=run_id)
    if run.status != RunStatus.paused:
        raise HTTPException(status_code=409, detail="Run is not paused")
    await service.executor.resume_run(run.id, payload.payload, background=False)
    await db.refresh(run)
    return _run_to_response(service, run)


@router.post("/{app_id}/coding-agent/runs/{run_id}/cancel", response_model=CodingAgentRunResponse)
async def cancel_coding_agent_run(
    app_id: UUID,
    run_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    run = await service.get_run_for_app(app_id=app.id, run_id=run_id)
    run = await service.cancel_run(run)
    return _run_to_response(service, run)


@router.get("/{app_id}/coding-agent/checkpoints", response_model=List[CodingAgentCheckpointResponse])
async def list_coding_agent_checkpoints(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    checkpoints = await service.list_checkpoints(app_id=app.id, limit=limit)
    return [CodingAgentCheckpointResponse(**item) for item in checkpoints]


@router.post("/{app_id}/coding-agent/checkpoints/{checkpoint_id}/restore", response_model=CodingAgentRestoreCheckpointResponse)
async def restore_coding_agent_checkpoint(
    app_id: UUID,
    checkpoint_id: UUID,
    payload: CodingAgentRestoreCheckpointRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None

    run = None
    service = PublishedAppCodingAgentRuntimeService(db)
    if payload.run_id is not None:
        run = await service.get_run_for_app(app_id=app.id, run_id=payload.run_id)

    # Fast validation for clearer 404 semantics before restore call.
    await _get_revision_for_app(db, app.id, checkpoint_id)
    restored = await service.restore_checkpoint(
        app=app,
        checkpoint_revision_id=checkpoint_id,
        actor_id=actor_id,
        run=run,
    )

    return CodingAgentRestoreCheckpointResponse(
        checkpoint_id=str(checkpoint_id),
        revision=_revision_to_response(restored),
        run_id=str(run.id) if run else None,
    )
