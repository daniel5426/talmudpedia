import asyncio
import json
import logging
from datetime import datetime, timezone
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
from app.db.postgres.engine import sessionmaker
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.db.postgres.session import get_db
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_orchestrator import PublishedAppCodingRunOrchestrator
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
    client_message_id: Optional[str] = None
    enqueue_if_active: bool = False


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


class CodingAgentActiveRunResponse(BaseModel):
    run_id: str
    status: str
    last_seq: int
    queued_prompt_count: int
    is_cancelling: bool


class CodingAgentPromptQueueItemResponse(BaseModel):
    id: str
    chat_session_id: str
    position: int
    status: str
    input: str
    client_message_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class CodingAgentQueueDeleteResponse(BaseModel):
    status: str
    id: str


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
    if normalized_files == dict(draft.files or {}):
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
    orchestrator = PublishedAppCodingRunOrchestrator(db)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    history_service = PublishedAppCodingChatHistoryService(db)
    draft_dev_session = None
    if actor_id is not None:
        try:
            draft_dev_session = await runtime_service.ensure_active_session(
                app=app,
                revision=draft,
                user_id=actor_id,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            draft_dev_session = None

    client_message_id = str(payload.client_message_id or "").strip() or None
    if draft_dev_session is not None and draft_dev_session.active_coding_run_id is not None:
        locked_run = None
        try:
            locked_run = await service.get_run_for_app(
                app_id=app.id,
                run_id=draft_dev_session.active_coding_run_id,
            )
        except HTTPException:
            draft_dev_session.active_coding_run_id = None
            draft_dev_session.active_coding_run_locked_at = None
            draft_dev_session.active_coding_run_client_message_id = None
        if locked_run is None:
            pass
        else:
            locked_status = locked_run.status.value if hasattr(locked_run.status, "value") else str(locked_run.status)
            if (
                client_message_id
                and draft_dev_session.active_coding_run_client_message_id
                and draft_dev_session.active_coding_run_client_message_id == client_message_id
            ):
                return _run_to_response(service, locked_run)
            if locked_status not in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
                RunStatus.paused.value,
            }:
                locked_chat_session_id = str(service.serialize_run(locked_run).get("chat_session_id") or "").strip() or None
                next_replay_seq = await orchestrator.get_next_replay_seq(run_id=locked_run.id)
                if payload.enqueue_if_active and actor_id is not None:
                    enqueue_chat_session_id: UUID | None = None
                    if payload.chat_session_id is not None:
                        enqueue_chat_session_id = payload.chat_session_id
                    elif locked_chat_session_id:
                        try:
                            enqueue_chat_session_id = UUID(locked_chat_session_id)
                        except Exception:
                            enqueue_chat_session_id = None
                    if enqueue_chat_session_id is None:
                        session = await history_service.resolve_or_create_session(
                            app_id=app.id,
                            user_id=actor_id,
                            user_prompt=user_prompt,
                            session_id=payload.chat_session_id,
                        )
                        enqueue_chat_session_id = session.id
                    await orchestrator.enqueue_prompt(
                        app_id=app.id,
                        user_id=actor_id,
                        chat_session_id=enqueue_chat_session_id,
                        payload={
                            "input": user_prompt,
                            "model_id": str(payload.model_id) if payload.model_id else None,
                            "engine": payload.engine,
                            "client_message_id": client_message_id,
                        },
                    )
                    await orchestrator.ensure_runner(app_id=app.id, run_id=locked_run.id)
                    return _run_to_response(service, locked_run)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CODING_AGENT_RUN_ACTIVE",
                        "message": "A coding-agent run is already active for this preview session.",
                        "active_run_id": str(locked_run.id),
                        "chat_session_id": locked_chat_session_id,
                        "next_replay_seq": next_replay_seq,
                    },
                )
            draft_dev_session.active_coding_run_id = None
            draft_dev_session.active_coding_run_locked_at = None
            draft_dev_session.active_coding_run_client_message_id = None
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
    if draft_dev_session is not None:
        draft_dev_session.active_coding_run_id = run.id
        draft_dev_session.active_coding_run_locked_at = datetime.now(timezone.utc)
        draft_dev_session.active_coding_run_client_message_id = client_message_id
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
    await orchestrator.ensure_runner(app_id=app.id, run_id=run.id)
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
    "/{app_id}/coding-agent/chat-sessions/{session_id}/active-run",
    response_model=CodingAgentActiveRunResponse,
)
async def get_coding_agent_chat_session_active_run(
    app_id: UUID,
    session_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent run state")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    history_service = PublishedAppCodingChatHistoryService(db)
    session = await history_service.get_session_for_user(
        app_id=app.id,
        user_id=actor_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Coding-agent chat session not found")

    orchestrator = PublishedAppCodingRunOrchestrator(db)
    run = await orchestrator.get_active_run_for_chat_session(
        app_id=app.id,
        chat_session_id=session.id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="No active coding-agent run for this chat session")
    next_replay_seq = await orchestrator.get_next_replay_seq(run_id=run.id)
    queued_count = await orchestrator.count_queued_prompts(chat_session_id=session.id)
    status = run.status.value if hasattr(run.status, "value") else str(run.status)
    return CodingAgentActiveRunResponse(
        run_id=str(run.id),
        status=status,
        last_seq=max(0, next_replay_seq - 1),
        queued_prompt_count=queued_count,
        is_cancelling=bool(getattr(run, "is_cancelling", False)),
    )


@router.get(
    "/{app_id}/coding-agent/chat-sessions/{session_id}/queue",
    response_model=List[CodingAgentPromptQueueItemResponse],
)
async def list_coding_agent_chat_session_queue(
    app_id: UUID,
    session_id: UUID,
    request: Request,
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
    session = await history_service.get_session_for_user(
        app_id=app.id,
        user_id=actor_id,
        session_id=session_id,
    )
    if session is None:
        return []
    orchestrator = PublishedAppCodingRunOrchestrator(db)
    items = await orchestrator.list_queue_items(
        app_id=app.id,
        user_id=actor_id,
        chat_session_id=session.id,
    )
    return [CodingAgentPromptQueueItemResponse(**orchestrator.serialize_queue_item(item)) for item in items]


@router.delete(
    "/{app_id}/coding-agent/chat-sessions/{session_id}/queue/{queue_item_id}",
    response_model=CodingAgentQueueDeleteResponse,
)
async def delete_coding_agent_chat_session_queue_item(
    app_id: UUID,
    session_id: UUID,
    queue_item_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent queue updates")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    history_service = PublishedAppCodingChatHistoryService(db)
    session = await history_service.get_session_for_user(
        app_id=app.id,
        user_id=actor_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Coding-agent chat session not found")
    orchestrator = PublishedAppCodingRunOrchestrator(db)
    removed = await orchestrator.remove_queue_item(
        app_id=app.id,
        user_id=actor_id,
        chat_session_id=session.id,
        queue_item_id=queue_item_id,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Queued prompt not found")
    return CodingAgentQueueDeleteResponse(status="removed", id=str(queue_item_id))


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
    from_seq: int = Query(default=1, ge=1),
    replay: bool = Query(default=True),
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    service = PublishedAppCodingAgentRuntimeService(db)
    run = await service.get_run_for_app(app_id=app.id, run_id=run_id)
    await PublishedAppCodingRunOrchestrator(db).purge_old_events(retention_hours=24)
    bind = db.get_bind()
    bind_dialect = getattr(bind, "dialect", None)
    bind_url = getattr(bind, "url", None)
    use_request_scoped_stream_db = (
        getattr(bind_dialect, "name", "") == "sqlite"
    )

    async def event_generator():
        if use_request_scoped_stream_db:
            orchestrator = PublishedAppCodingRunOrchestrator(db)
            yield ": " + (" " * 2048) + "\n\n"
            async for payload in orchestrator.stream_events(
                app_id=app.id,
                run_id=run.id,
                from_seq=from_seq,
                replay=replay,
            ):
                yield _sse(payload)
                await asyncio.sleep(0)
            return

        async with sessionmaker() as stream_db:
            orchestrator = PublishedAppCodingRunOrchestrator(stream_db)
            yield ": " + (" " * 2048) + "\n\n"
            async for payload in orchestrator.stream_events(
                app_id=app.id,
                run_id=run.id,
                from_seq=from_seq,
                replay=replay,
            ):
                yield _sse(payload)
                await asyncio.sleep(0)

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
