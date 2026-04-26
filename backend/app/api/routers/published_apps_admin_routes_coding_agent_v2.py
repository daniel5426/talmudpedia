from __future__ import annotations

import asyncio
from contextlib import suppress
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.session import get_db
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor
from app.services.published_app_coding_chat_session_service import PublishedAppCodingChatSessionService
from app.services.opencode_server_client import OpenCodeServerClient

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _get_app_for_tenant,
    _get_revision,
    _resolve_organization_admin_context,
)
from .published_apps_admin_shared import router


class CodingAgentCreateChatSessionRequest(BaseModel):
    title: Optional[str] = None


class CodingAgentSubmitMessageRequest(BaseModel):
    message_id: Optional[str] = None
    parts: List[Dict[str, Any]] = Field(default_factory=list)
    model_id: Optional[str] = None


class CodingAgentAnswerPermissionRequest(BaseModel):
    answers: List[List[str]] = Field(default_factory=list)


class CodingAgentChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class CodingAgentChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    parts: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class CodingAgentChatSessionPagingResponse(BaseModel):
    has_more: bool = False
    next_before_message_id: Optional[str] = None


class CodingAgentChatSessionDetailResponse(BaseModel):
    session: CodingAgentChatSessionResponse
    messages: List[CodingAgentChatMessageResponse] = Field(default_factory=list)
    paging: CodingAgentChatSessionPagingResponse


class CodingAgentMessageAcceptedResponse(BaseModel):
    submission_status: Literal["accepted"] = "accepted"
    chat_session_id: str
    message: CodingAgentChatMessageResponse


class CodingAgentAckResponse(BaseModel):
    ok: bool = True


class CodingAgentCheckpointResponse(BaseModel):
    checkpoint_id: str
    run_id: str
    app_id: str
    revision_id: Optional[str] = None
    created_at: datetime


async def _mark_latest_prompt_async_run_terminal(
    *,
    reader_factory: async_sessionmaker[AsyncSession],
    app_id: UUID,
    chat_session_id: UUID,
    terminal_status: str,
    error_message: str | None = None,
) -> None:
    async with reader_factory() as db:
        result = await db.execute(
            select(AgentRun)
            .where(
                AgentRun.published_app_id == app_id,
                AgentRun.surface == "published_app_coding_agent",
                AgentRun.status.in_([RunStatus.queued, RunStatus.running]),
            )
            .order_by(AgentRun.created_at.desc())
            .limit(20)
        )
        runs = list(result.scalars().all())
        target: AgentRun | None = None
        for run in runs:
            input_params = run.input_params if isinstance(run.input_params, dict) else {}
            context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
            if str(context.get("chat_session_id") or "").strip() != str(chat_session_id):
                continue
            if str(context.get("opencode_submission_mode") or "").strip() != "session_prompt_async":
                continue
            target = run
            break
        if target is None:
            return
        target.started_at = target.started_at or target.created_at or datetime.now(timezone.utc)
        target.completed_at = datetime.now(timezone.utc)
        if terminal_status == RunStatus.failed.value:
            target.status = RunStatus.failed
            target.error_message = str(error_message or "OpenCode session failed")
        else:
            target.status = RunStatus.completed
            target.error_message = None
        await db.commit()
        if terminal_status == RunStatus.completed.value:
            asyncio.create_task(
                PublishedAppCodingRunMonitor._finalize_terminal_scope_detached(app_id=app_id, run_id=target.id)
            )


class CodingAgentRestoreCheckpointRequest(BaseModel):
    run_id: Optional[UUID] = None


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _serialize_messages(messages: list[dict[str, Any]]) -> list[CodingAgentChatMessageResponse]:
    return [CodingAgentChatMessageResponse(**item) for item in messages]


async def _build_remote_session_catchup_events(
    *,
    service: PublishedAppCodingChatSessionService,
    chat_session: PublishedAppCodingChatSession,
) -> list[dict[str, Any]]:
    remote_session_id = str(chat_session.opencode_session_id or "").strip()
    if not remote_session_id:
        return []
    raw_messages = await service.client.list_messages(
        session_id=remote_session_id,
        sandbox_id=str(chat_session.opencode_sandbox_id or "").strip() or None,
        workspace_path=str(chat_session.opencode_workspace_path or "").strip() or None,
        limit=50,
    )
    latest_user_id = ""
    latest_user_created_at = -1
    latest_assistant_raw: dict[str, Any] | None = None
    latest_assistant_payload: dict[str, Any] | None = None
    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue
        serialized = service._serialize_remote_message(raw_message)
        if not serialized:
            continue
        role = str(serialized.get("role") or "").strip().lower()
        if role == "user":
            latest_user_id = str(serialized.get("id") or "").strip()
            raw_info = raw_message.get("info") if isinstance(raw_message.get("info"), dict) else {}
            raw_time = raw_info.get("time") if isinstance(raw_info.get("time"), dict) else {}
            latest_user_created_at = int(raw_time.get("created") or 0)
            continue
        if role != "assistant":
            continue
        latest_assistant_raw = raw_message
        latest_assistant_payload = serialized
    if latest_assistant_payload is None:
        return []
    assistant_info = latest_assistant_raw.get("info") if isinstance(latest_assistant_raw.get("info"), dict) else {}
    assistant_parent_id = str(assistant_info.get("parentID") or assistant_info.get("parentId") or "").strip()
    assistant_time = assistant_info.get("time") if isinstance(assistant_info.get("time"), dict) else {}
    assistant_created_at = int(assistant_time.get("created") or 0)
    if latest_user_id:
        if assistant_parent_id and assistant_parent_id != latest_user_id:
            return []
        if not assistant_parent_id and assistant_created_at and assistant_created_at < latest_user_created_at:
            return []

    events: list[dict[str, Any]] = [
        {
            "event": "message.updated",
            "session_id": str(chat_session.id),
            "payload": {
                "info": {
                    "id": latest_assistant_payload["id"],
                    "role": "assistant",
                }
            },
        }
    ]
    for part in latest_assistant_payload.get("parts") or []:
        if not isinstance(part, dict):
            continue
        events.append(
            {
                "event": "message.part.updated",
                "session_id": str(chat_session.id),
                "payload": {"part": dict(part)},
            }
        )
    if latest_assistant_raw and OpenCodeServerClient._assistant_message_is_final(latest_assistant_raw):
        events.append(
            {
                "event": "session.idle",
                "session_id": str(chat_session.id),
                "payload": {},
            }
        )
    return events


@router.post(
    "/{app_id}/coding-agent/v2/chat-sessions",
    response_model=CodingAgentChatSessionResponse,
)
async def create_coding_agent_chat_session(
    app_id: UUID,
    payload: CodingAgentCreateChatSessionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat sessions")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    service = PublishedAppCodingChatSessionService(db)
    session = await service.create_chat_session(app=app, actor_id=actor_id, title=payload.title)
    return CodingAgentChatSessionResponse(**service.history.serialize_session(session))


@router.get("/{app_id}/coding-agent/v2/chat-sessions", response_model=List[CodingAgentChatSessionResponse])
async def list_coding_agent_chat_sessions(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        return []
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    history = PublishedAppCodingChatHistoryService(db)
    sessions = await history.list_sessions(app_id=app.id, user_id=actor_id, limit=limit)
    return [CodingAgentChatSessionResponse(**history.serialize_session(session)) for session in sessions]


@router.get(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}",
    response_model=CodingAgentChatSessionDetailResponse,
)
async def get_coding_agent_chat_session(
    app_id: UUID,
    session_id: UUID,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat history")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    service = PublishedAppCodingChatSessionService(db)
    session = await service.get_chat_session_for_user(app=app, actor_id=actor_id, session_id=session_id)
    session_payload = CodingAgentChatSessionResponse(**service.history.serialize_session(session))
    messages = await service.list_remote_messages(chat_session=session, limit=limit)
    return CodingAgentChatSessionDetailResponse(
        session=session_payload,
        messages=_serialize_messages(messages),
        paging=CodingAgentChatSessionPagingResponse(has_more=False, next_before_message_id=None),
    )


@router.get(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/messages",
    response_model=List[CodingAgentChatMessageResponse],
)
async def list_coding_agent_chat_session_messages(
    app_id: UUID,
    session_id: UUID,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat history")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    service = PublishedAppCodingChatSessionService(db)
    session = await service.get_chat_session_for_user(app=app, actor_id=actor_id, session_id=session_id)
    messages = await service.list_remote_messages(chat_session=session, limit=limit)
    return _serialize_messages(messages)


@router.post(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/messages",
    response_model=CodingAgentMessageAcceptedResponse,
)
async def submit_coding_agent_message(
    app_id: UUID,
    session_id: UUID,
    payload: CodingAgentSubmitMessageRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    draft = await _get_revision(db, app.current_draft_revision_id)
    service = PublishedAppCodingChatSessionService(db)
    chat_session = await service.get_chat_session_for_user(app=app, actor_id=actor_id, session_id=session_id)
    parts = [dict(item) for item in payload.parts or [] if isinstance(item, dict)]
    if not parts:
        raise HTTPException(status_code=400, detail="parts is required")
    message_id = OpenCodeServerClient.normalize_message_id(payload.message_id)
    accepted = await service.submit_message(
        app=app,
        base_revision=draft,
        actor_id=actor_id,
        chat_session=chat_session,
        message_id=message_id,
        parts=parts,
        requested_model_id=payload.model_id,
    )
    return CodingAgentMessageAcceptedResponse(
        submission_status="accepted",
        chat_session_id=accepted["chat_session_id"],
        message=CodingAgentChatMessageResponse(**accepted["message"]),
    )


@router.get("/{app_id}/coding-agent/v2/chat-sessions/{session_id}/events")
async def stream_coding_agent_chat_session_events(
    app_id: UUID,
    session_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent events")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    service = PublishedAppCodingChatSessionService(db)
    chat_session = await service.get_chat_session_for_user(app=app, actor_id=actor_id, session_id=session_id)
    resolved_chat_session_id = chat_session.id
    reader_factory = async_sessionmaker(bind=db.bind, expire_on_commit=False)

    async def event_generator():
        yield ": " + (" " * 2048) + "\n\n"
        yield _sse({"event": "session.connected", "session_id": str(chat_session.id), "payload": {}})
        resolved_chat_session = chat_session
        remote_session_id = str(resolved_chat_session.opencode_session_id or "").strip()
        resolved_sandbox_id = str(resolved_chat_session.opencode_sandbox_id or "").strip() or None
        resolved_workspace_path = str(resolved_chat_session.opencode_workspace_path or "").strip() or None
        while not remote_session_id:
            if await request.is_disconnected():
                return
            async with reader_factory() as reader_session:
                row = (
                    await reader_session.execute(
                        text(
                            """
                            select
                                opencode_session_id,
                                opencode_sandbox_id,
                                opencode_workspace_path
                            from published_app_coding_chat_sessions
                            where id = :session_id
                            """
                        ),
                        {"session_id": resolved_chat_session_id},
                    )
                ).mappings().first()
            if row is None:
                return
            remote_session_id = str(row.get("opencode_session_id") or "").strip()
            resolved_sandbox_id = str(row.get("opencode_sandbox_id") or "").strip() or None
            resolved_workspace_path = str(row.get("opencode_workspace_path") or "").strip() or None
            if remote_session_id:
                resolved_chat_session.opencode_session_id = remote_session_id
                resolved_chat_session.opencode_sandbox_id = resolved_sandbox_id
                resolved_chat_session.opencode_workspace_path = resolved_workspace_path
                break
            yield ": ping\n\n"
            await asyncio.sleep(0.25)
        catchup_events = await _build_remote_session_catchup_events(
            service=service,
            chat_session=resolved_chat_session,
        )
        for payload in catchup_events:
            yield _sse(dict(payload))
        stream_iter = service.client.stream_session_events(
            session_id=remote_session_id,
            sandbox_id=resolved_sandbox_id,
            workspace_path=resolved_workspace_path,
        ).__aiter__()
        heartbeat_seconds = 1.0
        pending_next: asyncio.Task | None = asyncio.create_task(stream_iter.__anext__())
        try:
            while True:
                try:
                    done, _ = await asyncio.wait({pending_next}, timeout=heartbeat_seconds)
                except asyncio.CancelledError:
                    if pending_next is not None and not pending_next.done():
                        pending_next.cancel()
                        with suppress(Exception):
                            await pending_next
                    raise
                if not done:
                    yield ": ping\n\n"
                    continue
                task = done.pop()
                pending_next = None
                try:
                    payload = task.result()
                except StopAsyncIteration:
                    break
                normalized_payload = dict(payload)
                normalized_payload["session_id"] = str(resolved_chat_session_id)
                event_name = str(normalized_payload.get("event") or "").strip()
                if event_name == "session.idle":
                    asyncio.create_task(
                        _mark_latest_prompt_async_run_terminal(
                            reader_factory=reader_factory,
                            app_id=app.id,
                            chat_session_id=resolved_chat_session_id,
                            terminal_status=RunStatus.completed.value,
                        )
                    )
                elif event_name == "session.error":
                    payload_body = normalized_payload.get("payload")
                    payload_dict = payload_body if isinstance(payload_body, dict) else {}
                    asyncio.create_task(
                        _mark_latest_prompt_async_run_terminal(
                            reader_factory=reader_factory,
                            app_id=app.id,
                            chat_session_id=resolved_chat_session_id,
                            terminal_status=RunStatus.failed.value,
                            error_message=str(payload_dict.get("error") or "").strip() or None,
                        )
                    )
                yield _sse(normalized_payload)
                await asyncio.sleep(0)
                pending_next = asyncio.create_task(stream_iter.__anext__())
        finally:
            if pending_next is not None and not pending_next.done():
                pending_next.cancel()
                with suppress(Exception):
                    await pending_next
            with suppress(Exception):
                await stream_iter.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/abort",
    response_model=CodingAgentAckResponse,
)
async def abort_coding_agent_chat_session(
    app_id: UUID,
    session_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    service = PublishedAppCodingChatSessionService(db)
    chat_session = await service.get_chat_session_for_user(app=app, actor_id=actor_id, session_id=session_id)
    ok = await service.abort_chat_session(chat_session=chat_session)
    return CodingAgentAckResponse(ok=bool(ok))


@router.post(
    "/{app_id}/coding-agent/v2/chat-sessions/{session_id}/permissions/{permission_id}",
    response_model=CodingAgentAckResponse,
)
async def answer_coding_agent_permission(
    app_id: UUID,
    session_id: UUID,
    permission_id: str,
    payload: CodingAgentAnswerPermissionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="User context is required for coding-agent chat")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    service = PublishedAppCodingChatSessionService(db)
    chat_session = await service.get_chat_session_for_user(app=app, actor_id=actor_id, session_id=session_id)
    ok = await service.reply_request(
        chat_session=chat_session,
        request_id=permission_id,
        answers=payload.answers,
    )
    return CodingAgentAckResponse(ok=bool(ok))


@router.get("/{app_id}/coding-agent/v2/checkpoints", response_model=List[CodingAgentCheckpointResponse])
async def list_coding_agent_checkpoints(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, request, principal, db)
    raise HTTPException(
        status_code=404,
        detail={
            "code": "CODING_AGENT_CHECKPOINTS_REMOVED",
            "message": "Checkpoint endpoints were removed. Use /admin/apps/{app_id}/versions/{version_id}/restore.",
        },
    )


@router.post(
    "/{app_id}/coding-agent/v2/checkpoints/{checkpoint_id}/restore",
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
        status_code=404,
        detail={
            "code": "CODING_AGENT_CHECKPOINTS_REMOVED",
            "message": "Checkpoint restore endpoint was removed. Use /admin/apps/{app_id}/versions/{version_id}/restore.",
        },
    )
