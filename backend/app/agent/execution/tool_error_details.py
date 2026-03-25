from __future__ import annotations

from typing import Any

import httpx


def _truncate_text(value: Any, limit: int = 2000) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


class ArtifactToolExecutionError(RuntimeError):
    def __init__(
        self,
        *,
        run_id: str,
        error_payload: dict[str, Any] | None,
        stdout_excerpt: str | None = None,
        stderr_excerpt: str | None = None,
    ) -> None:
        message = str((error_payload or {}).get("message") or "Artifact-backed tool execution failed")
        super().__init__(message)
        self.run_id = run_id
        self.error_payload = dict(error_payload or {})
        self.stdout_excerpt = _truncate_text(stdout_excerpt)
        self.stderr_excerpt = _truncate_text(stderr_excerpt)


def build_tool_exception_details(exc: Exception) -> dict[str, Any]:
    details: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": str(exc),
    }

    if isinstance(exc, ArtifactToolExecutionError):
        details["artifact_run_id"] = exc.run_id
        details["error_payload"] = exc.error_payload
        if exc.stdout_excerpt:
            details["stdout_excerpt"] = exc.stdout_excerpt
        if exc.stderr_excerpt:
            details["stderr_excerpt"] = exc.stderr_excerpt
        return details

    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        request = exc.request
        details["http_status"] = response.status_code
        details["url"] = str(request.url)
        details["method"] = str(request.method)
        details["response_text"] = _truncate_text(response.text)
        content_type = str(response.headers.get("content-type") or "")
        if "application/json" in content_type:
            try:
                payload = response.json()
            except Exception:
                payload = None
            if isinstance(payload, dict):
                details["response_json"] = payload
        return details

    return details
