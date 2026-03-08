from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
from typing import Any

_DEFAULT_TRACE_FILE = "/tmp/talmudpedia-apps-builder-events.jsonl"
_WRITE_LOCK = threading.Lock()


def apps_builder_trace_enabled() -> bool:
    raw = os.getenv("APPS_BUILDER_TRACE_ENABLED")
    if raw is None or not str(raw).strip():
        raw = "1"
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def apps_builder_trace_file_path() -> str:
    raw = os.getenv("APPS_BUILDER_TRACE_FILE", _DEFAULT_TRACE_FILE)
    path = str(raw or "").strip()
    return path or _DEFAULT_TRACE_FILE


def apps_builder_trace(event: str, *, domain: str, **fields: Any) -> None:
    if not apps_builder_trace_enabled():
        return

    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event or "").strip() or "unknown",
        "domain": str(domain or "").strip() or "unknown",
        "pid": os.getpid(),
        **fields,
    }

    try:
        rendered = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        rendered = str(payload)

    try:
        with _WRITE_LOCK:
            with open(apps_builder_trace_file_path(), "a", encoding="utf-8") as handle:
                handle.write(rendered + "\n")
    except Exception:
        # Tracing must never block request or sandbox execution paths.
        pass
