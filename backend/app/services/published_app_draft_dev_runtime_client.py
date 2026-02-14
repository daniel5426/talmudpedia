from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from app.services.published_app_draft_dev_local_runtime import (
    LocalDraftDevRuntimeError,
    get_local_draft_dev_runtime_manager,
)


class PublishedAppDraftDevRuntimeClientError(Exception):
    pass


@dataclass(frozen=True)
class PublishedAppDraftDevRuntimeClientConfig:
    controller_url: Optional[str]
    controller_token: Optional[str]
    request_timeout_seconds: int
    local_preview_base_url: str
    embedded_local_enabled: bool


class PublishedAppDraftDevRuntimeClient:
    def __init__(self, config: PublishedAppDraftDevRuntimeClientConfig):
        self._config = config

    @classmethod
    def from_env(cls) -> "PublishedAppDraftDevRuntimeClient":
        timeout_seconds = int(os.getenv("APPS_DRAFT_DEV_CONTROLLER_TIMEOUT_SECONDS", "15"))
        return cls(
            PublishedAppDraftDevRuntimeClientConfig(
                controller_url=(os.getenv("APPS_DRAFT_DEV_CONTROLLER_URL") or "").strip() or None,
                controller_token=(os.getenv("APPS_DRAFT_DEV_CONTROLLER_TOKEN") or "").strip() or None,
                request_timeout_seconds=max(3, timeout_seconds),
                local_preview_base_url=(os.getenv("APPS_DRAFT_DEV_PREVIEW_BASE_URL") or "http://127.0.0.1:5173").strip(),
                embedded_local_enabled=(os.getenv("APPS_DRAFT_DEV_EMBEDDED_LOCAL_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}),
            )
        )

    def _local_preview_url(self, sandbox_id: str, draft_dev_token: str) -> str:
        base = self._config.local_preview_base_url.rstrip("/")
        query = urlencode({"draft_dev_token": draft_dev_token})
        return f"{base}/sandbox/{sandbox_id}/?{query}"

    async def _assert_local_preview_reachable(self) -> None:
        base = self._config.local_preview_base_url.rstrip("/")
        if not base:
            raise PublishedAppDraftDevRuntimeClientError(
                "Draft dev preview base URL is not configured. "
                "Set APPS_DRAFT_DEV_PREVIEW_BASE_URL or APPS_DRAFT_DEV_CONTROLLER_URL."
            )
        timeout = httpx.Timeout(min(self._config.request_timeout_seconds, 5))
        probe_url = f"{base}/"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(probe_url)
        except Exception as exc:
            raise PublishedAppDraftDevRuntimeClientError(
                f"Draft dev local preview endpoint is unreachable at {probe_url}. "
                "Start the draft dev sandbox/controller or configure APPS_DRAFT_DEV_CONTROLLER_URL. "
                f"Connection error: {exc}"
            ) from exc
        if response.status_code >= 500:
            raise PublishedAppDraftDevRuntimeClientError(
                f"Draft dev local preview endpoint is unhealthy at {probe_url} "
                f"(status {response.status_code})."
            )

    @property
    def is_remote_enabled(self) -> bool:
        return bool(self._config.controller_url)

    async def start_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        app_id: str,
        user_id: str,
        revision_id: str,
        entry_file: str,
        files: Dict[str, str],
        idle_timeout_seconds: int,
        dependency_hash: str,
        draft_dev_token: str,
    ) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.start_session(
                        session_id=session_id,
                        files=files,
                        dependency_hash=dependency_hash,
                        draft_dev_token=draft_dev_token,
                    )
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

            await self._assert_local_preview_reachable()
            return {
                "sandbox_id": session_id,
                "preview_url": self._local_preview_url(session_id, draft_dev_token),
                "status": "running",
            }

        payload: Dict[str, Any] = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "app_id": app_id,
            "user_id": user_id,
            "revision_id": revision_id,
            "entry_file": entry_file,
            "files": files,
            "idle_timeout_seconds": idle_timeout_seconds,
            "dependency_hash": dependency_hash,
            "draft_dev_token": draft_dev_token,
        }
        response = await self._request("POST", "/sessions/start", json=payload)
        return {
            "sandbox_id": str(response.get("sandbox_id") or session_id),
            "preview_url": str(response.get("preview_url") or self._local_preview_url(session_id, draft_dev_token)),
            "status": str(response.get("status") or "running"),
        }

    async def sync_session(
        self,
        *,
        sandbox_id: str,
        entry_file: str,
        files: Dict[str, str],
        idle_timeout_seconds: int,
        dependency_hash: str,
        install_dependencies: bool,
    ) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.sync_session(
                        sandbox_id=sandbox_id,
                        files=files,
                        dependency_hash=dependency_hash,
                        install_dependencies=install_dependencies,
                    )
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            return {"status": "running", "sandbox_id": sandbox_id}

        payload: Dict[str, Any] = {
            "entry_file": entry_file,
            "files": files,
            "idle_timeout_seconds": idle_timeout_seconds,
            "dependency_hash": dependency_hash,
            "install_dependencies": install_dependencies,
        }
        response = await self._request("PATCH", f"/sessions/{sandbox_id}/sync", json=payload)
        return {
            "status": str(response.get("status") or "running"),
            "sandbox_id": str(response.get("sandbox_id") or sandbox_id),
        }

    async def heartbeat_session(
        self,
        *,
        sandbox_id: str,
        idle_timeout_seconds: int,
    ) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.heartbeat_session(sandbox_id=sandbox_id)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            return {"status": "running", "sandbox_id": sandbox_id}

        payload = {"idle_timeout_seconds": idle_timeout_seconds}
        response = await self._request("POST", f"/sessions/{sandbox_id}/heartbeat", json=payload)
        return {
            "status": str(response.get("status") or "running"),
            "sandbox_id": str(response.get("sandbox_id") or sandbox_id),
        }

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.stop_session(sandbox_id=sandbox_id)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            return {"status": "stopped", "sandbox_id": sandbox_id}
        response = await self._request("POST", f"/sessions/{sandbox_id}/stop", json={})
        return {
            "status": str(response.get("status") or "stopped"),
            "sandbox_id": str(response.get("sandbox_id") or sandbox_id),
        }

    async def _request(self, method: str, path: str, *, json: Dict[str, Any]) -> Dict[str, Any]:
        if not self._config.controller_url:
            raise PublishedAppDraftDevRuntimeClientError("Draft dev controller URL is not configured")
        base_url = self._config.controller_url.rstrip("/")
        url = f"{base_url}{path}"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._config.controller_token:
            headers["Authorization"] = f"Bearer {self._config.controller_token}"

        timeout = httpx.Timeout(self._config.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, json=json)
        except Exception as exc:
            raise PublishedAppDraftDevRuntimeClientError(f"Draft dev controller request failed: {exc}") from exc

        if response.status_code >= 400:
            body = response.text.strip()
            raise PublishedAppDraftDevRuntimeClientError(
                f"Draft dev controller request failed ({response.status_code}): {body or response.reason_phrase}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise PublishedAppDraftDevRuntimeClientError("Draft dev controller returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise PublishedAppDraftDevRuntimeClientError("Draft dev controller returned invalid payload")
        return payload
