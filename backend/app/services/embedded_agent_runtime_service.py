from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.stream_contract_v2 import (
    build_stream_v2_event,
    normalize_filtered_event_to_v2,
)
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn
from app.services.runtime_attachment_service import RuntimeAttachmentService
from app.services.thread_service import ThreadService
from app.services.usage_quota_service import QuotaExceededError


def _stream_v2_enforced() -> bool:
    raw = (os.getenv("STREAM_V2_ENFORCED") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _turns_to_messages(turns: list[AgentThreadTurn]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for turn in sorted(turns, key=lambda item: int(item.turn_index or 0)):
        if turn.user_input_text:
            messages.append({"role": "user", "content": turn.user_input_text})
        if turn.assistant_output_text:
            messages.append({"role": "assistant", "content": turn.assistant_output_text})
    return messages


def serialize_thread_summary(thread: AgentThread) -> dict[str, Any]:
    return {
        "id": str(thread.id),
        "agent_id": str(thread.agent_id) if thread.agent_id else None,
        "external_user_id": thread.external_user_id,
        "external_session_id": thread.external_session_id,
        "title": thread.title,
        "status": thread.status.value if hasattr(thread.status, "value") else str(thread.status),
        "surface": thread.surface.value if hasattr(thread.surface, "value") else str(thread.surface),
        "last_run_id": str(thread.last_run_id) if thread.last_run_id else None,
        "last_activity_at": thread.last_activity_at,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def _serialize_turn_base(turn: AgentThreadTurn) -> dict[str, Any]:
    return {
        "id": str(turn.id),
        "run_id": str(turn.run_id),
        "turn_index": int(turn.turn_index or 0),
        "user_input_text": turn.user_input_text,
        "assistant_output_text": turn.assistant_output_text,
        "status": turn.status.value if hasattr(turn.status, "value") else str(turn.status),
        "usage_tokens": int(turn.usage_tokens or 0),
        "metadata": dict(turn.metadata_ or {}),
        "attachments": [
            RuntimeAttachmentService.serialize_attachment(link.attachment)
            for link in sorted(turn.attachment_links or [], key=lambda item: str(item.id))
            if getattr(link, "attachment", None) is not None
        ],
        "created_at": turn.created_at,
        "completed_at": turn.completed_at,
    }


def _trace_item_to_raw_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": str(item.get("event") or "").strip(),
        "name": item.get("name"),
        "span_id": item.get("span_id"),
        "visibility": item.get("visibility"),
        "data": item.get("data") if isinstance(item.get("data"), dict) else {},
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }


def _embed_history_ts(raw_timestamp: Any) -> str:
    if isinstance(raw_timestamp, str) and raw_timestamp.strip():
        return raw_timestamp
    return datetime.now(timezone.utc).isoformat()


def _embed_history_event(
    *,
    seq: int,
    run_id: UUID,
    timestamp: Any,
    mapped_event: str,
    stage: str,
    payload: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    envelope = build_stream_v2_event(
        seq=seq,
        run_id=str(run_id),
        event=mapped_event,
        stage=stage,
        payload=payload,
        diagnostics=diagnostics,
    )
    envelope["ts"] = _embed_history_ts(timestamp)
    return envelope


async def list_public_run_events(*, db: AsyncSession, run_id: UUID) -> list[dict[str, Any]]:
    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    raw_events = await recorder.list_events(db, run_id)
    events: list[dict[str, Any]] = []
    seq = 1

    for item in raw_events:
        raw_event = _trace_item_to_raw_event(item)
        event_name = str(raw_event.get("event") or "").strip()
        if not event_name:
            continue
        if event_name == "assistant.ui":
            data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}
            if not bool(data.get("is_final")):
                continue
        is_allowed = (
            StreamAdapter._is_client_safe(raw_event.get("visibility"))
            or event_name in StreamAdapter._TOOL_LIFECYCLE_EVENTS
            or event_name in StreamAdapter._PRODUCTION_LEGACY_ALLOW
        )
        if not is_allowed:
            continue

        mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=raw_event)
        if mapped_event != "assistant.delta":
            events.append(
                _embed_history_event(
                    seq=seq,
                    run_id=run_id,
                    timestamp=item.get("timestamp"),
                    mapped_event=mapped_event,
                    stage=stage,
                    payload=payload,
                    diagnostics=diagnostics,
                )
            )
            seq += 1

        reasoning = StreamAdapter._reasoning_event(
            event_type=event_name,
            event_name=str(raw_event.get("name") or "").strip() or None,
            step_id=str(raw_event.get("span_id") or "").strip() or None,
            data=raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {},
        )
        if reasoning is None:
            continue

        reasoning_event, reasoning_stage, reasoning_payload, reasoning_diagnostics = normalize_filtered_event_to_v2(
            raw_event=reasoning
        )
        events.append(
            _embed_history_event(
                seq=seq,
                run_id=run_id,
                timestamp=item.get("timestamp"),
                mapped_event=reasoning_event,
                stage=reasoning_stage,
                payload=reasoning_payload,
                diagnostics=reasoning_diagnostics,
            )
        )
        seq += 1

    return events


async def serialize_thread_detail(*, db: AsyncSession, thread: AgentThread) -> dict[str, Any]:
    payload = serialize_thread_summary(thread)
    payload["turns"] = [
        {
            **_serialize_turn_base(turn),
            "run_events": await list_public_run_events(db=db, run_id=turn.run_id),
        }
        for turn in sorted(thread.turns or [], key=lambda item: int(item.turn_index or 0))
    ]
    return payload


async def ensure_published_embed_agent(*, db: AsyncSession, agent_id: UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.status != AgentStatus.published:
        raise HTTPException(status_code=404, detail="Published agent not found")
    return agent


async def stream_embedded_agent(
    *,
    db: AsyncSession,
    agent: Agent,
    api_key_principal: dict[str, Any],
    input_text: str | None,
    messages: list[dict[str, Any]],
    attachment_ids: list[str] | None,
    thread_id: UUID | None,
    external_user_id: str,
    external_session_id: str | None,
    metadata: dict[str, Any] | None,
    client: dict[str, Any] | None,
) -> StreamingResponse | JSONResponse:
    thread_service = ThreadService(db)
    run_messages: list[dict[str, Any]] = []

    if thread_id is not None:
        existing_thread = await thread_service.get_thread_with_turns(
            tenant_id=agent.tenant_id,
            thread_id=thread_id,
            agent_id=agent.id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
        )
        if existing_thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        run_messages.extend(_turns_to_messages(list(existing_thread.turns or [])))

    run_messages.extend(list(messages or []))

    request_context = {
        "surface": "embedded_agent_runtime",
        "tenant_id": str(agent.tenant_id),
        "thread_id": str(thread_id) if thread_id else None,
        "external_user_id": external_user_id,
        "external_session_id": external_session_id,
        "tenant_api_key_id": api_key_principal["api_key_id"],
        "tenant_api_key_name": api_key_principal.get("name"),
        "tenant_api_key_prefix": api_key_principal.get("key_prefix"),
        "embed_metadata": dict(metadata or {}),
        "embed_client": dict(client or {}),
    }

    executor = AgentExecutorService(db=db)
    try:
        run_id = await executor.start_run(
            agent.id,
            {
                "messages": run_messages,
                "input": input_text,
                "attachment_ids": list(attachment_ids or []),
                "thread_id": str(thread_id) if thread_id else None,
                "context": request_context,
            },
            user_id=None,
            background=False,
            mode=ExecutionMode.PRODUCTION,
            thread_id=thread_id,
        )
    except QuotaExceededError as exc:
        return JSONResponse(status_code=429, content=exc.to_payload())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_row = await db.get(AgentRun, run_id)
    thread_id_value = str(run_row.thread_id) if run_row and run_row.thread_id else None

    async def event_generator() -> AsyncGenerator[str, None]:
        raw_stream = executor.run_and_stream(run_id, db, resume_payload=None, mode=ExecutionMode.PRODUCTION)
        filtered_stream = StreamAdapter.filter_stream(raw_stream, ExecutionMode.PRODUCTION)
        seq = 1
        yield ": " + (" " * 2048) + "\n\n"
        if _stream_v2_enforced():
            accepted = build_stream_v2_event(
                seq=seq,
                run_id=str(run_id),
                event="run.accepted",
                stage="run",
                payload={"status": "running", "thread_id": thread_id_value},
            )
            seq += 1
            yield f"data: {json.dumps(accepted, default=str)}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'run_id', 'run_id': str(run_id)})}\n\n"

        try:
            async for event_dict in filtered_stream:
                if _stream_v2_enforced():
                    mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=event_dict)
                    envelope = build_stream_v2_event(
                        seq=seq,
                        run_id=str(run_id),
                        event=mapped_event,
                        stage=stage,
                        payload=payload,
                        diagnostics=diagnostics,
                    )
                    seq += 1
                    yield f"data: {json.dumps(envelope, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps(event_dict, default=str)}\n\n"
        except Exception as exc:
            if _stream_v2_enforced():
                envelope = build_stream_v2_event(
                    seq=seq,
                    run_id=str(run_id),
                    event="run.failed",
                    stage="run",
                    payload={"error": str(exc)},
                    diagnostics=[{"message": str(exc)}],
                )
                yield f"data: {json.dumps(envelope, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
            "X-Thread-ID": thread_id_value or "",
        },
    )
