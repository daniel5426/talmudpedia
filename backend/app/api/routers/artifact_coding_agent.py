from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.schemas.context_window import ContextWindowResponse
from app.api.schemas.run_usage import RunUsageResponse
from app.api.routers.artifacts import get_artifact_context
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.stream_contract_v2 import build_stream_v2_event, normalize_filtered_event_to_v2
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.artifact_runtime import ArtifactCodingSession
from app.db.postgres.models.identity import Organization
from app.db.postgres.engine import sessionmaker as db_sessionmaker
from app.db.postgres.session import get_db
from app.services.artifact_coding_agent_tools import ARTIFACT_CODING_AGENT_SURFACE
from app.services.artifact_coding_chat_history_service import ArtifactCodingChatHistoryService
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.services.context_window_service import ContextWindowService
from app.services.model_accounting import usage_payload_from_run

router = APIRouter(prefix="/admin/artifacts/coding-agent/v1", tags=["artifacts"])

logger = logging.getLogger(__name__)


class ArtifactCodingPromptRequest(BaseModel):
    input: str
    chat_session_id: Optional[UUID] = None
    artifact_id: Optional[UUID] = None
    draft_key: Optional[str] = None
    model_id: Optional[str] = None
    client_message_id: Optional[str] = None
    draft_snapshot: Dict[str, Any] = Field(default_factory=dict)


class ArtifactCodingRunResponse(BaseModel):
    run_id: str
    status: str
    chat_session_id: Optional[str] = None
    artifact_id: Optional[str] = None
    draft_key: Optional[str] = None
    surface: Optional[str] = None
    requested_model_id: Optional[str] = None
    resolved_model_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    context_window: Optional[ContextWindowResponse] = None
    run_usage: Optional[RunUsageResponse] = None


class ArtifactCodingPromptSubmissionResponse(BaseModel):
    submission_status: str = "started"
    chat_session_id: str
    run: ArtifactCodingRunResponse


class ArtifactCodingChatSessionResponse(BaseModel):
    id: str
    title: str
    artifact_id: Optional[str] = None
    draft_key: Optional[str] = None
    active_run_id: Optional[str] = None
    last_run_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class ArtifactCodingChatMessageResponse(BaseModel):
    id: str
    run_id: str
    role: str
    content: str
    created_at: datetime


class ArtifactCodingRunEventResponse(BaseModel):
    run_id: str
    event: str
    stage: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    ts: Optional[str] = None


class ArtifactCodingChatSessionPagingResponse(BaseModel):
    has_more: bool = False
    next_before_message_id: Optional[str] = None


class ArtifactCodingChatSessionDetailResponse(BaseModel):
    session: ArtifactCodingChatSessionResponse
    messages: List[ArtifactCodingChatMessageResponse] = Field(default_factory=list)
    run_events: List[ArtifactCodingRunEventResponse] = Field(default_factory=list)
    draft_snapshot: Dict[str, Any] = Field(default_factory=dict)
    paging: ArtifactCodingChatSessionPagingResponse
    context_window: Optional[ContextWindowResponse] = None


class ArtifactCodingDraftSnapshotResponse(BaseModel):
    session_id: str
    draft_snapshot: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class ArtifactCodingActiveRunResponse(BaseModel):
    run_id: str
    status: str
    context_window: Optional[ContextWindowResponse] = None
    run_usage: Optional[RunUsageResponse] = None


class ArtifactCodingAnswerQuestionRequest(BaseModel):
    question_id: str = Field(min_length=1)
    answers: List[List[str]] = Field(default_factory=list)


class ArtifactCodingCancelRunRequest(BaseModel):
    assistant_output_text: Optional[str] = None


class ArtifactCodingRevertRequest(BaseModel):
    run_id: UUID


def _session_scope_snapshot(session: ArtifactCodingSession | None) -> dict[str, Any]:
    if session is None:
        return {
            "chat_session_id": None,
            "artifact_id": None,
            "draft_key": None,
        }
    return {
        "chat_session_id": str(session.id),
        "artifact_id": str(session.artifact_id) if session.artifact_id else None,
        "draft_key": session.draft_key,
    }


def _run_response_from_snapshot(
    run: AgentRun,
    *,
    session_scope: dict[str, Any] | None = None,
) -> ArtifactCodingRunResponse:
    scope = session_scope or {"chat_session_id": None, "artifact_id": None, "draft_key": None}
    return ArtifactCodingRunResponse(
        run_id=str(run.id),
        status=str(getattr(run.status, "value", run.status)),
        chat_session_id=scope.get("chat_session_id"),
        artifact_id=scope.get("artifact_id"),
        draft_key=scope.get("draft_key"),
        surface=str(run.surface or "") or None,
        requested_model_id=str(run.requested_model_id) if run.requested_model_id else None,
        resolved_model_id=str(run.resolved_model_id) if run.resolved_model_id else None,
        error=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        context_window=ContextWindowService.read_from_run(run),
        run_usage=usage_payload_from_run(run),
    )


def _project_id_from_principal(principal: Dict[str, Any] | None) -> UUID | None:
    raw = (principal or {}).get("project_id")
    try:
        return UUID(str(raw)) if raw else None
    except Exception:
        return None


async def _require_user_context(artifact_ctx) -> tuple[Organization, Any, AsyncSession]:
    organization, user, db = artifact_ctx
    if organization is None:
        raise HTTPException(status_code=400, detail="Organization context required")
    if user is None:
        raise HTTPException(status_code=403, detail="User context is required for artifact coding chat")
    return organization, user, db


async def _get_session_for_user_or_404(
    *,
    db: AsyncSession,
    organization_id: UUID,
    project_id: UUID | None,
    user_id: UUID,
    session_id: UUID,
) -> ArtifactCodingSession:
    history = ArtifactCodingChatHistoryService(db)
    session = await history.get_session_for_user(
        organization_id=organization_id,
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Artifact coding chat session not found")
    return session


async def _require_run_owner(
    *,
    db: AsyncSession,
    organization_id: UUID,
    project_id: UUID | None,
    user_id: UUID,
    run_id: UUID,
) -> tuple[AgentRun, ArtifactCodingSession]:
    run = await db.get(AgentRun, run_id)
    if (
        run is None
        or run.organization_id != organization_id
        or run.project_id != project_id
        or str(run.surface or "") != ARTIFACT_CODING_AGENT_SURFACE
    ):
        raise HTTPException(status_code=404, detail="Artifact coding run not found")
    session_id = _session_id_for_run(run)
    if session_id is None:
        raise HTTPException(status_code=404, detail="Artifact coding run is missing a bound chat session")
    session = await _get_session_for_user_or_404(
        db=db,
        organization_id=organization_id,
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
    )
    return run, session


def _normalize_trace_events(
    *,
    run_id: UUID,
    raw_events: list[dict[str, Any]],
) -> list[ArtifactCodingRunEventResponse]:
    normalized: list[ArtifactCodingRunEventResponse] = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or "").strip()
        event_type = str(item.get("type") or "").strip()
        if event_name not in {"on_tool_start", "on_tool_end", "tool.failed"} and event_name != "token" and event_type != "token":
            continue
        mapped, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=item)
        normalized.append(
            ArtifactCodingRunEventResponse(
                run_id=str(run_id),
                event=mapped,
                stage=stage,
                payload=payload,
                diagnostics=diagnostics,
                ts=str(item.get("ts") or "") or None,
            )
        )
    return normalized


async def _reconcile_session_run(
    *,
    db: AsyncSession,
    session: ArtifactCodingSession,
    run: AgentRun,
) -> None:
    history = ArtifactCodingChatHistoryService(db)
    await history.reconcile_session_run(session=session, run=run)
    await db.commit()


async def _build_session_detail_response(
    *,
    db: AsyncSession,
    organization_id: UUID,
    session: ArtifactCodingSession,
    before_message_id: UUID | None,
    limit: int,
) -> ArtifactCodingChatSessionDetailResponse:
    history = ArtifactCodingChatHistoryService(db)
    shared_drafts = ArtifactCodingSharedDraftService(db)
    messages, has_more, next_before_message_id = await history.list_messages_page(
        session_id=session.id,
        limit=limit,
        before_message_id=before_message_id,
    )
    run_events: list[ArtifactCodingRunEventResponse] = []
    run_ids: list[UUID] = []
    seen: set[UUID] = set()
    for message in messages:
        if message.run_id in seen:
            continue
        seen.add(message.run_id)
        run_ids.append(message.run_id)
    if run_ids:
        recorder = ExecutionTraceRecorder(serializer=lambda value: value)
        for run_id in run_ids:
            run = await db.get(AgentRun, run_id)
            if run is None or run.organization_id != organization_id:
                continue
            raw_events = await recorder.list_events(db, run_id)
            run_events.extend(_normalize_trace_events(run_id=run_id, raw_events=raw_events))
    context_run: AgentRun | None = None
    if session.active_run_id is not None:
        context_run = await db.get(AgentRun, session.active_run_id)
    if context_run is None and session.last_run_id is not None:
        context_run = await db.get(AgentRun, session.last_run_id)
    return ArtifactCodingChatSessionDetailResponse(
        session=ArtifactCodingChatSessionResponse(**history.serialize_session(session)),
        messages=[ArtifactCodingChatMessageResponse(**history.serialize_message(item)) for item in messages],
        run_events=run_events,
        draft_snapshot=dict((await shared_drafts.resolve_for_session(session=session)).working_draft_snapshot or {}),
        paging=ArtifactCodingChatSessionPagingResponse(
            has_more=has_more,
            next_before_message_id=str(next_before_message_id) if next_before_message_id else None,
        ),
        context_window=ContextWindowService.read_from_run(context_run),
    )


@router.get("/sessions", response_model=List[ArtifactCodingChatSessionResponse])
async def list_artifact_coding_sessions(
    artifact_id: Optional[UUID] = None,
    draft_key: Optional[str] = None,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    if artifact_id is None and not str(draft_key or "").strip():
        raise HTTPException(status_code=400, detail="artifact_id or draft_key is required")
    sessions = await ArtifactCodingChatHistoryService(db).list_sessions(
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        artifact_id=artifact_id,
        draft_key=str(draft_key or "").strip() or None,
        limit=limit,
    )
    return [ArtifactCodingChatSessionResponse(**ArtifactCodingChatHistoryService(db).serialize_session(item)) for item in sessions]


@router.get("/sessions/{session_id}", response_model=ArtifactCodingChatSessionDetailResponse)
async def get_artifact_coding_session(
    session_id: UUID,
    before_message_id: Optional[UUID] = None,
    limit: int = Query(default=10, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    history = ArtifactCodingChatHistoryService(db)
    shared_drafts = ArtifactCodingSharedDraftService(db)
    session = await _get_session_for_user_or_404(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        session_id=session_id,
    )
    if session.last_run_id is not None:
        run = await db.get(AgentRun, session.last_run_id)
        if run is not None:
            await _reconcile_session_run(db=db, session=session, run=run)
            await db.refresh(session)
    return await _build_session_detail_response(
        db=db,
        organization_id=organization.id,
        session=session,
        before_message_id=before_message_id,
        limit=limit,
    )


@router.get("/sessions/{session_id}/draft-snapshot", response_model=ArtifactCodingDraftSnapshotResponse)
async def get_artifact_coding_session_draft_snapshot(
    session_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    session = await _get_session_for_user_or_404(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        session_id=session_id,
    )
    shared_draft = await ArtifactCodingSharedDraftService(db).resolve_for_session(session=session)
    return ArtifactCodingDraftSnapshotResponse(
        session_id=str(session.id),
        draft_snapshot=dict(shared_draft.working_draft_snapshot or {}),
        updated_at=shared_draft.updated_at,
    )


@router.get("/sessions/{session_id}/active-run", response_model=ArtifactCodingActiveRunResponse)
async def get_artifact_coding_session_active_run(
    session_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    session = await _get_session_for_user_or_404(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        session_id=session_id,
    )
    if session.active_run_id is None:
        raise HTTPException(status_code=404, detail="No active artifact coding run for this chat session")
    run = await db.get(AgentRun, session.active_run_id)
    if run is None:
        session.active_run_id = None
        await db.commit()
        raise HTTPException(status_code=404, detail="No active artifact coding run for this chat session")
    status = str(getattr(run.status, "value", run.status) or "")
    if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
        await _reconcile_session_run(db=db, session=session, run=run)
        raise HTTPException(status_code=404, detail="No active artifact coding run for this chat session")
    return ArtifactCodingActiveRunResponse(
        run_id=str(run.id),
        status=status,
        context_window=ContextWindowService.read_from_run(run),
        run_usage=usage_payload_from_run(run),
    )


@router.post("/prompts", response_model=ArtifactCodingPromptSubmissionResponse)
async def submit_artifact_coding_prompt(
    payload: ArtifactCodingPromptRequest,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    user_prompt = str(payload.input or "").strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="input is required")
    requested_model_id = str(payload.model_id or "").strip() or None
    runtime = ArtifactCodingRuntimeService(db)
    try:
        session, _shared_draft, run = await runtime.start_prompt_run(
            organization_id=organization.id,
            project_id=_project_id_from_principal(principal),
            user_id=user.id,
            user_prompt=user_prompt,
            artifact_id=payload.artifact_id,
            draft_key=str(payload.draft_key or "").strip() or None,
            chat_session_id=payload.chat_session_id,
            draft_snapshot=dict(payload.draft_snapshot or {}),
            model_id=requested_model_id,
        )
    except RuntimeError as exc:
        if str(exc) == "CODING_AGENT_RUN_ACTIVE":
            session = await _get_session_for_user_or_404(
                db=db,
                organization_id=organization.id,
                project_id=_project_id_from_principal(principal),
                user_id=user.id,
                session_id=payload.chat_session_id,
            )
            active_run = await db.get(AgentRun, session.active_run_id) if session.active_run_id else None
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CODING_AGENT_RUN_ACTIVE",
                    "message": "An artifact coding run is already active for this chat session.",
                    "active_run_id": str(active_run.id) if active_run else None,
                    "chat_session_id": str(session.id),
                },
            ) from exc
        raise
    session_scope = _session_scope_snapshot(session)
    return ArtifactCodingPromptSubmissionResponse(
        chat_session_id=str(session.id),
        run=_run_response_from_snapshot(run, session_scope=session_scope),
    )


@router.get("/runs/{run_id}", response_model=ArtifactCodingRunResponse)
async def get_artifact_coding_run(
    run_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    run, session = await _require_run_owner(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        run_id=run_id,
    )
    await _reconcile_session_run(db=db, session=session, run=run)
    await db.refresh(session)
    await db.refresh(run)
    return _run_response_from_snapshot(run, session_scope=_session_scope_snapshot(session))


@router.get("/runs/{run_id}/stream")
async def stream_artifact_coding_run(
    run_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    run, session = await _require_run_owner(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        run_id=run_id,
    )
    session_id = session.id if session is not None else None

    async def event_generator():
        async with db_sessionmaker() as stream_db:
            stream_run = await stream_db.get(AgentRun, run_id)
            if stream_run is None:
                yield (
                    "data: "
                    + json.dumps(
                        build_stream_v2_event(
                            seq=1,
                            run_id=str(run_id),
                            event="run.failed",
                            stage="run",
                            payload={"error": "Artifact coding run not found"},
                        ),
                        default=str,
                    )
                    + "\n\n"
                )
                return

            executor = AgentExecutorService(db=stream_db)
            stream_session = None
            if session_id is not None:
                stream_session = await stream_db.get(ArtifactCodingSession, session_id)

            seq = 1
            blocking_tool_failure_error: str | None = None
            yield ": " + (" " * 2048) + "\n\n"
            yield (
                "data: "
                + json.dumps(
                    build_stream_v2_event(
                        seq=seq,
                        run_id=str(stream_run.id),
                        event="run.accepted",
                        stage="run",
                        payload={
                            "status": str(getattr(stream_run.status, "value", stream_run.status)),
                            "thread_id": str(stream_run.thread_id) if stream_run.thread_id else None,
                            "context_window": ContextWindowService.read_from_run(stream_run),
                            "run_usage": usage_payload_from_run(stream_run),
                        },
                    ),
                    default=str,
                )
                + "\n\n"
            )
            seq += 1
            try:
                async for event_dict in executor.run_and_stream(stream_run.id, stream_db, None, mode=ExecutionMode.DEBUG):
                    mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=event_dict)
                    if mapped_event == "tool.failed":
                        payload_dict = payload if isinstance(payload, dict) else {}
                        blocking_tool_failure_error = str(
                            payload_dict.get("error")
                            or payload_dict.get("message")
                            or (diagnostics[0].get("message") if diagnostics else "")
                            or "Artifact coding tool failed"
                        ).strip() or "Artifact coding tool failed"
                    elif mapped_event == "run.completed" and blocking_tool_failure_error:
                        mapped_event = "run.failed"
                        stage = "run"
                        payload = {"error": blocking_tool_failure_error}
                        diagnostics = [{"message": blocking_tool_failure_error}]
                    envelope = build_stream_v2_event(
                        seq=seq,
                        run_id=str(stream_run.id),
                        event=mapped_event,
                        stage=stage,
                        payload=payload,
                        diagnostics=diagnostics,
                    )
                    seq += 1
                    yield f"data: {json.dumps(envelope, default=str)}\n\n"
            except Exception as exc:
                logger.exception("Artifact coding run stream failed run_id=%s", stream_run.id)
                yield (
                    "data: "
                    + json.dumps(
                        build_stream_v2_event(
                            seq=seq,
                            run_id=str(stream_run.id),
                            event="run.failed",
                            stage="run",
                            payload={"error": str(exc)},
                            diagnostics=[{"message": str(exc)}],
                        ),
                        default=str,
                    )
                    + "\n\n"
                )
            finally:
                latest_run = await stream_db.get(AgentRun, stream_run.id)
                if latest_run is not None and stream_session is not None:
                    await _reconcile_session_run(db=stream_db, session=stream_session, run=latest_run)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _session_id_for_run(run: AgentRun) -> UUID | None:
    input_context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
    if not isinstance(input_context, dict):
        return None
    raw = input_context.get("artifact_coding_session_id")
    try:
        return UUID(str(raw)) if raw else None
    except Exception:
        return None


@router.post("/runs/{run_id}/cancel", response_model=ArtifactCodingRunResponse)
async def cancel_artifact_coding_run(
    run_id: UUID,
    payload: ArtifactCodingCancelRunRequest,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    run, _session = await _require_run_owner(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        run_id=run_id,
    )
    runtime = ArtifactCodingRuntimeService(db)
    run, session = await runtime.cancel_run(
        run=run,
        partial_assistant_text=payload.assistant_output_text,
    )
    return _run_response_from_snapshot(run, session_scope=_session_scope_snapshot(session))


@router.post("/runs/{run_id}/answer-question", response_model=ArtifactCodingRunResponse)
async def answer_artifact_coding_run_question(
    run_id: UUID,
    payload: ArtifactCodingAnswerQuestionRequest,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    run, session = await _require_run_owner(
        db=db,
        organization_id=organization.id,
        project_id=_project_id_from_principal(principal),
        user_id=user.id,
        run_id=run_id,
    )
    if str(getattr(run.status, "value", run.status)) != RunStatus.paused.value:
        raise HTTPException(status_code=400, detail="Run is not paused")
    executor = AgentExecutorService(db=db)
    await executor.resume_run(
        run.id,
        {"question_id": payload.question_id, "answers": payload.answers},
        background=False,
    )
    refreshed = await db.get(AgentRun, run.id)
    return _run_response_from_snapshot(refreshed or run, session_scope=_session_scope_snapshot(session))


@router.post("/sessions/{session_id}/revert", response_model=ArtifactCodingChatSessionDetailResponse)
async def revert_artifact_coding_session_to_run(
    session_id: UUID,
    payload: ArtifactCodingRevertRequest,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = await _require_user_context(artifact_ctx)
    history = ArtifactCodingChatHistoryService(db)
    shared_drafts = ArtifactCodingSharedDraftService(db)
    project_id = _project_id_from_principal(principal)
    session = await _get_session_for_user_or_404(
        db=db,
        organization_id=organization.id,
        project_id=project_id,
        user_id=user.id,
        session_id=session_id,
    )
    if session.active_run_id is not None:
        active_run = await db.get(AgentRun, session.active_run_id)
        if active_run is not None and str(getattr(active_run.status, "value", active_run.status) or "") not in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
        }:
            raise HTTPException(status_code=409, detail="Cannot revert while this chat has an active run")
    snapshot = await shared_drafts.get_run_snapshot(
        organization_id=organization.id,
        project_id=project_id,
        run_id=payload.run_id,
        snapshot_kind="pre_run",
    )
    if snapshot is None or snapshot.session_id != session.id:
        raise HTTPException(status_code=404, detail="Artifact coding snapshot not found for this chat message")
    await shared_drafts.restore_run_snapshot(
        organization_id=organization.id,
        project_id=project_id,
        run_id=payload.run_id,
        snapshot_kind="pre_run",
    )
    await shared_drafts.set_last_run(
        shared_draft=await shared_drafts.resolve_for_session(session=session),
        run_id=payload.run_id,
    )
    await history.truncate_session_after_run(session=session, run_id=payload.run_id)
    await db.commit()
    await db.refresh(session)
    return await _build_session_detail_response(
        db=db,
        organization_id=organization.id,
        session=session,
        before_message_id=None,
        limit=10,
    )
