from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

import httpx


class OpenCodeServerClientError(Exception):
    pass


@dataclass(frozen=True)
class OpenCodeServerClientConfig:
    enabled: bool
    base_url: str | None
    api_key: str | None
    request_timeout_seconds: float
    connect_timeout_seconds: float
    health_cache_seconds: int


class OpenCodeServerClient:
    def __init__(self, config: OpenCodeServerClientConfig):
        self._config = config
        self._health_checked_at: datetime | None = None
        self._health_ok = False

    @classmethod
    def from_env(cls) -> "OpenCodeServerClient":
        enabled = (os.getenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "0").strip().lower() not in {"0", "false", "off", "no"})
        base_url = (os.getenv("APPS_CODING_AGENT_OPENCODE_BASE_URL") or "").strip() or None
        api_key = (os.getenv("APPS_CODING_AGENT_OPENCODE_API_KEY") or "").strip() or None
        request_timeout = float(os.getenv("APPS_CODING_AGENT_OPENCODE_REQUEST_TIMEOUT_SECONDS", "20").strip())
        connect_timeout = float(os.getenv("APPS_CODING_AGENT_OPENCODE_CONNECT_TIMEOUT_SECONDS", "5").strip())
        health_cache_seconds = int(os.getenv("APPS_CODING_AGENT_OPENCODE_HEALTH_CACHE_SECONDS", "15").strip())
        return cls(
            OpenCodeServerClientConfig(
                enabled=enabled,
                base_url=base_url,
                api_key=api_key,
                request_timeout_seconds=max(3.0, request_timeout),
                connect_timeout_seconds=max(1.0, connect_timeout),
                health_cache_seconds=max(3, health_cache_seconds),
            )
        )

    @property
    def is_enabled(self) -> bool:
        return bool(self._config.enabled and self._config.base_url)

    async def ensure_healthy(self, *, force: bool = False) -> None:
        if not self.is_enabled:
            raise OpenCodeServerClientError(
                "OpenCode engine is disabled or missing APPS_CODING_AGENT_OPENCODE_BASE_URL."
            )

        now = datetime.now(timezone.utc)
        if not force and self._health_checked_at is not None:
            if now - self._health_checked_at <= timedelta(seconds=self._config.health_cache_seconds):
                if self._health_ok:
                    return
                raise OpenCodeServerClientError("OpenCode engine health check is currently failing.")

        await self._request("GET", "/health", json_payload={}, retries=1)
        self._health_checked_at = now
        self._health_ok = True

    async def start_run(
        self,
        *,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        payload = {
            "run_id": run_id,
            "app_id": app_id,
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "model_id": model_id,
            "prompt": prompt,
            "messages": messages,
            "ephemeral": True,
        }
        response = await self._request("POST", "/v1/runs", json_payload=payload, retries=0)
        run_ref = response.get("run_ref") or response.get("id")
        if not run_ref:
            raise OpenCodeServerClientError("OpenCode run start response is missing run_ref.")
        return str(run_ref)

    async def stream_run_events(self, *, run_ref: str) -> AsyncGenerator[dict[str, Any], None]:
        if not self._config.base_url:
            raise OpenCodeServerClientError("OpenCode base URL is not configured.")

        url = f"{self._config.base_url.rstrip('/')}/v1/runs/{run_ref}/events"
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace").strip()
                        raise OpenCodeServerClientError(
                            f"OpenCode stream request failed ({response.status_code}): {body or response.reason_phrase}"
                        )
                    async for line in response.aiter_lines():
                        raw = (line or "").strip()
                        if not raw or raw.startswith(":"):
                            continue
                        if raw.startswith("data:"):
                            raw = raw[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            parsed = json.loads(raw)
                        except Exception as exc:
                            raise OpenCodeServerClientError(f"OpenCode event stream returned invalid JSON: {raw}") from exc
                        if isinstance(parsed, dict):
                            yield parsed
        except OpenCodeServerClientError:
            raise
        except Exception as exc:
            raise OpenCodeServerClientError(f"OpenCode stream request failed: {exc}") from exc

    async def cancel_run(self, *, run_ref: str) -> bool:
        response = await self._request("POST", f"/v1/runs/{run_ref}/cancel", json_payload={}, retries=0)
        cancelled = response.get("cancelled")
        if isinstance(cancelled, bool):
            return cancelled
        return True

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any],
        retries: int,
    ) -> dict[str, Any]:
        if not self._config.base_url:
            raise OpenCodeServerClientError("OpenCode base URL is not configured.")

        url = f"{self._config.base_url.rstrip('/')}{path}"
        headers = self._headers()
        attempts = max(0, retries) + 1
        last_error: Exception | None = None

        for _ in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self._timeout()) as client:
                    response = await client.request(method, url, headers=headers, json=json_payload)
                if response.status_code >= 400:
                    body = response.text.strip()
                    raise OpenCodeServerClientError(
                        f"OpenCode request failed ({response.status_code}): {body or response.reason_phrase}"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise OpenCodeServerClientError("OpenCode server returned invalid JSON payload.")
                return payload
            except OpenCodeServerClientError as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc

        raise OpenCodeServerClientError(f"OpenCode request failed: {last_error}")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            timeout=self._config.request_timeout_seconds,
            connect=self._config.connect_timeout_seconds,
        )
