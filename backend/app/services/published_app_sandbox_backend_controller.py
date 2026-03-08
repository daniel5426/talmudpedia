from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from app.services.published_app_sandbox_backend import (
    PublishedAppSandboxBackend,
    PublishedAppSandboxBackendError,
)


class ControllerSandboxBackend(PublishedAppSandboxBackend):
    backend_name = "controller"
    is_remote = True

    @staticmethod
    def _operation_timeout_seconds(env_name: str, fallback_seconds: float) -> float:
        raw = (os.getenv(env_name) or "").strip()
        if raw:
            try:
                parsed = float(raw)
                if parsed > 0:
                    return parsed
            except Exception:
                pass
        return float(fallback_seconds)

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.config.controller_token:
            headers["Authorization"] = f"Bearer {self.config.controller_token}"
        return headers

    @staticmethod
    def _preview_metadata_from_url(preview_url: str, *, base_path: str) -> dict[str, Any]:
        parsed = urlparse((preview_url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return {}
        upstream_base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return {
            "preview": {
                "upstream_base_url": upstream_base_url,
                "base_path": base_path,
                "upstream_path": parsed.path or "/",
            }
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self.config.controller_url:
            raise PublishedAppSandboxBackendError("Sandbox controller URL is not configured")
        url = f"{self.config.controller_url.rstrip('/')}{path}"
        timeout = httpx.Timeout(timeout_seconds or self.config.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_payload,
                )
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise PublishedAppSandboxBackendError(f"Sandbox controller request failed: {detail}") from exc
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise PublishedAppSandboxBackendError(
                f"Sandbox controller request failed ({response.status_code}): {detail}"
            )
        try:
            payload = response.json()
        except Exception as exc:
            raw_text = getattr(response, "text", "")
            if not raw_text:
                return {}
            raise PublishedAppSandboxBackendError(
                f"Sandbox controller returned invalid JSON for {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise PublishedAppSandboxBackendError(f"Sandbox controller returned invalid payload for {path}")
        return payload

    async def start_session(
        self,
        *,
        session_id: str,
        runtime_generation: int,
        tenant_id: str,
        app_id: str,
        user_id: str,
        revision_id: str,
        entry_file: str,
        files: Dict[str, str],
        idle_timeout_seconds: int,
        dependency_hash: str,
        draft_dev_token: str,
        preview_base_path: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "session_id": session_id,
            "runtime_generation": int(runtime_generation or 0),
            "tenant_id": tenant_id,
            "app_id": app_id,
            "user_id": user_id,
            "revision_id": revision_id,
            "entry_file": entry_file,
            "files": files,
            "idle_timeout_seconds": idle_timeout_seconds,
            "dependency_hash": dependency_hash,
            "draft_dev_token": draft_dev_token,
            "preview_base_path": preview_base_path,
        }
        start_timeout_seconds = self._operation_timeout_seconds(
            "APPS_DRAFT_DEV_CONTROLLER_START_TIMEOUT_SECONDS",
            max(float(self.config.request_timeout_seconds), 120.0),
        )
        response = await self._request(
            "POST",
            "/sessions/start",
            json_payload=payload,
            timeout_seconds=start_timeout_seconds,
        )
        result: Dict[str, Any] = {
            "sandbox_id": str(response.get("sandbox_id") or session_id),
            "status": str(response.get("status") or "running"),
            "runtime_backend": self.backend_name,
        }
        workspace_path = str(response.get("workspace_path") or "").strip()
        if workspace_path:
            result["workspace_path"] = workspace_path
        preview_url = str(response.get("preview_url") or "").strip()
        result["backend_metadata"] = self._preview_metadata_from_url(
            preview_url,
            base_path=preview_base_path,
        )
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
        preview_base_path: str | None = None,
    ) -> Dict[str, Any]:
        payload = {
            "entry_file": entry_file,
            "files": files,
            "idle_timeout_seconds": idle_timeout_seconds,
            "dependency_hash": dependency_hash,
            "install_dependencies": install_dependencies,
        }
        if preview_base_path:
            payload["preview_base_path"] = str(preview_base_path)
        sync_timeout_seconds = self._operation_timeout_seconds(
            "APPS_DRAFT_DEV_CONTROLLER_SYNC_TIMEOUT_SECONDS",
            max(float(self.config.request_timeout_seconds), 90.0),
        )
        response = await self._request(
            "PATCH",
            f"/sessions/{sandbox_id}/sync",
            json_payload=payload,
            timeout_seconds=sync_timeout_seconds,
        )
        return {
            "status": str(response.get("status") or "running"),
            "sandbox_id": str(response.get("sandbox_id") or sandbox_id),
            "runtime_backend": self.backend_name,
        }

    async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int) -> Dict[str, Any]:
        response = await self._request(
            "POST",
            f"/sessions/{sandbox_id}/heartbeat",
            json_payload={"idle_timeout_seconds": idle_timeout_seconds},
        )
        return {
            "status": str(response.get("status") or "running"),
            "sandbox_id": str(response.get("sandbox_id") or sandbox_id),
            "runtime_backend": self.backend_name,
        }

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        response = await self._request("POST", f"/sessions/{sandbox_id}/stop", json_payload={})
        return {
            "status": str(response.get("status") or "stopped"),
            "sandbox_id": str(response.get("sandbox_id") or sandbox_id),
            "runtime_backend": self.backend_name,
        }

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        return await self._request("GET", f"/sessions/{sandbox_id}/files", json_payload={"limit": int(limit)})

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        return await self._request("POST", f"/sessions/{sandbox_id}/files/read", json_payload={"path": path})

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
        return await self._request("POST", f"/sessions/{sandbox_id}/files/read-range", json_payload=payload)

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/search",
            json_payload={"query": query, "max_results": int(max_results)},
        )

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/workspace-index",
            json_payload={
                "limit": int(limit),
                "query": query,
                "max_symbols_per_file": int(max_symbols_per_file),
            },
        )

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/apply-patch",
            json_payload={
                "patch": patch,
                "options": options or {},
                "preconditions": preconditions or {},
            },
        )

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/write",
            json_payload={"path": path, "content": content},
        )

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        return await self._request("POST", f"/sessions/{sandbox_id}/files/delete", json_payload={"path": path})

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/files/rename",
            json_payload={"from_path": from_path, "to_path": to_path},
        )

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/sessions/{sandbox_id}/files/snapshot", json_payload={})

    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/stage/prepare",
            json_payload={"reset": bool(reset)},
        )

    async def snapshot_workspace(self, *, sandbox_id: str, workspace: str = "live") -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/stage/snapshot",
            json_payload={"workspace": workspace},
        )

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/sessions/{sandbox_id}/stage/promote", json_payload={})

    async def prepare_publish_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/sessions/{sandbox_id}/publish/prepare", json_payload={})

    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/publish/dependencies/prepare",
            json_payload={"workspace_path": workspace_path},
        )

    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        workspace_path: str | None = None,
    ) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/commands/run",
            json_payload={
                "command": command,
                "timeout_seconds": int(timeout_seconds),
                "max_output_bytes": int(max_output_bytes),
                "workspace_path": str(workspace_path).strip() if workspace_path else None,
            },
        )

    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/workspace/archive",
            json_payload={"workspace_path": workspace_path, "format": format},
        )

    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/workspace/sync",
            json_payload={"workspace_path": workspace_path, "files": files},
        )

    async def resolve_workspace_path(self, *, sandbox_id: str) -> str | None:
        _ = sandbox_id
        return None

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
        start_timeout_raw = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_OPENCODE_START_TIMEOUT_SECONDS") or "").strip()
        start_timeout_seconds = float(start_timeout_raw) if start_timeout_raw else max(float(self.config.request_timeout_seconds), 30.0)
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/opencode/start",
            json_payload={
                "run_id": run_id,
                "app_id": app_id,
                "workspace_path": workspace_path,
                "model_id": model_id,
                "prompt": prompt,
                "messages": messages,
            },
            timeout_seconds=start_timeout_seconds,
        )

    async def stream_opencode_events(self, *, sandbox_id: str, run_ref: str):
        if not self.config.controller_url:
            raise PublishedAppSandboxBackendError("Sandbox controller URL is not configured")
        url = f"{self.config.controller_url.rstrip('/')}/sessions/{sandbox_id}/opencode/events"
        stream_read_timeout_raw = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_STREAM_READ_TIMEOUT_SECONDS") or "").strip()
        stream_read_timeout_seconds = float(stream_read_timeout_raw) if stream_read_timeout_raw else None
        timeout = httpx.Timeout(
            connect=max(1.0, float(self.config.request_timeout_seconds)),
            write=max(1.0, float(self.config.request_timeout_seconds)),
            pool=max(1.0, float(self.config.request_timeout_seconds)),
            read=stream_read_timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url, headers=self._headers(), params={"run_ref": run_ref}) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace").strip()
                        raise PublishedAppSandboxBackendError(
                            f"Sandbox controller stream request failed ({response.status_code}): "
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
                            raise PublishedAppSandboxBackendError(
                                f"Sandbox controller event stream returned invalid JSON: {raw}"
                            ) from exc
                        if isinstance(parsed, dict):
                            yield parsed
        except PublishedAppSandboxBackendError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise PublishedAppSandboxBackendError(
                f"Sandbox controller stream request failed: {detail}"
            ) from exc

    async def cancel_opencode_run(self, *, sandbox_id: str, run_ref: str) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/opencode/cancel",
            json_payload={"run_ref": run_ref},
        )

    async def answer_opencode_question(
        self,
        *,
        sandbox_id: str,
        run_ref: str,
        question_id: str,
        answers: list[list[str]],
    ) -> Dict[str, Any]:
        question_timeout_raw = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_OPENCODE_QUESTION_TIMEOUT_SECONDS") or "").strip()
        question_timeout_seconds = float(question_timeout_raw) if question_timeout_raw else max(float(self.config.request_timeout_seconds), 45.0)
        return await self._request(
            "POST",
            f"/sessions/{sandbox_id}/opencode/question-answer",
            json_payload={"run_ref": run_ref, "question_id": question_id, "answers": answers},
            timeout_seconds=question_timeout_seconds,
        )
