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


class CloudflareDispatchHTTPError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        response_text: str,
        response_json: dict[str, Any] | None,
        url: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.response_json = response_json
        self.url = url

    def to_error_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": "CLOUDFLARE_DISPATCH_HTTP_ERROR",
            "message": str(self),
            "http_status": self.status_code,
            "url": self.url,
            "response_text": self.response_text,
        }
        if isinstance(self.response_json, dict):
            payload["response_json"] = self.response_json
            detail = self.response_json.get("detail")
            if isinstance(detail, dict):
                payload["dispatch_detail"] = detail
        return payload


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
        try:
            body = response.json()
        except Exception:
            body = None
        if response.status_code >= 400:
            response_text = response.text
            message = f"Dispatch worker returned HTTP {response.status_code} for {response.request.url}"
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, dict):
                    detail_message = detail.get("message") or detail.get("error") or detail.get("code")
                    if detail_message:
                        message = f"{message}: {detail_message}"
                elif isinstance(detail, str) and detail.strip():
                    message = f"{message}: {detail.strip()}"
            raise CloudflareDispatchHTTPError(
                status_code=response.status_code,
                message=message,
                response_text=response_text,
                response_json=body if isinstance(body, dict) else None,
                url=str(response.request.url),
            )
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
