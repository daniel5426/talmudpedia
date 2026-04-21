from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.chat_response_blocks import (
    apply_stream_v2_event_to_response_blocks,
    extract_assistant_text_from_blocks,
    finalize_response_blocks,
)
from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.stream_contract_v2 import build_stream_v2_event, normalize_filtered_event_to_v2
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.db.postgres.models.agents import AgentRun

from .contracts import RuntimeEventView


def _trace_item_to_raw_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": str(item.get("event") or "").strip(),
        "name": item.get("name"),
        "span_id": item.get("span_id"),
        "visibility": item.get("visibility"),
        "data": item.get("data") if isinstance(item.get("data"), dict) else {},
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }


def _history_ts(raw_timestamp: Any) -> str:
    if isinstance(raw_timestamp, str) and raw_timestamp.strip():
        return raw_timestamp
    return datetime.now(timezone.utc).isoformat()


def _history_event(
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
    envelope["ts"] = _history_ts(timestamp)
    return envelope


async def list_run_events(
    *,
    db: AsyncSession,
    run_id: UUID,
    view: RuntimeEventView,
    after_sequence: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    raw_events = await recorder.list_events(db, run_id, after_sequence=after_sequence, limit=limit)
    if view == RuntimeEventView.internal_full:
        return raw_events

    events: list[dict[str, Any]] = []
    seq = 1
    response_blocks: list[dict[str, Any]] = []
    final_output: Any = None
    run = await db.get(AgentRun, run_id)
    if run is not None and isinstance(run.output_result, dict):
        final_output = run.output_result.get("final_output")

    for item in raw_events:
        raw_event = _trace_item_to_raw_event(item)
        event_name = str(raw_event.get("event") or "").strip()
        if not event_name:
            continue
        is_allowed = (
            StreamAdapter._is_client_safe(raw_event.get("visibility"))
            or event_name in StreamAdapter._TOOL_LIFECYCLE_EVENTS
            or event_name in StreamAdapter._PRODUCTION_LEGACY_ALLOW
        )
        if not is_allowed:
            continue

        mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=raw_event)
        response_blocks = apply_stream_v2_event_to_response_blocks(
            response_blocks,
            event=mapped_event,
            run_id=str(run_id),
            seq=seq,
            ts=_history_ts(item.get("timestamp")),
            stage=stage,
            payload=payload,
            diagnostics=diagnostics,
        )
        if mapped_event in {"run.completed", "run.failed", "run.cancelled", "run.paused"}:
            response_blocks = finalize_response_blocks(
                response_blocks,
                final_output=(payload or {}).get("final_output"),
                run_id=str(run_id),
                fallback_seq=seq,
            )
        payload = dict(payload)
        payload["response_blocks"] = response_blocks
        assistant_text = extract_assistant_text_from_blocks(response_blocks)
        if assistant_text:
            payload["assistant_output_text"] = assistant_text
        if mapped_event != "assistant.delta":
            events.append(
                _history_event(
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
        response_blocks = apply_stream_v2_event_to_response_blocks(
            response_blocks,
            event=reasoning_event,
            run_id=str(run_id),
            seq=seq,
            ts=_history_ts(item.get("timestamp")),
            stage=reasoning_stage,
            payload=reasoning_payload,
            diagnostics=reasoning_diagnostics,
        )
        reasoning_payload = dict(reasoning_payload)
        reasoning_payload["response_blocks"] = response_blocks
        assistant_text = extract_assistant_text_from_blocks(response_blocks)
        if assistant_text:
            reasoning_payload["assistant_output_text"] = assistant_text
        events.append(
            _history_event(
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

    if final_output is not None:
        finalize_response_blocks(
            response_blocks,
            final_output=final_output,
            run_id=str(run_id),
            fallback_seq=seq,
        )

    return events
