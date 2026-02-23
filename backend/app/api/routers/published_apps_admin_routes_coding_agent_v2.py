from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.agents import RunStatus
from app.db.postgres.models.published_apps import PublishedAppDraftDevSessionStatus, PublishedAppRevision
from app.db.postgres.session import get_db
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_queue_service import PublishedAppCodingQueueService
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor
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

logger = logging.getLogger(__name__)


class CodingAgentSubmitPromptRequest(BaseModel):
    input: str
    chat_session_id: Optional[UUID] = None
    model_id: Optional[UUID] = None
    client_message_id: Optional[str] = None


class CodingAgentRunResponse(BaseModel):
    run_id: str
    status: str
    execution_engine: Literal["opencode"]
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


class CodingAgentPromptSubmissionStartedResponse(BaseModel):
    submission_status: Literal["started"] = "started"
    run: CodingAgentRunResponse


class CodingAgentPromptSubmissionQueuedResponse(BaseModel):
    submission_status: Literal["queued"] = "queued"
    active_run_id: str
    queue_item: CodingAgentPromptQueueItemResponse


CodingAgentPromptSubmissionResponse = CodingAgentPromptSubmissionStartedResponse | CodingAgentPromptSubmissionQueuedResponse


class CodingAgentCheckpointResponse(BaseModel):
    checkpoint_id: str
    run_id: str
    app_id: str
    revision_id: Optional[str] = None
    created_at: datetime


class CodingAgentRestoreCheckpointRequest(BaseModel):
    run_id: Optional[UUID] = None


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


class CodingAgentActiveRunResponse(BaseModel):
    run_id: str
    status: str
    queued_prompt_count: int


class CodingAgentQueueDeleteResponse(BaseModel):
    status: str
    id: str


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


@router.post(
    "/{app_id}/coding-agent/v2/prompts",
    response_model=CodingAgentPromptSubmissionResponse,
)
async def submit_coding_agent_prompt(
    app_id: UUID,
    payload: CodingAgentSubmitPromptRequest,
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
    draft = await _ensure_current_draft_revision(db, app, actor_id)
    draft = await _refresh_draft_from_active_builder_sandbox(
        db=db,
        app=app,
        draft=draft,
        actor_id=actor_id,
    )

    user_prompt = (payload.input or "").strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="input is required")

    queue_service = PublishedAppCodingQueueService(db)
    result = await queue_service.submit_prompt(
        app=app,
        base_revision=draft,
        actor_id=actor_id,
        user_prompt=user_prompt,
        model_id=payload.model_id,
        chat_session_id=payload.chat_session_id,
        client_message_id=str(payload.client_message_id or "").strip() or None,
    )

    runtime = PublishedAppCodingAgentRuntimeService(db)
    if result.status == "started" and result.run is not None:
        await PublishedAppCodingRunMonitor(db).ensure_monitor(app_id=app.id, run_id=result.run.id)
        return CodingAgentPromptSubmissionStartedResponse(run=_run_to_response(runtime, result.run))

    if result.active_run is None or result.queue_item is None:
        raise HTTPException(status_code=500, detail="Queued prompt result is incomplete")

    return CodingAgentPromptSubmissionQueuedResponse(
        active_run_id=str(result.active_run.id),
        queue_item=CodingAgentPromptQueueItemResponse(**queue_service.serialize_queue_item(result.queue_item)),
    )


@router.get("/{app_id}/coding-agent/v2/runs/{run_id}", response_model=CodingAgentRunResponse)
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


@router.get("/{app_id}/coding-agent/v2/runs/{run_id}/stream")
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
    monitor = PublishedAppCodingRunMonitor(db)

    async def event_generator():
        yield ": " + (" " * 2048) + "\n\n"
        seq = 0
        async for payload in monitor.stream_events(app_id=app.id, run_id=run.id):
            seq += 1
            payload["seq"] = seq
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


@router.post("/{app_id}/coding-agent/v2/runs/{run_id}/cancel", response_model=CodingAgentRunResponse)
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

    queue_service = PublishedAppCodingQueueService(db)
    next_run = await queue_service.dispatch_next_for_terminal_run(terminal_run=run)
    if next_run is not None:
        asyncio.create_task(PublishedAppCodingRunMonitor.ensure_monitor_detached(app_id=app.id, run_id=next_run.id))

    return _run_to_response(service, run)


@router.get("/{app_id}/coding-agent/v2/chat-sessions", response_model=List[CodingAgentChatSessionResponse])
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
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}",
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
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/active-run",
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

    queue_service = PublishedAppCodingQueueService(db)
    run = await queue_service.get_active_run_for_chat_session(
        app_id=app.id,
        chat_session_id=session.id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="No active coding-agent run for this chat session")

    queued_count = await queue_service.count_queued_prompts(chat_session_id=session.id)
    status = run.status.value if hasattr(run.status, "value") else str(run.status)
    return CodingAgentActiveRunResponse(
        run_id=str(run.id),
        status=status,
        queued_prompt_count=queued_count,
    )


@router.get(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/queue",
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

    queue_service = PublishedAppCodingQueueService(db)
    items = await queue_service.list_queue_items(
        app_id=app.id,
        user_id=actor_id,
        chat_session_id=session.id,
    )
    return [CodingAgentPromptQueueItemResponse(**queue_service.serialize_queue_item(item)) for item in items]


@router.delete(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/queue/{queue_item_id}",
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

    queue_service = PublishedAppCodingQueueService(db)
    removed = await queue_service.remove_queue_item(
        app_id=app.id,
        user_id=actor_id,
        chat_session_id=session.id,
        queue_item_id=queue_item_id,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Queued prompt not found")
    return CodingAgentQueueDeleteResponse(status="removed", id=str(queue_item_id))


@router.get("/{app_id}/coding-agent/v2/checkpoints", response_model=List[CodingAgentCheckpointResponse])
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


@router.post(
    "/{app_id}/coding-agent/v2/checkpoints/{checkpoint_id}/restore",
    response_model=CodingAgentRestoreCheckpointResponse,
)
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
