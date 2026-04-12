from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator
from uuid import UUID

from app.agent.execution.chat_response_blocks import (
    apply_stream_v2_event_to_response_blocks,
    extract_assistant_text_from_blocks,
    finalize_response_blocks,
)
from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.stream_contract_v2 import build_stream_v2_event, normalize_filtered_event_to_v2
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.agent.execution.types import ExecutionMode
from app.db.postgres.engine import sessionmaker as fresh_sessionmaker
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.context_window_service import ContextWindowService
from app.services.model_accounting import usage_payload_from_run

_TERMINAL_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
    RunStatus.paused.value,
}


def _status_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _trace_item_to_chunk(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": str(item.get("event") or "").strip(),
        "name": item.get("name"),
        "span_id": item.get("span_id"),
        "visibility": item.get("visibility"),
        "data": item.get("data") if isinstance(item.get("data"), dict) else {},
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "_sequence": int(item.get("sequence") or 0),
    }


def _iter_filtered_chunks(
    *,
    raw_events: list[dict[str, Any]],
    mode: ExecutionMode,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in raw_events:
        chunk = _trace_item_to_chunk(item)
        event_type = str(chunk.get("event") or "").strip()
        is_tool_lifecycle = event_type in StreamAdapter._TOOL_LIFECYCLE_EVENTS
        if mode == ExecutionMode.PRODUCTION and not (
            StreamAdapter._is_client_safe(chunk.get("visibility"))
            or is_tool_lifecycle
            or event_type in StreamAdapter._PRODUCTION_LEGACY_ALLOW
        ):
            continue
        events.append(chunk)
        reasoning = StreamAdapter._reasoning_event(
            event_type=event_type,
            event_name=str(chunk.get("name") or "").strip() or None,
            step_id=str(chunk.get("span_id") or "").strip() or None,
            data=chunk.get("data") if isinstance(chunk.get("data"), dict) else {},
        )
        if reasoning is not None:
            reasoning["_sequence"] = int(chunk.get("_sequence") or 0)
            events.append(reasoning)
    return events


def _legacy_terminal_payload(run: AgentRun) -> dict[str, Any]:
    status = _status_text(run.status)
    payload = {
        "event": "run_status",
        "data": {
            "status": status,
            "final_output": (
                run.output_result.get("final_output")
                if isinstance(run.output_result, dict)
                else None
            ),
            "context_window": ContextWindowService.read_from_run(run),
            "run_usage": usage_payload_from_run(run) or {},
        },
    }
    if status == RunStatus.failed.value and run.error_message:
        payload["data"]["error"] = run.error_message
    return payload


def _build_terminal_envelope(*, seq: int, run: AgentRun) -> dict[str, Any]:
    status = _status_text(run.status)
    mapped = {
        RunStatus.completed.value: "run.completed",
        RunStatus.failed.value: "run.failed",
        RunStatus.cancelled.value: "run.cancelled",
        RunStatus.paused.value: "run.paused",
    }.get(status, "run.accepted")
    payload = {
        "status": status,
        "final_output": (
            run.output_result.get("final_output")
            if isinstance(run.output_result, dict)
            else None
        ),
        "context_window": ContextWindowService.read_from_run(run),
        "run_usage": usage_payload_from_run(run) or {},
    }
    diagnostics: list[dict[str, Any]] = []
    if status == RunStatus.failed.value and run.error_message:
        diagnostics.append({"message": str(run.error_message)})
    return build_stream_v2_event(
        seq=seq,
        run_id=str(run.id),
        event=mapped,
        stage="run",
        payload=payload,
        diagnostics=diagnostics,
    )


async def stream_persisted_run_events(
    *,
    run_id: UUID,
    mode: ExecutionMode,
    stream_v2_enforced: bool,
    thread_id_value: str | None,
    poll_interval_s: float = 0.05,
    padding_bytes: int = 4096,
) -> AsyncGenerator[str, None]:
    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    seq = 1
    last_sequence = 0
    saw_terminal = False
    response_blocks: list[dict[str, Any]] = []

    yield ": " + (" " * max(0, int(padding_bytes))) + "\n\n"

    while True:
        async with fresh_sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
            if run is None:
                if stream_v2_enforced:
                    envelope = build_stream_v2_event(
                        seq=seq,
                        run_id=str(run_id),
                        event="run.failed",
                        stage="run",
                        payload={"error": "Run not found"},
                        diagnostics=[{"message": "Run not found"}],
                    )
                    yield f"data: {json.dumps(envelope, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Run not found'})}\n\n"
                return

            if seq == 1:
                if stream_v2_enforced:
                    accepted = build_stream_v2_event(
                        seq=seq,
                        run_id=str(run.id),
                        event="run.accepted",
                        stage="run",
                        payload={
                            "status": _status_text(run.status),
                            "thread_id": thread_id_value,
                            "context_window": ContextWindowService.read_from_run(run),
                            "run_usage": usage_payload_from_run(run) or {},
                            "response_blocks": [],
                        },
                    )
                    yield f"data: {json.dumps(accepted, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'run_id', 'run_id': str(run.id)})}\n\n"
                seq += 1

            raw_events = await recorder.list_events(db, run.id, after_sequence=last_sequence)
            filtered = _iter_filtered_chunks(raw_events=raw_events, mode=mode)
            for item in filtered:
                last_sequence = max(last_sequence, int(item.get("_sequence") or 0))
                if stream_v2_enforced:
                    mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=item)
                    response_blocks = apply_stream_v2_event_to_response_blocks(
                        response_blocks,
                        event=mapped_event,
                        run_id=str(run.id),
                        seq=seq,
                        ts=None,
                        stage=stage,
                        payload=payload,
                        diagnostics=diagnostics,
                    )
                    if mapped_event in {"run.completed", "run.failed", "run.cancelled", "run.paused"}:
                        response_blocks = finalize_response_blocks(
                            response_blocks,
                            final_output=(payload or {}).get("final_output"),
                            run_id=str(run.id),
                            fallback_seq=seq,
                        )
                        saw_terminal = True
                    payload = dict(payload or {})
                    payload["response_blocks"] = response_blocks
                    assistant_text = extract_assistant_text_from_blocks(response_blocks)
                    if assistant_text:
                        payload["assistant_output_text"] = assistant_text
                    envelope = build_stream_v2_event(
                        seq=seq,
                        run_id=str(run.id),
                        event=mapped_event,
                        stage=stage,
                        payload=payload,
                        diagnostics=diagnostics,
                    )
                    yield f"data: {json.dumps(envelope, default=str)}\n\n"
                else:
                    event_name = str(item.get("event") or item.get("type") or "").strip()
                    if event_name == "run_status":
                        status = str((item.get("data") or {}).get("status") or "").strip().lower()
                        if status in _TERMINAL_STATUSES:
                            saw_terminal = True
                    yield f"data: {json.dumps(item, default=str)}\n\n"
                seq += 1

            status = _status_text(run.status)
            if status in _TERMINAL_STATUSES:
                if not saw_terminal:
                    if stream_v2_enforced:
                        terminal_envelope = _build_terminal_envelope(seq=seq, run=run)
                        terminal_payload = terminal_envelope.get("payload") if isinstance(terminal_envelope.get("payload"), dict) else {}
                        response_blocks = finalize_response_blocks(
                            response_blocks,
                            final_output=terminal_payload.get("final_output"),
                            run_id=str(run.id),
                            fallback_seq=seq,
                        )
                        terminal_payload = dict(terminal_payload)
                        terminal_payload["response_blocks"] = response_blocks
                        assistant_text = extract_assistant_text_from_blocks(response_blocks)
                        if assistant_text:
                            terminal_payload["assistant_output_text"] = assistant_text
                        terminal_envelope["payload"] = terminal_payload
                        yield f"data: {json.dumps(terminal_envelope, default=str)}\n\n"
                    else:
                        yield f"data: {json.dumps(_legacy_terminal_payload(run), default=str)}\n\n"
                return

        await asyncio.sleep(max(0.05, float(poll_interval_s)))
