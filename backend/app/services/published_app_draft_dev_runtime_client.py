from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services.published_app_sandbox_backend_sprite import SpriteSandboxBackend
from app.services.published_app_sandbox_backend import (
    PublishedAppOpenCodeEndpoint,
    PublishedAppSandboxBackendError,
)
from app.services.published_app_sandbox_backend_factory import (
    build_published_app_sandbox_backend,
    load_published_app_sandbox_backend_config,
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
    backend: Optional[str] = None
    preview_proxy_base_path: str = "/public/apps-builder/draft-dev/sessions"
    e2b_template: Optional[str] = None
    e2b_template_tag: Optional[str] = None
    e2b_timeout_seconds: int = 1800
    e2b_workspace_path: str = "/workspace"
    e2b_preview_port: int = 4173
    e2b_opencode_port: int = 4141
    e2b_secure: bool = True
    e2b_allow_internet_access: bool = True
    e2b_auto_pause: bool = False
    sprite_api_base_url: str = "https://api.sprites.dev"
    sprite_api_token: Optional[str] = None
    sprite_name_prefix: str = "app-builder"
    sprite_workspace_path: str = "/home/sprite/app"
    sprite_stage_workspace_path: Optional[str] = None
    sprite_publish_workspace_path: Optional[str] = None
    sprite_preview_port: int = 8080
    sprite_opencode_port: int = 4141
    sprite_preview_service_name: str = "builder-preview"
    sprite_opencode_service_name: str = "opencode"
    sprite_opencode_command: Optional[str] = None
    sprite_command_timeout_seconds: int = 900
    sprite_retention_seconds: int = 21600
    sprite_network_policy: Optional[str] = None


class PublishedAppDraftDevRuntimeClient:
    def __init__(self, config: PublishedAppDraftDevRuntimeClientConfig):
        self._config = config
        backend_config = load_published_app_sandbox_backend_config()
        resolved_backend = config.backend
        if resolved_backend is None and not config.controller_url:
            resolved_backend = backend_config.backend
        merged = backend_config.__class__(
            backend=resolved_backend,
            controller_url=config.controller_url,
            controller_token=config.controller_token,
            request_timeout_seconds=config.request_timeout_seconds,
            local_preview_base_url=config.local_preview_base_url,
            embedded_local_enabled=config.embedded_local_enabled,
            preview_proxy_base_path=config.preview_proxy_base_path,
            e2b_template=config.e2b_template,
            e2b_template_tag=config.e2b_template_tag,
            e2b_timeout_seconds=config.e2b_timeout_seconds,
            e2b_workspace_path=config.e2b_workspace_path,
            e2b_preview_port=config.e2b_preview_port,
            e2b_opencode_port=config.e2b_opencode_port,
            e2b_secure=config.e2b_secure,
            e2b_allow_internet_access=config.e2b_allow_internet_access,
            e2b_auto_pause=config.e2b_auto_pause,
            sprite_api_base_url=config.sprite_api_base_url,
            sprite_api_token=config.sprite_api_token,
            sprite_name_prefix=config.sprite_name_prefix,
            sprite_workspace_path=config.sprite_workspace_path,
            sprite_stage_workspace_path=config.sprite_stage_workspace_path,
            sprite_publish_workspace_path=config.sprite_publish_workspace_path,
            sprite_preview_port=config.sprite_preview_port,
            sprite_opencode_port=config.sprite_opencode_port,
            sprite_preview_service_name=config.sprite_preview_service_name,
            sprite_opencode_service_name=config.sprite_opencode_service_name,
            sprite_opencode_command=config.sprite_opencode_command,
            sprite_command_timeout_seconds=config.sprite_command_timeout_seconds,
            sprite_retention_seconds=config.sprite_retention_seconds,
            sprite_network_policy=config.sprite_network_policy,
        )
        self._backend = build_published_app_sandbox_backend(merged)

    @classmethod
    def from_env(cls) -> "PublishedAppDraftDevRuntimeClient":
        backend_config = load_published_app_sandbox_backend_config()
        return cls(
            PublishedAppDraftDevRuntimeClientConfig(
                controller_url=backend_config.controller_url,
                controller_token=backend_config.controller_token,
                request_timeout_seconds=backend_config.request_timeout_seconds,
                local_preview_base_url=backend_config.local_preview_base_url,
                embedded_local_enabled=backend_config.embedded_local_enabled,
                backend=backend_config.backend,
                preview_proxy_base_path=backend_config.preview_proxy_base_path,
                e2b_template=backend_config.e2b_template,
                e2b_template_tag=backend_config.e2b_template_tag,
                e2b_timeout_seconds=backend_config.e2b_timeout_seconds,
                e2b_workspace_path=backend_config.e2b_workspace_path,
                e2b_preview_port=backend_config.e2b_preview_port,
                e2b_opencode_port=backend_config.e2b_opencode_port,
                e2b_secure=backend_config.e2b_secure,
                e2b_allow_internet_access=backend_config.e2b_allow_internet_access,
                e2b_auto_pause=backend_config.e2b_auto_pause,
                sprite_api_base_url=backend_config.sprite_api_base_url,
                sprite_api_token=backend_config.sprite_api_token,
                sprite_name_prefix=backend_config.sprite_name_prefix,
                sprite_workspace_path=backend_config.sprite_workspace_path,
                sprite_stage_workspace_path=backend_config.sprite_stage_workspace_path,
                sprite_publish_workspace_path=backend_config.sprite_publish_workspace_path,
                sprite_preview_port=backend_config.sprite_preview_port,
                sprite_opencode_port=backend_config.sprite_opencode_port,
                sprite_preview_service_name=backend_config.sprite_preview_service_name,
                sprite_opencode_service_name=backend_config.sprite_opencode_service_name,
                sprite_opencode_command=backend_config.sprite_opencode_command,
                sprite_command_timeout_seconds=backend_config.sprite_command_timeout_seconds,
                sprite_retention_seconds=backend_config.sprite_retention_seconds,
                sprite_network_policy=backend_config.sprite_network_policy,
            )
        )

    @property
    def is_remote_enabled(self) -> bool:
        return bool(self._backend.is_remote)

    @property
    def backend_name(self) -> str:
        return str(self._backend.backend_name)

    def expected_sandbox_id_for_app(self, *, app_id: str) -> str | None:
        if self.backend_name != "sprite":
            return None
        return SpriteSandboxBackend._sprite_name(
            prefix=self._config.sprite_name_prefix,
            app_id=app_id,
        )

    def build_preview_proxy_path(self, session_id: str) -> str:
        base = str(self._config.preview_proxy_base_path or "").rstrip("/")
        return f"{base}/{session_id}/preview/"

    async def start_session(
        self,
        *,
        session_id: str,
        runtime_generation: int,
        organization_id: str,
        app_id: str,
        user_id: str,
        revision_id: str,
        app_public_id: str,
        agent_id: str,
        entry_file: str,
        files: Dict[str, str],
        idle_timeout_seconds: int,
        dependency_hash: str,
        preview_base_path: str | None = None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.start_session(
                session_id=session_id,
                runtime_generation=runtime_generation,
                organization_id=organization_id,
                app_id=app_id,
                user_id=user_id,
                revision_id=revision_id,
                app_public_id=app_public_id,
                agent_id=agent_id,
                entry_file=entry_file,
                files=files,
                idle_timeout_seconds=idle_timeout_seconds,
                dependency_hash=dependency_hash,
                preview_base_path=preview_base_path or self.build_preview_proxy_path(session_id),
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def reconcile_session_scope(
        self,
        *,
        session_id: str,
        expected_sandbox_id: str | None,
        runtime_generation: int | None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.reconcile_session_scope(
                session_id=session_id,
                expected_sandbox_id=expected_sandbox_id,
                runtime_generation=runtime_generation,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def sweep_remote_sessions(
        self,
        *,
        active_sessions: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.sweep_remote_sessions(active_sessions=active_sessions)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def sync_session(
        self,
        *,
        sandbox_id: str,
        app_id: str,
        app_public_id: str,
        agent_id: str,
        entry_file: str,
        files: Dict[str, str],
        idle_timeout_seconds: int,
        dependency_hash: str,
        install_dependencies: bool,
        preview_base_path: str | None = None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.sync_session(
                sandbox_id=sandbox_id,
                app_id=app_id,
                app_public_id=app_public_id,
                agent_id=agent_id,
                entry_file=entry_file,
                files=files,
                idle_timeout_seconds=idle_timeout_seconds,
                dependency_hash=dependency_hash,
                install_dependencies=install_dependencies,
                preview_base_path=preview_base_path,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int) -> Dict[str, Any]:
        try:
            return await self._backend.heartbeat_session(
                sandbox_id=sandbox_id,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            return await self._backend.stop_session(sandbox_id=sandbox_id)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def update_live_preview_context(
        self,
        *,
        sandbox_id: str,
        workspace_fingerprint: str | None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.update_live_preview_context(
                sandbox_id=sandbox_id,
                workspace_fingerprint=workspace_fingerprint,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        try:
            return await self._backend.list_files(sandbox_id=sandbox_id, limit=limit)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        try:
            return await self._backend.read_file(sandbox_id=sandbox_id, path=path)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

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
        try:
            return await self._backend.read_file_range(
                sandbox_id=sandbox_id,
                path=path,
                start_line=start_line,
                end_line=end_line,
                context_before=context_before,
                context_after=context_after,
                max_bytes=max_bytes,
                with_line_numbers=with_line_numbers,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        try:
            return await self._backend.search_code(sandbox_id=sandbox_id, query=query, max_results=max_results)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.workspace_index(
                sandbox_id=sandbox_id,
                limit=limit,
                query=query,
                max_symbols_per_file=max_symbols_per_file,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.apply_patch(
                sandbox_id=sandbox_id,
                patch=patch,
                options=options or {},
                preconditions=preconditions or {},
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        try:
            return await self._backend.write_file(sandbox_id=sandbox_id, path=path, content=content)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        try:
            return await self._backend.delete_file(sandbox_id=sandbox_id, path=path)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        try:
            return await self._backend.rename_file(
                sandbox_id=sandbox_id,
                from_path=from_path,
                to_path=to_path,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            return await self._backend.snapshot_files(sandbox_id=sandbox_id)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, Any]:
        try:
            return await self._backend.prepare_stage_workspace(sandbox_id=sandbox_id, reset=reset)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def snapshot_workspace(self, *, sandbox_id: str, workspace: str = "live") -> Dict[str, Any]:
        try:
            return await self._backend.snapshot_workspace(sandbox_id=sandbox_id, workspace=workspace)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            return await self._backend.promote_stage_workspace(sandbox_id=sandbox_id)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        try:
            return await self._backend.prepare_publish_dependencies(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        workspace_path: str | None = None,
    ) -> Dict[str, Any]:
        try:
            return await self._backend.run_command(
                sandbox_id=sandbox_id,
                command=command,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                workspace_path=workspace_path,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, Any]:
        try:
            return await self._backend.export_workspace_archive(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                format=format,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, Any]:
        try:
            return await self._backend.sync_workspace_files(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                files=files,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    @staticmethod
    def decode_archive_payload(response: Dict[str, Any]) -> bytes:
        payload = str(response.get("archive_base64") or "")
        if not payload:
            raise PublishedAppDraftDevRuntimeClientError("Sandbox archive response is missing archive_base64")
        try:
            return base64.b64decode(payload)
        except Exception as exc:
            raise PublishedAppDraftDevRuntimeClientError("Sandbox archive response contains invalid base64 payload") from exc

    async def resolve_local_workspace_path(self, *, sandbox_id: str) -> str | None:
        try:
            return await self._backend.resolve_workspace_path(sandbox_id=sandbox_id)
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc

    async def ensure_opencode_endpoint(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> PublishedAppOpenCodeEndpoint:
        try:
            return await self._backend.ensure_opencode_endpoint(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
            )
        except PublishedAppSandboxBackendError as exc:
            raise PublishedAppDraftDevRuntimeClientError(str(exc)) from exc
