from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


def is_truthy(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class PublishedAppSandboxBackendError(Exception):
    pass


@dataclass(frozen=True)
class PublishedAppSandboxBackendConfig:
    backend: Optional[str]
    controller_url: Optional[str]
    controller_token: Optional[str]
    request_timeout_seconds: int
    local_preview_base_url: str
    embedded_local_enabled: bool
    preview_proxy_base_path: str
    e2b_template: Optional[str]
    e2b_template_tag: Optional[str]
    e2b_timeout_seconds: int
    e2b_workspace_path: str
    e2b_preview_port: int
    e2b_opencode_port: int
    e2b_secure: bool
    e2b_allow_internet_access: bool
    e2b_auto_pause: bool
    sprite_api_base_url: str
    sprite_api_token: Optional[str]
    sprite_name_prefix: str
    sprite_workspace_path: str
    sprite_stage_workspace_path: Optional[str]
    sprite_publish_workspace_path: Optional[str]
    sprite_preview_port: int
    sprite_opencode_port: int
    sprite_preview_service_name: str
    sprite_opencode_service_name: str
    sprite_opencode_command: Optional[str]
    sprite_command_timeout_seconds: int
    sprite_retention_seconds: int
    sprite_network_policy: Optional[str]


@dataclass(frozen=True)
class PublishedAppOpenCodeEndpoint:
    sandbox_id: str
    base_url: str
    workspace_path: str
    api_key: Optional[str] = None
    extra_headers: Dict[str, str] | None = None


class PublishedAppSandboxBackend(ABC):
    backend_name = "unknown"
    is_remote = False

    def __init__(self, config: PublishedAppSandboxBackendConfig):
        self.config = config

    @abstractmethod
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
        preview_base_path: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def heartbeat_session(
        self,
        *,
        sandbox_id: str,
        idle_timeout_seconds: int,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def snapshot_workspace(self, *, sandbox_id: str, workspace: str = "live") -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def update_live_preview_context(
        self,
        *,
        sandbox_id: str,
        workspace_fingerprint: str | None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        workspace_path: str | None = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def resolve_workspace_path(self, *, sandbox_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def ensure_opencode_endpoint(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> PublishedAppOpenCodeEndpoint:
        raise NotImplementedError

    async def reconcile_session_scope(
        self,
        *,
        session_id: str,
        expected_sandbox_id: str | None,
        runtime_generation: int | None,
    ) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "kept_sandbox_id": expected_sandbox_id,
            "runtime_generation": int(runtime_generation or 0),
            "removed_sandbox_ids": [],
        }

    async def sweep_remote_sessions(
        self,
        *,
        active_sessions: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        _ = active_sessions
        return {"checked": 0, "removed_sandbox_ids": []}
