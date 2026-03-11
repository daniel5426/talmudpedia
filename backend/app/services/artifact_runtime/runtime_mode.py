from __future__ import annotations

import os


RUNTIME_MODE_WORKERS_FOR_PLATFORMS = "workers_for_platforms"
RUNTIME_MODE_STANDARD_WORKER_TEST = "standard_worker_test"


def artifact_cloudflare_runtime_mode() -> str:
    raw = str(os.getenv("ARTIFACT_CF_RUNTIME_MODE") or "").strip().lower()
    if raw == RUNTIME_MODE_STANDARD_WORKER_TEST:
        return RUNTIME_MODE_STANDARD_WORKER_TEST
    return RUNTIME_MODE_WORKERS_FOR_PLATFORMS

