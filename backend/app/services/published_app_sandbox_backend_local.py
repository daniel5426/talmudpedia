from __future__ import annotations

from typing import Any, Dict

from app.services.published_app_draft_dev_local_runtime import (
    LocalDraftDevRuntimeError,
    get_local_draft_dev_runtime_manager,
)
from app.services.published_app_sandbox_backend import (
    PublishedAppSandboxBackend,
    PublishedAppSandboxBackendError,
)


class LocalSandboxBackend(PublishedAppSandboxBackend):
    backend_name = "local"
    is_remote = False

    @staticmethod
    def _manager():
        return get_local_draft_dev_runtime_manager()

    @staticmethod
    def _translate(exc: Exception) -> PublishedAppSandboxBackendError:
        return PublishedAppSandboxBackendError(str(exc))

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
        preview_base_path: str,
    ) -> Dict[str, Any]:
        _ = tenant_id, app_id, user_id, revision_id, entry_file, idle_timeout_seconds
        try:
            payload = await self._manager().start_session(
                session_id=session_id,
                files=files,
                dependency_hash=dependency_hash,
                draft_dev_token=draft_dev_token,
                preview_base_path=preview_base_path,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc
        payload["runtime_backend"] = self.backend_name
        payload["backend_metadata"] = {}
        return payload

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
        _ = entry_file, idle_timeout_seconds, preview_base_path
        try:
            payload = await self._manager().sync_session(
                sandbox_id=sandbox_id,
                files=files,
                dependency_hash=dependency_hash,
                install_dependencies=install_dependencies,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc
        payload["runtime_backend"] = self.backend_name
        return payload

    async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int) -> Dict[str, Any]:
        _ = idle_timeout_seconds
        try:
            payload = await self._manager().heartbeat_session(sandbox_id=sandbox_id)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc
        payload["runtime_backend"] = self.backend_name
        return payload

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            payload = await self._manager().stop_session(sandbox_id=sandbox_id)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc
        payload["runtime_backend"] = self.backend_name
        return payload

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        try:
            return await self._manager().list_files(sandbox_id=sandbox_id, limit=limit)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        try:
            return await self._manager().read_file(sandbox_id=sandbox_id, path=path)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

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
            return await self._manager().read_file_range(
                sandbox_id=sandbox_id,
                path=path,
                start_line=start_line,
                end_line=end_line,
                context_before=context_before,
                context_after=context_after,
                max_bytes=max_bytes,
                with_line_numbers=with_line_numbers,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        try:
            return await self._manager().search_code(sandbox_id=sandbox_id, query=query, max_results=max_results)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        try:
            return await self._manager().workspace_index(
                sandbox_id=sandbox_id,
                limit=limit,
                query=query,
                max_symbols_per_file=max_symbols_per_file,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        try:
            return await self._manager().apply_patch(
                sandbox_id=sandbox_id,
                patch=patch,
                options=options or {},
                preconditions=preconditions or {},
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        try:
            return await self._manager().write_file(sandbox_id=sandbox_id, path=path, content=content)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        try:
            return await self._manager().delete_file(sandbox_id=sandbox_id, path=path)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        try:
            return await self._manager().rename_file(sandbox_id=sandbox_id, from_path=from_path, to_path=to_path)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            return await self._manager().snapshot_files(sandbox_id=sandbox_id)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, Any]:
        try:
            return await self._manager().prepare_stage_workspace(sandbox_id=sandbox_id, reset=reset)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def snapshot_workspace(self, *, sandbox_id: str, workspace: str = "live") -> Dict[str, Any]:
        try:
            return await self._manager().snapshot_workspace(sandbox_id=sandbox_id, workspace=workspace)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            return await self._manager().promote_stage_workspace(sandbox_id=sandbox_id)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def prepare_publish_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        try:
            return await self._manager().prepare_publish_workspace(sandbox_id=sandbox_id)
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        try:
            return await self._manager().prepare_publish_dependencies(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

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
            return await self._manager().run_command(
                sandbox_id=sandbox_id,
                command=command,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                workspace_path=workspace_path,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, Any]:
        try:
            return await self._manager().export_workspace_archive(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                format=format,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, Any]:
        try:
            return await self._manager().sync_workspace_files(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                files=files,
            )
        except LocalDraftDevRuntimeError as exc:
            raise self._translate(exc) from exc

    async def resolve_workspace_path(self, *, sandbox_id: str) -> str | None:
        return await self._manager().resolve_project_dir(sandbox_id=sandbox_id)

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
        raise PublishedAppSandboxBackendError(
            "OpenCode sandbox run requires a remote sandbox backend."
        )

    async def stream_opencode_events(self, *, sandbox_id: str, run_ref: str):
        _ = sandbox_id, run_ref
        raise PublishedAppSandboxBackendError(
            "OpenCode sandbox stream requires a remote sandbox backend."
        )

    async def cancel_opencode_run(self, *, sandbox_id: str, run_ref: str) -> Dict[str, Any]:
        _ = sandbox_id, run_ref
        raise PublishedAppSandboxBackendError(
            "OpenCode sandbox cancellation requires a remote sandbox backend."
        )

    async def answer_opencode_question(
        self,
        *,
        sandbox_id: str,
        run_ref: str,
        question_id: str,
        answers: list[list[str]],
    ) -> Dict[str, Any]:
        _ = sandbox_id, run_ref, question_id, answers
        raise PublishedAppSandboxBackendError(
            "OpenCode sandbox question response requires a remote sandbox backend."
        )
