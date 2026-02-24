from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any


def monitor_trace_enabled() -> bool:
    raw = str(os.getenv("APPS_CODING_AGENT_DEBUG_TRACE_ENABLED", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def monitor_trace_file_path() -> str:
    return str(
        os.getenv("APPS_CODING_AGENT_DEBUG_TRACE_FILE", "/tmp/talmudpedia-coding-agent-trace.log")
        or "/tmp/talmudpedia-coding-agent-trace.log"
    ).strip()


def monitor_trace(event: str, **fields: Any) -> None:
    if not monitor_trace_enabled():
        return
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    try:
        rendered = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        rendered = str(payload)
    try:
        with open(monitor_trace_file_path(), "a", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    except Exception:
        pass


def monitor_inactivity_timeout_seconds() -> float:
    raw = (os.getenv("APPS_CODING_AGENT_MONITOR_INACTIVITY_TIMEOUT_SECONDS") or "").strip()
    try:
        parsed = float(raw) if raw else 45.0
    except Exception:
        parsed = 45.0
    return max(10.0, parsed)


def monitor_poll_interval_seconds(*, inactivity_timeout_seconds: float) -> float:
    raw = (os.getenv("APPS_CODING_AGENT_MONITOR_POLL_INTERVAL_SECONDS") or "").strip()
    try:
        parsed = float(raw) if raw else 1.0
    except Exception:
        parsed = 1.0
    return max(0.25, min(parsed, min(10.0, max(0.25, inactivity_timeout_seconds))))


def monitor_max_runtime_seconds() -> float:
    raw = (os.getenv("APPS_CODING_AGENT_MONITOR_MAX_RUNTIME_SECONDS") or "").strip()
    try:
        parsed = float(raw) if raw else 1200.0
    except Exception:
        parsed = 1200.0
    return max(60.0, parsed)


def monitor_status_probe_interval_seconds() -> float:
    raw = (os.getenv("APPS_CODING_AGENT_MONITOR_STATUS_PROBE_INTERVAL_SECONDS") or "").strip()
    try:
        parsed = float(raw) if raw else 0.5
    except Exception:
        parsed = 0.5
    return max(0.1, min(parsed, 10.0))
