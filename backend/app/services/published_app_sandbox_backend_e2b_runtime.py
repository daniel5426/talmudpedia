from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Any, Dict

from app.services.opencode_server_launch import build_official_opencode_bootstrap_command
from app.services.published_app_sandbox_backend import (
    PublishedAppOpenCodeEndpoint,
    PublishedAppSandboxBackendError,
)

try:
    from e2b import AsyncSandbox
    from e2b.sandbox.sandbox_api import SandboxQuery
except Exception:  # pragma: no cover - import failure is handled at runtime
    AsyncSandbox = None
    SandboxQuery = None


@dataclass
class _E2BProcessState:
    preview_pid: int | None = None
    preview_base_path: str = "/"
    opencode_pid: int | None = None


@dataclass(frozen=True)
class _E2BSandboxRecord:
    sandbox_id: str
    metadata: dict[str, Any]


_E2B_PROCESS_STATE: dict[str, _E2BProcessState] = {}
logger = logging.getLogger(__name__)


class E2BSandboxRuntimeMixin:
    async def _read_log_excerpt(self, sandbox, *, log_path: str, max_chars: int = 1600) -> str:
        try:
            content = await sandbox.files.read(log_path)
        except Exception:
            return ""
        text = str(content or "").strip()
        if len(text) > max(200, int(max_chars or 1600)):
            text = text[-int(max_chars or 1600):]
        return text

    @staticmethod
    def _metadata_generation(metadata: dict[str, Any] | None) -> int:
        try:
            return int((metadata or {}).get("runtime_generation") or 0)
        except Exception:
            return 0

    async def _list_session_sandboxes(self, *, session_id: str) -> list[_E2BSandboxRecord]:
        self._require_sdk()
        try:
            paginator = AsyncSandbox.list(
                query=SandboxQuery(metadata={"session_id": str(session_id)}),
                limit=50,
            )
            items = await paginator.next_items()
        except Exception as exc:
            raise PublishedAppSandboxBackendError(
                f"Failed to list E2B sandboxes for session `{session_id}`: {exc}"
            ) from exc
        records: list[_E2BSandboxRecord] = []
        for item in items or []:
            sandbox_id = str(getattr(item, "sandbox_id", "") or "").strip()
            if sandbox_id:
                metadata = getattr(item, "metadata", None)
                records.append(
                    _E2BSandboxRecord(
                        sandbox_id=sandbox_id,
                        metadata=dict(metadata) if isinstance(metadata, dict) else {},
                    )
                )
        return records

    async def _kill_sandbox_id(self, sandbox_id: str) -> None:
        try:
            sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
            await sandbox.kill()
        except Exception:
            return
        _E2B_PROCESS_STATE.pop(sandbox_id, None)

    async def _kill_session_sandboxes(self, *, session_id: str, exclude_sandbox_id: str | None = None) -> list[str]:
        removed: list[str] = []
        for record in await self._list_session_sandboxes(session_id=session_id):
            sandbox_id = record.sandbox_id
            if exclude_sandbox_id and sandbox_id == str(exclude_sandbox_id):
                continue
            await self._kill_sandbox_id(sandbox_id)
            removed.append(sandbox_id)
        return removed

    async def reconcile_session_scope(
        self,
        *,
        session_id: str,
        expected_sandbox_id: str | None,
        runtime_generation: int | None,
    ) -> Dict[str, Any]:
        expected_generation = int(runtime_generation or 0)
        removed: list[str] = []
        for record in await self._list_session_sandboxes(session_id=session_id):
            same_sandbox = expected_sandbox_id and record.sandbox_id == str(expected_sandbox_id)
            same_generation = self._metadata_generation(record.metadata) == expected_generation
            if same_sandbox and same_generation:
                continue
            await self._kill_sandbox_id(record.sandbox_id)
            removed.append(record.sandbox_id)
        return {
            "session_id": session_id,
            "kept_sandbox_id": str(expected_sandbox_id or "").strip() or None,
            "runtime_generation": expected_generation,
            "removed_sandbox_ids": removed,
        }

    async def sweep_remote_sessions(
        self,
        *,
        active_sessions: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        self._require_sdk()
        try:
            paginator = AsyncSandbox.list(
                query=SandboxQuery(metadata={"runtime_profile": "app_builder_preview"}),
                limit=200,
            )
            items = await paginator.next_items()
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Failed to list E2B app-builder sandboxes: {exc}") from exc

        expected_sessions: dict[str, dict[str, Any]] = {}
        for session_id, payload in dict(active_sessions or {}).items():
            normalized_session_id = str(session_id or "").strip()
            if not normalized_session_id:
                continue
            expected_sessions[normalized_session_id] = {
                "sandbox_id": str((payload or {}).get("sandbox_id") or "").strip() or None,
                "runtime_generation": int((payload or {}).get("runtime_generation") or 0),
            }

        removed: list[str] = []
        checked = 0
        for item in items or []:
            sandbox_id = str(getattr(item, "sandbox_id", "") or "").strip()
            metadata = getattr(item, "metadata", None)
            record = _E2BSandboxRecord(
                sandbox_id=sandbox_id,
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
            session_id = str(record.metadata.get("session_id") or "").strip()
            if not sandbox_id:
                continue
            checked += 1
            expected = expected_sessions.get(session_id)
            if expected is None:
                await self._kill_sandbox_id(record.sandbox_id)
                removed.append(record.sandbox_id)
                continue
            if record.sandbox_id != expected["sandbox_id"]:
                await self._kill_sandbox_id(record.sandbox_id)
                removed.append(record.sandbox_id)
                continue
            if self._metadata_generation(record.metadata) != int(expected["runtime_generation"]):
                await self._kill_sandbox_id(record.sandbox_id)
                removed.append(record.sandbox_id)

        return {"checked": checked, "removed_sandbox_ids": removed}

    def _opencode_headers(self, sandbox) -> dict[str, str]:
        headers: dict[str, str] = {}
        traffic_access_token = str(sandbox.traffic_access_token or "").strip()
        if traffic_access_token:
            headers["e2b-traffic-access-token"] = traffic_access_token
        return headers

    def _build_opencode_client(self, sandbox):
        from app.services.opencode_server_client import OpenCodeServerClient, OpenCodeServerClientConfig

        base_url = self._normalize_upstream_base_url(sandbox.get_host(self.config.e2b_opencode_port))
        logger.info(
            "E2B_OPENCODE_CLIENT_BUILD sandbox_id=%s base_url=%s port=%s override=%s",
            str(getattr(sandbox, "sandbox_id", "") or ""),
            base_url,
            self.config.e2b_opencode_port,
            False,
        )
        return OpenCodeServerClient(
            OpenCodeServerClientConfig(
                enabled=True,
                base_url=base_url,
                api_key=None,
                request_timeout_seconds=max(20.0, float(self.config.request_timeout_seconds)),
                connect_timeout_seconds=5.0,
                health_cache_seconds=5,
                sandbox_controller_mode_override=False,
                extra_headers=self._opencode_headers(sandbox),
                skip_workspace_bootstrap=True,
            )
        )

    async def _ensure_opencode_server(self, sandbox, *, sandbox_id: str, workspace_path: str):
        state = _E2B_PROCESS_STATE.setdefault(sandbox_id, _E2BProcessState())
        if state.opencode_pid:
            try:
                listed = await sandbox.commands.list()
                if any(int(process.pid) == int(state.opencode_pid) for process in listed):
                    return self._build_opencode_client(sandbox)
            except Exception:
                pass
            state.opencode_pid = None

        log_dir = f"{workspace_path}/.opencode"
        log_path = f"{log_dir}/server.log"
        await self._ensure_directory(sandbox, log_dir)

        explicit = (os.getenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_SERVER_COMMAND") or "").strip()
        if not explicit:
            explicit = (os.getenv("APPS_CODING_AGENT_OPENCODE_SERVER_COMMAND") or "").strip()
        fallback_command = build_official_opencode_bootstrap_command(
            host="{host}",
            port=self.config.e2b_opencode_port,
        )
        template = explicit or fallback_command
        command = template.format(host="0.0.0.0", port=self.config.e2b_opencode_port)
        try:
            pid = await self._spawn_detached_shell(
                sandbox,
                command,
                cwd=workspace_path,
                log_path=log_path,
            )
            state.opencode_pid = int(pid)
            await self._wait_for_port(sandbox, self.config.e2b_opencode_port, timeout_seconds=60)
            client = self._build_opencode_client(sandbox)
            await client.ensure_healthy(force=True)
            return client
        except Exception as exc:
            log_excerpt = await self._read_log_excerpt(sandbox, log_path=log_path)
            if log_excerpt:
                raise PublishedAppSandboxBackendError(
                    f"OpenCode server failed to start on port {self.config.e2b_opencode_port}: {log_excerpt}"
                ) from exc
            raise

    async def ensure_opencode_endpoint(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> PublishedAppOpenCodeEndpoint:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        resolved_workspace = await self._resolve_workspace_path(sandbox, workspace_path)
        client = await self._ensure_opencode_server(
            sandbox,
            sandbox_id=sandbox_id,
            workspace_path=resolved_workspace,
        )
        base_url = str(getattr(getattr(client, "_config", None), "base_url", "") or "").strip()
        if not base_url:
            raise PublishedAppSandboxBackendError("E2B OpenCode endpoint is missing a base URL.")
        return PublishedAppOpenCodeEndpoint(
            sandbox_id=str(sandbox_id),
            base_url=base_url,
            workspace_path=resolved_workspace,
            extra_headers=self._opencode_headers(sandbox) or None,
        )
