from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any

import httpx


@dataclass(frozen=True)
class CloudflareDispatchResult:
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    stdout_excerpt: str
    stderr_excerpt: str
    duration_ms: int | None
    worker_id: str | None
    sandbox_session_id: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    runtime_metadata: dict[str, Any] = field(default_factory=dict)


class CloudflareDispatchClient:
    async def execute(self, payload: dict[str, Any]) -> CloudflareDispatchResult:
        base_url = str(os.getenv("ARTIFACT_CF_DISPATCH_BASE_URL") or "").strip().rstrip("/")
        token = str(os.getenv("ARTIFACT_CF_DISPATCH_TOKEN") or "").strip()
        if not base_url:
            raise RuntimeError("ARTIFACT_CF_DISPATCH_BASE_URL is required")
        async with httpx.AsyncClient(timeout=float(os.getenv("ARTIFACT_CF_DISPATCH_TIMEOUT_SECONDS") or "60")) as client:
            response = await client.post(
                f"{base_url}/execute",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError("Dispatch response is invalid")
        return CloudflareDispatchResult(
            status=str(data.get("status") or "failed"),
            result=data.get("result") if isinstance(data.get("result"), dict) else data.get("result"),
            error=data.get("error") if isinstance(data.get("error"), dict) else None,
            stdout_excerpt=str(data.get("stdout_excerpt") or ""),
            stderr_excerpt=str(data.get("stderr_excerpt") or ""),
            duration_ms=int(data.get("duration_ms") or 0) if data.get("duration_ms") is not None else None,
            worker_id=str(data.get("worker_id") or "") or None,
            sandbox_session_id=str(data.get("dispatch_request_id") or "") or None,
            events=list(data.get("events") or []),
            runtime_metadata=dict(data.get("runtime_metadata") or {}),
        )

    async def cancel(self, dispatch_request_id: str) -> None:
        base_url = str(os.getenv("ARTIFACT_CF_DISPATCH_BASE_URL") or "").strip().rstrip("/")
        token = str(os.getenv("ARTIFACT_CF_DISPATCH_TOKEN") or "").strip()
        if not base_url:
            return
        async with httpx.AsyncClient(timeout=float(os.getenv("ARTIFACT_CF_DISPATCH_TIMEOUT_SECONDS") or "30")) as client:
            response = await client.post(
                f"{base_url}/cancel",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                json={"dispatch_request_id": dispatch_request_id},
            )
        response.raise_for_status()
