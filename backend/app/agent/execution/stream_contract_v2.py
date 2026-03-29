from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from app.agent.execution.types import ExecutionEvent


def build_stream_v2_event(
    *,
    seq: int,
    run_id: str,
    event: str,
    stage: str,
    payload: Dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return {
        "version": "run-stream.v2",
        "seq": int(seq),
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "run_id": str(run_id),
        "stage": stage,
        "payload": payload or {},
        "diagnostics": diagnostics or [],
    }


def normalize_filtered_event_to_v2(
    *,
    raw_event: Dict[str, Any] | ExecutionEvent,
) -> Tuple[str, str, Dict[str, Any], list[dict[str, Any]]]:
    if isinstance(raw_event, ExecutionEvent):
        normalized_raw_event: Dict[str, Any] = raw_event.model_dump()
    else:
        normalized_raw_event = dict(raw_event or {})

    raw_event = normalized_raw_event
    event_name = str(raw_event.get("event") or "").strip()
    event_type = str(raw_event.get("type") or "").strip()
    data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}

    if event_name == "token" or event_type == "token":
        content = raw_event.get("content")
        if content is None:
            content = data.get("content")
        return "assistant.delta", "assistant", {"content": str(content or "")}, []

    if event_name == "on_tool_start":
        return (
            "tool.started",
            "tool",
            {
                "tool": raw_event.get("name"),
                "span_id": raw_event.get("span_id"),
                "input": data.get("input"),
                "message": data.get("message"),
                "tool_slug": data.get("tool_slug"),
                "action": data.get("action"),
                "display_name": data.get("display_name"),
                "summary": data.get("summary"),
                "renderer_kind": data.get("renderer_kind"),
            },
            [],
        )

    if event_name == "on_tool_end":
        output = data.get("output") if isinstance(data.get("output"), dict) else None
        return (
            "tool.completed",
            "tool",
            {
                "tool": raw_event.get("name"),
                "span_id": raw_event.get("span_id"),
                "output": data.get("output"),
                "tool_slug": data.get("tool_slug"),
                "action": data.get("action"),
                "display_name": data.get("display_name"),
                "summary": data.get("summary"),
                "renderer_kind": data.get("renderer_kind"),
                "output_kind": output.get("kind") if isinstance(output, dict) else None,
            },
            [],
        )

    if event_name == "tool.failed":
        return (
            "tool.failed",
            "tool",
            {
                "tool": raw_event.get("name"),
                "span_id": raw_event.get("span_id"),
                "input": data.get("input"),
                "error": data.get("error"),
                "tool_slug": data.get("tool_slug"),
                "action": data.get("action"),
                "display_name": data.get("display_name"),
                "summary": data.get("summary"),
                "renderer_kind": data.get("renderer_kind"),
            },
            [{"message": str(data.get("error") or "Tool failed")}],
        )

    if event_name == "run_status":
        status = str(data.get("status") or "").strip().lower()
        mapped = {
            "completed": "run.completed",
            "failed": "run.failed",
            "cancelled": "run.cancelled",
            "paused": "run.paused",
            "running": "run.accepted",
            "queued": "run.accepted",
        }.get(status, "run.accepted")
        diagnostics: list[dict[str, Any]] = []
        if mapped == "run.failed" and data.get("error"):
            diagnostics.append({"message": str(data.get("error"))})
        return (
            mapped,
            "run",
            {
                "status": status or None,
                "next": data.get("next"),
                "next_nodes": data.get("next_nodes"),
                "final_output": data.get("final_output"),
                "context_status": data.get("context_status"),
            },
            diagnostics,
        )

    if event_name == "context.status":
        return (
            "context.status",
            "context",
            {
                "context_status": data.get("context_status"),
            },
            [],
        )

    if event_name == "error" or event_type == "error":
        err = (
            raw_event.get("error")
            or data.get("error")
            or "Runtime error"
        )
        return (
            "runtime.error",
            "system",
            {"error": str(err)},
            [{"message": str(err)}],
        )

    if event_type == "reasoning":
        return "reasoning.update", "reasoning", dict(data or {}), []

    passthrough_name = event_name or event_type or "system.event"
    return (
        passthrough_name,
        "system",
        {
            "name": raw_event.get("name"),
            "span_id": raw_event.get("span_id"),
            "data": data,
            "metadata": raw_event.get("metadata") if isinstance(raw_event.get("metadata"), dict) else {},
        },
        [],
    )
