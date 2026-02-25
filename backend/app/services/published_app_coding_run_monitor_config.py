from __future__ import annotations

import os
from typing import Any

from app.services.published_app_coding_pipeline_trace import (
    pipeline_trace,
    pipeline_trace_enabled,
    pipeline_trace_file_path,
)


def monitor_trace_enabled() -> bool:
    return pipeline_trace_enabled()


def monitor_trace_file_path() -> str:
    return pipeline_trace_file_path()


def monitor_trace(event: str, **fields: Any) -> None:
    pipeline_trace(event, pipeline="monitor", **fields)


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
