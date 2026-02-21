from __future__ import annotations

import json
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
        controller_url = (
            (os.getenv("APPS_SANDBOX_CONTROLLER_URL") or "").strip()
            or (os.getenv("APPS_DRAFT_DEV_CONTROLLER_URL") or "").strip()
            or None
        )
        controller_token = (
            (os.getenv("APPS_SANDBOX_CONTROLLER_TOKEN") or "").strip()
            or (os.getenv("APPS_DRAFT_DEV_CONTROLLER_TOKEN") or "").strip()
            or None
        )
        return cls(
            PublishedAppDraftDevRuntimeClientConfig(
                controller_url=controller_url,
                controller_token=controller_token,
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
        workspace_path = str(response.get("workspace_path") or "").strip()
        result: Dict[str, Any] = {
            "sandbox_id": str(response.get("sandbox_id") or session_id),
            "preview_url": str(response.get("preview_url") or self._local_preview_url(session_id, draft_dev_token)),
            "status": str(response.get("status") or "running"),
        }
        if workspace_path:
            result["workspace_path"] = workspace_path
        return result

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

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.list_files(sandbox_id=sandbox_id, limit=limit)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox file listing requires embedded runtime or remote controller")
        response = await self._request("GET", f"/sessions/{sandbox_id}/files", json={"limit": int(limit)})
        return response

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.read_file(sandbox_id=sandbox_id, path=path)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox file reads require embedded runtime or remote controller")
        return await self._request("POST", f"/sessions/{sandbox_id}/files/read", json={"path": path})

    async def read_file_range(
        self,
        *,
        sandbox_id: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        context_before: int = 0,
        context_after: int = 0,
        max_bytes: int = 12000,
        with_line_numbers: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "path": path,
            "context_before": int(context_before or 0),
            "context_after": int(context_after or 0),
            "max_bytes": int(max_bytes or 12000),
            "with_line_numbers": bool(with_line_numbers),
        }
        if start_line is not None:
            payload["start_line"] = int(start_line)
        if end_line is not None:
            payload["end_line"] = int(end_line)

        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.read_file_range(sandbox_id=sandbox_id, **payload)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError(
                "Sandbox file range reads require embedded runtime or remote controller"
            )
        return await self._request("POST", f"/sessions/{sandbox_id}/files/read-range", json=payload)

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.search_code(sandbox_id=sandbox_id, query=query, max_results=max_results)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox search requires embedded runtime or remote controller")
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/search",
            json={"query": query, "max_results": int(max_results)},
        )

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "limit": int(limit),
            "query": query,
            "max_symbols_per_file": int(max_symbols_per_file),
        }
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.workspace_index(sandbox_id=sandbox_id, **payload)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError(
                "Sandbox workspace index requires embedded runtime or remote controller"
            )
        return await self._request("POST", f"/sessions/{sandbox_id}/files/workspace-index", json=payload)

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "patch": patch,
            "options": options or {},
            "preconditions": preconditions or {},
        }
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.apply_patch(
                        sandbox_id=sandbox_id,
                        patch=patch,
                        options=options or {},
                        preconditions=preconditions or {},
                    )
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError(
                "Sandbox patch apply requires embedded runtime or remote controller"
            )
        return await self._request("POST", f"/sessions/{sandbox_id}/files/apply-patch", json=payload)

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.write_file(sandbox_id=sandbox_id, path=path, content=content)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox file writes require embedded runtime or remote controller")
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/write",
            json={"path": path, "content": content},
        )

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.delete_file(sandbox_id=sandbox_id, path=path)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox file deletion requires embedded runtime or remote controller")
        return await self._request("POST", f"/sessions/{sandbox_id}/files/delete", json={"path": path})

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.rename_file(sandbox_id=sandbox_id, from_path=from_path, to_path=to_path)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox file rename requires embedded runtime or remote controller")
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/rename",
            json={"from_path": from_path, "to_path": to_path},
        )

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.snapshot_files(sandbox_id=sandbox_id)
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox snapshot requires embedded runtime or remote controller")
        return await self._request("GET", f"/sessions/{sandbox_id}/files/snapshot", json={})

    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
    ) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            if self._config.embedded_local_enabled:
                manager = get_local_draft_dev_runtime_manager()
                try:
                    return await manager.run_command(
                        sandbox_id=sandbox_id,
                        command=command,
                        timeout_seconds=timeout_seconds,
                        max_output_bytes=max_output_bytes,
                    )
                except LocalDraftDevRuntimeError as exc:
                    raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
            raise PublishedAppDraftDevRuntimeClientError("Sandbox command execution requires embedded runtime or remote controller")
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/commands/run",
            json={
                "command": command,
                "timeout_seconds": int(timeout_seconds),
                "max_output_bytes": int(max_output_bytes),
            },
        )

    async def resolve_local_workspace_path(self, *, sandbox_id: str) -> str | None:
        if self.is_remote_enabled or not self._config.embedded_local_enabled:
            return None
        manager = get_local_draft_dev_runtime_manager()
        return await manager.resolve_project_dir(sandbox_id=sandbox_id)

    async def start_opencode_run(
        self,
        *,
        sandbox_id: str,
        run_id: str,
        app_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        messages: list[dict[str, str]],
    ) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            raise PublishedAppDraftDevRuntimeClientError(
                "OpenCode sandbox run requires APPS_SANDBOX_CONTROLLER_URL or APPS_DRAFT_DEV_CONTROLLER_URL"
            )
        start_timeout_raw = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_OPENCODE_START_TIMEOUT_SECONDS") or "").strip()
        start_timeout_seconds: float | None = None
        if start_timeout_raw:
            try:
                parsed = float(start_timeout_raw)
                if parsed > 0:
                    start_timeout_seconds = parsed
            except Exception:
                start_timeout_seconds = None
        if start_timeout_seconds is None:
            start_timeout_seconds = max(float(self._config.request_timeout_seconds), 30.0)
        payload = {
            "run_id": run_id,
            "app_id": app_id,
            "workspace_path": workspace_path,
            "model_id": model_id,
            "prompt": prompt,
            "messages": messages,
        }
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/opencode/start",
            json=payload,
            timeout_seconds=start_timeout_seconds,
        )

    async def stream_opencode_events(
        self,
        *,
        sandbox_id: str,
        run_ref: str,
    ):
        if not self._config.controller_url:
            raise PublishedAppDraftDevRuntimeClientError("Draft dev controller URL is not configured")
        url = f"{self._config.controller_url.rstrip('/')}/sessions/{sandbox_id}/opencode/events"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._config.controller_token:
            headers["Authorization"] = f"Bearer {self._config.controller_token}"
        stream_read_timeout_raw = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_STREAM_READ_TIMEOUT_SECONDS") or "").strip()
        stream_read_timeout_seconds: float | None = None
        if stream_read_timeout_raw:
            try:
                parsed = float(stream_read_timeout_raw)
                stream_read_timeout_seconds = parsed if parsed > 0 else None
            except Exception:
                stream_read_timeout_seconds = None
        timeout = httpx.Timeout(
            connect=max(1.0, float(self._config.request_timeout_seconds)),
            write=max(1.0, float(self._config.request_timeout_seconds)),
            pool=max(1.0, float(self._config.request_timeout_seconds)),
            read=stream_read_timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url, headers=headers, params={"run_ref": run_ref}) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace").strip()
                        raise PublishedAppDraftDevRuntimeClientError(
                            f"Draft dev controller stream request failed ({response.status_code}): "
                            f"{body or response.reason_phrase}"
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
                            raise PublishedAppDraftDevRuntimeClientError(
                                f"Draft dev controller event stream returned invalid JSON: {raw}"
                            ) from exc
                        if isinstance(parsed, dict):
                            yield parsed
        except PublishedAppDraftDevRuntimeClientError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise PublishedAppDraftDevRuntimeClientError(f"Draft dev controller stream request failed: {detail}") from exc

    async def cancel_opencode_run(self, *, sandbox_id: str, run_ref: str) -> Dict[str, Any]:
        if not self.is_remote_enabled:
            raise PublishedAppDraftDevRuntimeClientError(
                "OpenCode sandbox run requires APPS_SANDBOX_CONTROLLER_URL or APPS_DRAFT_DEV_CONTROLLER_URL"
            )
        payload = {"run_ref": run_ref}
        return await self._request("POST", f"/sessions/{sandbox_id}/opencode/cancel", json=payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> Dict[str, Any]:
        if not self._config.controller_url:
            raise PublishedAppDraftDevRuntimeClientError("Draft dev controller URL is not configured")
        base_url = self._config.controller_url.rstrip("/")
        url = f"{base_url}{path}"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._config.controller_token:
            headers["Authorization"] = f"Bearer {self._config.controller_token}"

        effective_timeout = float(timeout_seconds) if timeout_seconds is not None else float(self._config.request_timeout_seconds)
        if effective_timeout <= 0:
            effective_timeout = float(self._config.request_timeout_seconds)
        timeout = httpx.Timeout(effective_timeout)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, json=json)
        except Exception as exc:
            detail = str(exc).strip()
            if not detail:
                detail = exc.__class__.__name__
            raise PublishedAppDraftDevRuntimeClientError(f"Draft dev controller request failed: {detail}") from exc

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
