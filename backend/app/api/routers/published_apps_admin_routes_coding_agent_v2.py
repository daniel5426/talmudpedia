from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.schemas.context_window import ContextWindowResponse
from app.api.schemas.run_usage import RunUsageResponse
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedAppRevision
from app.db.postgres.session import get_db
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_pipeline_trace import pipeline_trace
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled
from app.services.context_window_service import ContextWindowService
from app.services.model_accounting import usage_payload_from_run

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _get_revision_for_app,
    _resolve_tenant_admin_context,
)
from .published_apps_admin_shared import PublishedAppRevisionResponse, _revision_to_response, router


class CodingAgentSubmitPromptRequest(BaseModel):
    input: str
    chat_session_id: Optional[UUID] = None
    model_id: Optional[str] = None
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
    requested_model_id: Optional[str] = None
    resolved_model_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sandbox_id: Optional[str] = None
    sandbox_status: Optional[str] = None
    sandbox_started_at: Optional[datetime] = None
    context_window: Optional[ContextWindowResponse] = None
    run_usage: Optional[RunUsageResponse] = None


class CodingAgentPromptSubmissionStartedResponse(BaseModel):
    submission_status: Literal["started"] = "started"
    run: CodingAgentRunResponse


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
    run_events: List["CodingAgentRunEventResponse"] = Field(default_factory=list)
    paging: "CodingAgentChatSessionPagingResponse"
    context_window: Optional[ContextWindowResponse] = None


class CodingAgentChatSessionPagingResponse(BaseModel):
    has_more: bool = False
    next_before_message_id: Optional[str] = None


class CodingAgentRunEventResponse(BaseModel):
    run_id: str
    event: Literal["tool.started", "tool.completed", "tool.failed"]
    stage: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    ts: Optional[str] = None


class CodingAgentActiveRunResponse(BaseModel):
    run_id: str
    status: str
    context_window: Optional[ContextWindowResponse] = None
    run_usage: Optional[RunUsageResponse] = None


class CodingAgentAnswerQuestionRequest(BaseModel):
    question_id: str = Field(min_length=1)
    answers: List[List[str]] = Field(default_factory=list)


def _run_to_response(service: PublishedAppCodingAgentRuntimeService, run) -> CodingAgentRunResponse:
    return CodingAgentRunResponse(**service.serialize_run(run))


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _normalize_run_tool_events(*, run: AgentRun) -> List[CodingAgentRunEventResponse]:
    output_result = run.output_result if isinstance(run.output_result, dict) else {}
    raw_events = output_result.get("tool_events")
    if not isinstance(raw_events, list):
        return []
    normalized: List[CodingAgentRunEventResponse] = []
    for raw_item in raw_events:
        if not isinstance(raw_item, dict):
            continue
        event_name = str(raw_item.get("event") or "").strip()
        if event_name not in {"tool.started", "tool.completed", "tool.failed"}:
            continue
        stage_value = str(raw_item.get("stage") or "tool").strip() or "tool"
        payload_value = raw_item.get("payload")
        payload_dict = payload_value if isinstance(payload_value, dict) else {}
        diagnostics_value = raw_item.get("diagnostics")
        diagnostics_list = [item for item in diagnostics_value if isinstance(item, dict)] if isinstance(diagnostics_value, list) else []
        ts_value = str(raw_item.get("ts") or "").strip() or None
        normalized.append(
            CodingAgentRunEventResponse(
                run_id=str(run.id),
                event=event_name,
                stage=stage_value,
                payload=payload_dict,
                diagnostics=diagnostics_list,
                ts=ts_value,
            )
        )
    return normalized


@router.post(
    "/{app_id}/coding-agent/v2/prompts",
    response_model=CodingAgentPromptSubmissionStartedResponse,
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

    user_prompt = (payload.input or "").strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="input is required")
    client_message_id = str(payload.client_message_id or "").strip() or None
    pipeline_trace(
        "api.prompt.received",
        pipeline="api_v2",
        app_id=str(app.id),
        actor_id=str(actor_id) if actor_id else None,
        requested_chat_session_id=str(payload.chat_session_id) if payload.chat_session_id else None,
        requested_model_id=str(payload.model_id or "") or None,
        client_message_id=client_message_id,
        prompt_chars=len(user_prompt),
    )

    runtime = PublishedAppCodingAgentRuntimeService(db)
    history = PublishedAppCodingChatHistoryService(db)
    resolved_session_id: UUID | None = None
    run_messages: list[dict[str, str]] | None = None

    if actor_id is not None:
        session = await history.resolve_or_create_session(
            app_id=app.id,
            user_id=actor_id,
            user_prompt=user_prompt,
            session_id=payload.chat_session_id,
        )
        resolved_session_id = session.id
        run_messages = await history.build_run_messages(
            session_id=session.id,
            current_user_prompt=user_prompt,
        )
        active_run = await runtime.get_active_run_for_chat_session(
            app_id=app.id,
            chat_session_id=session.id,
        )
        if active_run is not None:
            pipeline_trace(
                "api.prompt.rejected_active_run",
                pipeline="api_v2",
                app_id=str(app.id),
                actor_id=str(actor_id) if actor_id else None,
                chat_session_id=str(session.id),
                active_run_id=str(active_run.id),
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CODING_AGENT_RUN_ACTIVE",
                    "message": "A coding-agent run is already active for this chat session.",
                    "active_run_id": str(active_run.id),
                    "chat_session_id": str(session.id),
                    "client_message_id": client_message_id,
                },
            )

    run = await runtime.create_run(
        app=app,
        base_revision=draft,
        actor_id=actor_id,
        user_prompt=user_prompt,
        messages=run_messages,
        requested_model_id=(str(payload.model_id or "").strip() or None),
        chat_session_id=resolved_session_id,
    )
    pipeline_trace(
        "api.prompt.run_created",
        pipeline="api_v2",
        app_id=str(app.id),
        run_id=str(run.id),
        actor_id=str(actor_id) if actor_id else None,
        chat_session_id=str(resolved_session_id) if resolved_session_id else None,
    )

    if resolved_session_id is not None:
        await history.persist_user_message(
            session_id=resolved_session_id,
            run_id=run.id,
            content=user_prompt,
        )
    else:
        await db.commit()

    await PublishedAppCodingRunMonitor(db).ensure_monitor(app_id=app.id, run_id=run.id)
    pipeline_trace(
        "api.prompt.monitor_ensured",
        pipeline="api_v2",
        app_id=str(app.id),
        run_id=str(run.id),
    )
    return CodingAgentPromptSubmissionStartedResponse(
        run=_run_to_response(runtime, run),
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
    heartbeat_raw = (os.getenv("APPS_CODING_AGENT_STREAM_HEARTBEAT_SECONDS") or "").strip()
    try:
        heartbeat_seconds = float(heartbeat_raw) if heartbeat_raw else 10.0
    except Exception:
        heartbeat_seconds = 10.0
    heartbeat_seconds = max(1.0, min(heartbeat_seconds, 30.0))

    async def event_generator():
        pipeline_trace(
            "api.stream.opened",
            pipeline="api_v2",
            app_id=str(app.id),
            run_id=str(run.id),
        )
        PublishedAppCodingRunMonitor._trace(
            "api.stream.opened",
            app_id=str(app.id),
            run_id=str(run.id),
        )
        yield ": " + (" " * 2048) + "\n\n"
        stream_iter = monitor.stream_events(
            app_id=app.id,
            run_id=run.id,
        ).__aiter__()
        pending_next: asyncio.Task | None = None
        try:
            while True:
                if pending_next is None:
                    pending_next = asyncio.create_task(stream_iter.__anext__())
                try:
                    done, _ = await asyncio.wait({pending_next}, timeout=heartbeat_seconds)
                except asyncio.CancelledError:
                    if pending_next is not None and not pending_next.done():
                        pending_next.cancel()
                        with suppress(Exception):
                            await pending_next
                    raise
                if not done:
                    pipeline_trace(
                        "api.stream.heartbeat",
                        pipeline="api_v2",
                        app_id=str(app.id),
                        run_id=str(run.id),
                    )
                    PublishedAppCodingRunMonitor._trace(
                        "api.stream.heartbeat",
                        app_id=str(app.id),
                        run_id=str(run.id),
                    )
                    yield ": ping\n\n"
                    continue
                task = done.pop()
                pending_next = None
                try:
                    payload = task.result()
                except StopAsyncIteration:
                    break
                yield _sse(dict(payload))
                await asyncio.sleep(0)
        finally:
            if pending_next is not None and not pending_next.done():
                pending_next.cancel()
                with suppress(Exception):
                    await pending_next
            with suppress(Exception):
                await stream_iter.aclose()
            pipeline_trace(
                "api.stream.closed",
                pipeline="api_v2",
                app_id=str(app.id),
                run_id=str(run.id),
            )
            PublishedAppCodingRunMonitor._trace(
                "api.stream.closed",
                app_id=str(app.id),
                run_id=str(run.id),
            )

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
    PublishedAppCodingRunMonitor._trace(
        "api.cancel.requested",
        app_id=str(app.id),
        run_id=str(run.id),
        status=(run.status.value if hasattr(run.status, "value") else str(run.status)),
    )
    pipeline_trace(
        "api.cancel.requested",
        pipeline="api_v2",
        app_id=str(app.id),
        run_id=str(run.id),
        status=(run.status.value if hasattr(run.status, "value") else str(run.status)),
    )
    await PublishedAppCodingRunMonitor(db).ensure_monitor(app_id=app.id, run_id=run.id)
    run = await service.cancel_run(run)
    PublishedAppCodingRunMonitor._trace(
        "api.cancel.persisted",
        app_id=str(app.id),
        run_id=str(run.id),
        status=(run.status.value if hasattr(run.status, "value") else str(run.status)),
    )
    pipeline_trace(
        "api.cancel.persisted",
        pipeline="api_v2",
        app_id=str(app.id),
        run_id=str(run.id),
        status=(run.status.value if hasattr(run.status, "value") else str(run.status)),
    )
    return _run_to_response(service, run)


@router.post("/{app_id}/coding-agent/v2/runs/{run_id}/answer-question", response_model=CodingAgentRunResponse)
async def answer_coding_agent_run_question(
    app_id: UUID,
    run_id: UUID,
    payload: CodingAgentAnswerQuestionRequest,
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
    pipeline_trace(
        "api.answer_question.requested",
        pipeline="api_v2",
        app_id=str(app.id),
        run_id=str(run.id),
        question_id=payload.question_id,
        answer_groups=len(payload.answers or []),
    )
    await PublishedAppCodingRunMonitor(db).ensure_monitor(app_id=app.id, run_id=run.id)
    updated = await service.answer_question(
        run=run,
        question_id=payload.question_id,
        answers=payload.answers,
    )
    pipeline_trace(
        "api.answer_question.sent",
        pipeline="api_v2",
        app_id=str(app.id),
        run_id=str(run.id),
        question_id=payload.question_id,
    )
    return _run_to_response(service, updated)


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
    limit: int = Query(default=10, ge=1, le=100),
    before_message_id: Optional[UUID] = Query(default=None),
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
    messages, has_more, next_before_message_id = await history_service.list_messages_page(
        session_id=session.id,
        limit=limit,
        before_message_id=before_message_id,
    )
    run_events: List[CodingAgentRunEventResponse] = []
    run_ids_in_order: List[UUID] = []
    seen_run_ids: set[UUID] = set()
    run_rows: list[AgentRun] = []
    runs_by_id: dict[str, AgentRun] = {}
    for item in messages:
        run_id = item.run_id
        if run_id in seen_run_ids:
            continue
        seen_run_ids.add(run_id)
        run_ids_in_order.append(run_id)
    if run_ids_in_order:
        run_rows = list(
            (
                await db.execute(
                    select(AgentRun).where(
                        and_(
                            AgentRun.id.in_(run_ids_in_order),
                            AgentRun.published_app_id == app.id,
                            AgentRun.surface == CODING_AGENT_SURFACE,
                        )
                    )
                )
            ).scalars().all()
        )
        runs_by_id = {str(row.id): row for row in run_rows}
        for run_id in run_ids_in_order:
            run = runs_by_id.get(str(run_id))
            if run is None:
                continue
            run_events.extend(_normalize_run_tool_events(run=run))
    context_run = runs_by_id.get(str(run_ids_in_order[-1])) if run_ids_in_order else None
    return CodingAgentChatSessionDetailResponse(
        session=CodingAgentChatSessionResponse(**history_service.serialize_session(session)),
        messages=[CodingAgentChatMessageResponse(**history_service.serialize_message(item)) for item in messages],
        run_events=run_events,
        paging=CodingAgentChatSessionPagingResponse(
            has_more=has_more,
            next_before_message_id=str(next_before_message_id) if next_before_message_id else None,
        ),
        context_window=ContextWindowService.read_from_run(context_run),
        run_usage=usage_payload_from_run(context_run),
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

    runtime_service = PublishedAppCodingAgentRuntimeService(db)
    run = await runtime_service.get_active_run_for_chat_session(
        app_id=app.id,
        chat_session_id=session.id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="No active coding-agent run for this chat session")

    status = run.status.value if hasattr(run.status, "value") else str(run.status)
    return CodingAgentActiveRunResponse(
        run_id=str(run.id),
        status=status,
        context_window=ContextWindowService.read_from_run(run),
        run_usage=usage_payload_from_run(run),
    )


@router.get("/{app_id}/coding-agent/v2/checkpoints", response_model=List[CodingAgentCheckpointResponse])
async def list_coding_agent_checkpoints(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, request, limit, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "CODING_AGENT_CHECKPOINTS_ENDPOINT_REMOVED",
            "message": "Checkpoint endpoints were removed. Use /admin/apps/{app_id}/versions/{version_id}/restore.",
        },
    )


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
    _ = (app_id, checkpoint_id, payload, request, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "CODING_AGENT_CHECKPOINTS_ENDPOINT_REMOVED",
            "message": "Checkpoint restore endpoint was removed. Use /admin/apps/{app_id}/versions/{version_id}/restore.",
        },
    )
