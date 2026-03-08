from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
from typing import Any

from app.services.apps_builder_trace import apps_builder_trace

_DEFAULT_TRACE_FILE = "/tmp/talmudpedia-coding-agent-pipeline-trace.jsonl"
_WRITE_LOCK = threading.Lock()


def pipeline_trace_enabled() -> bool:
    raw = os.getenv("APPS_CODING_AGENT_PIPELINE_TRACE_ENABLED")
    if raw is None or not str(raw).strip():
        raw = os.getenv("APPS_CODING_AGENT_DEBUG_TRACE_ENABLED", "1")
    normalized = str(raw or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def pipeline_trace_file_path() -> str:
    raw = os.getenv("APPS_CODING_AGENT_PIPELINE_TRACE_FILE")
    if raw is None or not str(raw).strip():
        raw = os.getenv("APPS_CODING_AGENT_DEBUG_TRACE_FILE", _DEFAULT_TRACE_FILE)
    path = str(raw or "").strip()
    return path or _DEFAULT_TRACE_FILE


def pipeline_trace(event: str, *, pipeline: str, **fields: Any) -> None:
    if not pipeline_trace_enabled():
        return

    apps_builder_trace(
        event,
        domain=f"coding_agent.{str(pipeline or '').strip() or 'unknown'}",
        **fields,
    )

    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event or "").strip() or "unknown",
        "pipeline": str(pipeline or "").strip() or "unknown",
        "pid": os.getpid(),
        **fields,
    }

    try:
        rendered = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        rendered = str(payload)

    try:
        with _WRITE_LOCK:
            with open(pipeline_trace_file_path(), "a", encoding="utf-8") as handle:
                handle.write(rendered + "\n")
    except Exception:
        # Logging must never impact run execution.
        pass
