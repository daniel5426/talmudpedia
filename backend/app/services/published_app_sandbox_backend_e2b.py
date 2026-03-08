from __future__ import annotations

import base64
import io
import json
import tarfile
from typing import Any, Dict

import httpx

from app.services.published_app_draft_dev_patching import apply_unified_patch_transaction, hash_text
from app.services.published_app_sandbox_backend import (
    PublishedAppSandboxBackend,
    PublishedAppSandboxBackendError,
)
from app.services.published_app_sandbox_backend_e2b_runtime import (
    E2BSandboxRuntimeMixin,
    _E2BProcessState,
    _E2B_PROCESS_STATE,
)
from app.services.published_app_sandbox_backend_e2b_workspace import E2BSandboxWorkspaceMixin

try:
    from e2b import AsyncSandbox
    from e2b.sandbox.sandbox_api import SandboxQuery
except Exception:  # pragma: no cover - import failure is handled at runtime
    AsyncSandbox = None
    SandboxQuery = None

class E2BSandboxBackend(E2BSandboxRuntimeMixin, E2BSandboxWorkspaceMixin, PublishedAppSandboxBackend):
    backend_name = "e2b"
    is_remote = True

    def _require_sdk(self) -> None:
        if AsyncSandbox is None or SandboxQuery is None:
            raise PublishedAppSandboxBackendError(
                "E2B backend is configured but the `e2b` package is unavailable."
            )

    async def _create_sandbox(self, *, metadata: dict[str, str], idle_timeout_seconds: int):
        self._require_sdk()
        lifecycle = None
        if self.config.e2b_auto_pause:
            lifecycle = {
                "on_timeout": "pause",
                "auto_resume": True,
            }
        try:
            return await AsyncSandbox.create(
                template=self.config.e2b_template or None,
                timeout=max(int(idle_timeout_seconds), int(self.config.e2b_timeout_seconds)),
                metadata=metadata,
                secure=bool(self.config.e2b_secure),
                allow_internet_access=bool(self.config.e2b_allow_internet_access),
                lifecycle=lifecycle,
            )
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Failed to create E2B sandbox: {exc}") from exc

    async def _connect_sandbox(self, *, sandbox_id: str):
        self._require_sdk()
        try:
            return await AsyncSandbox.connect(
                sandbox_id=sandbox_id,
                timeout=max(60, int(self.config.e2b_timeout_seconds)),
            )
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Failed to connect to E2B sandbox `{sandbox_id}`: {exc}") from exc

    async def _start_preview_process(self, sandbox, *, sandbox_id: str, workspace_root: str, preview_base_path: str) -> None:
        state = _E2B_PROCESS_STATE.setdefault(sandbox_id, _E2BProcessState())
        await self._kill_pid_if_present(sandbox, state.preview_pid)
        command = self._dev_command(
            port=self.config.e2b_preview_port,
            preview_base_path=preview_base_path,
        )
        preview_pid = await self._spawn_detached_shell(
            sandbox,
            command,
            cwd=workspace_root,
            log_path=f"{workspace_root}/.draft-dev.log",
        )
        state.preview_pid = int(preview_pid)
        state.preview_base_path = preview_base_path
        try:
            await self._wait_for_port(sandbox, self.config.e2b_preview_port)
            await self._verify_preview_http_ready(sandbox, preview_base_path=preview_base_path)
        except Exception as exc:
            log_excerpt = await self._read_preview_log_excerpt(sandbox, workspace_root=workspace_root)
            if log_excerpt:
                raise PublishedAppSandboxBackendError(
                    f"Preview server failed to start on port {self.config.e2b_preview_port}: {log_excerpt}"
                ) from exc
            raise

    async def _read_preview_log_excerpt(self, sandbox, *, workspace_root: str) -> str:
        try:
            content = await sandbox.files.read(f"{workspace_root}/.draft-dev.log")
        except Exception:
            return ""
        text = str(content or "").strip()
        if len(text) > 1200:
            text = text[-1200:]
        return text

    async def _verify_preview_http_ready(self, sandbox, *, preview_base_path: str) -> None:
        upstream = self._normalize_upstream_base_url(sandbox.get_host(self.config.e2b_preview_port))
        headers: dict[str, str] = {}
        traffic_access_token = str(sandbox.traffic_access_token or "").strip()
        if traffic_access_token:
            headers["e2b-traffic-access-token"] = traffic_access_token
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.get(f"{upstream.rstrip('/')}{preview_base_path}", headers=headers)
        except Exception as exc:
            raise PublishedAppSandboxBackendError(
                f"Preview service is unreachable on port {self.config.e2b_preview_port}: {exc}"
            ) from exc
        if response.status_code >= 500:
            raise PublishedAppSandboxBackendError(
                f"Preview service responded with {response.status_code} on port {self.config.e2b_preview_port}."
            )

    async def _ensure_preview_process(self, sandbox, *, sandbox_id: str, workspace_root: str, preview_base_path: str) -> None:
        try:
            await self._wait_for_port(sandbox, self.config.e2b_preview_port, timeout_seconds=3)
            await self._verify_preview_http_ready(sandbox, preview_base_path=preview_base_path)
            state = _E2B_PROCESS_STATE.setdefault(sandbox_id, _E2BProcessState())
            state.preview_base_path = preview_base_path
            return
        except PublishedAppSandboxBackendError:
            pass
        await self._start_preview_process(
            sandbox,
            sandbox_id=sandbox_id,
            workspace_root=workspace_root,
            preview_base_path=preview_base_path,
        )

    async def _build_backend_metadata(self, sandbox, *, preview_base_path: str) -> dict[str, Any]:
        host = self._normalize_upstream_base_url(sandbox.get_host(self.config.e2b_preview_port))
        metadata: dict[str, Any] = {
            "preview": {
                "upstream_base_url": host,
                "base_path": preview_base_path,
            },
            "workspace_path": self._workspace_root(self.config.e2b_workspace_path),
        }
        traffic_access_token = str(sandbox.traffic_access_token or "").strip()
        if traffic_access_token:
            metadata["preview"]["traffic_access_token"] = traffic_access_token
        return metadata

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
        _ = entry_file, draft_dev_token
        workspace_root = self._workspace_root(self.config.e2b_workspace_path)
        metadata = {
            "runtime_profile": "app_builder_preview",
            "tenant_id": tenant_id,
            "app_id": app_id,
            "user_id": user_id,
            "revision_id": revision_id,
            "session_id": session_id,
            "runtime_generation": str(int(runtime_generation or 0)),
        }
        sandbox = await self._create_sandbox(metadata=metadata, idle_timeout_seconds=idle_timeout_seconds)
        await self._ensure_directory(sandbox, workspace_root)
        await self._sync_workspace_tree(sandbox, workspace_root, files)
        if await self._must_install_dependencies(sandbox, workspace_root, dependency_hash):
            await self._run_install(sandbox, workspace_root)
            await self._write_dependency_hash_marker(sandbox, workspace_root, dependency_hash)
        await self._start_preview_process(
            sandbox,
            sandbox_id=sandbox.sandbox_id,
            workspace_root=workspace_root,
            preview_base_path=preview_base_path,
        )
        removed = await self._kill_session_sandboxes(session_id=session_id, exclude_sandbox_id=str(sandbox.sandbox_id))
        return {
            "sandbox_id": str(sandbox.sandbox_id),
            "status": "serving",
            "workspace_path": workspace_root,
            "runtime_backend": self.backend_name,
            "removed_sandbox_ids": removed,
            "backend_metadata": await self._build_backend_metadata(
                sandbox,
                preview_base_path=preview_base_path,
            ),
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
        preview_base_path: str | None = None,
    ) -> Dict[str, Any]:
        _ = entry_file
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        await sandbox.set_timeout(max(int(idle_timeout_seconds), int(self.config.e2b_timeout_seconds)))
        workspace_root = self._workspace_root(self.config.e2b_workspace_path)
        await self._sync_workspace_tree(sandbox, workspace_root, files)
        effective_preview_base_path = str(preview_base_path or "").strip() or (
            _E2B_PROCESS_STATE.get(sandbox_id, _E2BProcessState()).preview_base_path or "/"
        )
        if install_dependencies or await self._must_install_dependencies(sandbox, workspace_root, dependency_hash):
            await self._run_install(sandbox, workspace_root)
            await self._write_dependency_hash_marker(sandbox, workspace_root, dependency_hash)
        await self._ensure_preview_process(
            sandbox,
            sandbox_id=sandbox_id,
            workspace_root=workspace_root,
            preview_base_path=effective_preview_base_path,
        )
        return {
            "status": "serving",
            "sandbox_id": sandbox_id,
            "runtime_backend": self.backend_name,
            "backend_metadata": await self._build_backend_metadata(
                sandbox,
                preview_base_path=effective_preview_base_path,
            ),
        }

    async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        await sandbox.set_timeout(max(int(idle_timeout_seconds), int(self.config.e2b_timeout_seconds)))
        preview_base_path = _E2B_PROCESS_STATE.get(sandbox_id, _E2BProcessState()).preview_base_path or "/"
        await self._ensure_preview_process(
            sandbox,
            sandbox_id=sandbox_id,
            workspace_root=self._workspace_root(self.config.e2b_workspace_path),
            preview_base_path=preview_base_path,
        )
        return {"status": "serving", "sandbox_id": sandbox_id, "runtime_backend": self.backend_name}

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        state = _E2B_PROCESS_STATE.pop(sandbox_id, None)
        if state is not None:
            await self._kill_pid_if_present(sandbox, state.preview_pid)
            await self._kill_pid_if_present(sandbox, state.opencode_pid)
        try:
            await sandbox.kill()
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Failed to kill E2B sandbox `{sandbox_id}`: {exc}") from exc
        return {"status": "stopped", "sandbox_id": sandbox_id, "runtime_backend": self.backend_name}

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        files = await self._list_workspace_paths(sandbox, self._workspace_root(self.config.e2b_workspace_path))
        return {"sandbox_id": sandbox_id, "count": len(files), "paths": files[: max(1, int(limit))]}

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        normalized = self._normalize_runtime_path(path)
        target_path = f"{self._workspace_root(self.config.e2b_workspace_path)}/{normalized}"
        try:
            content = await sandbox.files.read(target_path)
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"File not found: {normalized}") from exc
        rendered = str(content)
        return {
            "sandbox_id": sandbox_id,
            "path": normalized,
            "content": rendered,
            "size_bytes": len(rendered.encode("utf-8")),
            "sha256": hash_text(rendered),
        }

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
        payload = await self.read_file(sandbox_id=sandbox_id, path=path)
        source = str(payload.get("content") or "")
        lines = source.splitlines()
        if not lines:
            return {
                "sandbox_id": sandbox_id,
                "path": path,
                "start_line": 1,
                "end_line": 1,
                "content": "",
                "line_count": 0,
                "truncated": False,
                "size_bytes": 0,
                "sha256": hash_text(source),
            }
        effective_start = max(1, int(start_line or 1))
        effective_end = int(end_line or effective_start)
        if effective_end < effective_start:
            effective_end = effective_start
        effective_start = max(1, effective_start - max(0, int(context_before or 0)))
        effective_end = min(len(lines), effective_end + max(0, int(context_after or 0)))
        if effective_start > len(lines):
            effective_start = len(lines)
        if effective_end < effective_start:
            effective_end = effective_start
        selected = lines[effective_start - 1 : effective_end]
        rendered = [f"{effective_start + idx}: {line}" for idx, line in enumerate(selected)] if with_line_numbers else selected
        content = "\n".join(rendered)
        encoded = content.encode("utf-8")
        truncated = False
        if len(encoded) > max(256, int(max_bytes or 12000)):
            content = encoded[: int(max_bytes or 12000)].decode("utf-8", errors="ignore")
            truncated = True
        return {
            "sandbox_id": sandbox_id,
            "path": path,
            "start_line": effective_start,
            "end_line": effective_end,
            "content": content,
            "line_count": len(selected),
            "truncated": truncated,
            "size_bytes": len(content.encode("utf-8")),
            "sha256": hash_text(source),
        }

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        needle = str(query or "").strip().lower()
        if not needle:
            return {"sandbox_id": sandbox_id, "query": query, "matches": []}
        files = await self.snapshot_files(sandbox_id=sandbox_id)
        matches: list[dict[str, Any]] = []
        for rel_path, source in dict(files.get("files") or {}).items():
            for line_no, line in enumerate(str(source).splitlines(), start=1):
                if needle in line.lower():
                    matches.append({"path": rel_path, "line": line_no, "preview": line[:220]})
                    if len(matches) >= max(1, int(max_results)):
                        return {"sandbox_id": sandbox_id, "query": query, "matches": matches}
        return {"sandbox_id": sandbox_id, "query": query, "matches": matches}

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        files = await self.snapshot_files(sandbox_id=sandbox_id)
        query_text = str(query or "").strip().lower()
        rows: list[dict[str, Any]] = []
        total_size = 0
        for rel_path, source in dict(files.get("files") or {}).items():
            text = str(source)
            size_bytes = len(text.encode("utf-8"))
            total_size += size_bytes
            symbols = self._extract_symbol_outline(text, rel_path, max_symbols_per_file=max_symbols_per_file)
            score = 0
            if query_text:
                if query_text in rel_path.lower():
                    score += 4
                if query_text in text.lower():
                    score += 2
                if any(query_text in str(item.get("name", "")).lower() for item in symbols):
                    score += 3
                if score <= 0:
                    continue
            rows.append(
                {
                    "path": rel_path,
                    "size_bytes": size_bytes,
                    "sha256": hash_text(text),
                    "language": self._detect_language(rel_path),
                    "symbol_outline": symbols,
                    "score": score,
                }
            )
        rows.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("path", ""))))
        return {
            "sandbox_id": sandbox_id,
            "query": query,
            "total_files": len(rows),
            "total_size_bytes": total_size,
            "files": rows[: max(1, int(limit))],
        }

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        files_payload = await self.snapshot_files(sandbox_id=sandbox_id)
        current_files = {
            str(path): str(content if isinstance(content, str) else str(content))
            for path, content in dict(files_payload.get("files") or {}).items()
        }

        def _normalize_path(path_value: str) -> str:
            return self._normalize_runtime_path(path_value)

        def _read_file(path_value: str) -> str | None:
            return current_files.get(path_value)

        try:
            result = apply_unified_patch_transaction(
                patch=patch,
                normalize_path=_normalize_path,
                read_file=_read_file,
                options=options,
                preconditions=preconditions,
            )
        except Exception as exc:
            return {
                "ok": False,
                "code": "PATCH_POLICY_VIOLATION",
                "summary": str(exc) or "Patch policy violation",
                "failures": [],
                "applied_files": [],
            }

        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        workspace_root = self._workspace_root(self.config.e2b_workspace_path)
        writes = result.get("writes") if isinstance(result.get("writes"), dict) else {}
        deletes = result.get("deletes") if isinstance(result.get("deletes"), list) else []
        for path_value, content in writes.items():
            await sandbox.files.write(f"{workspace_root}/{path_value}", str(content))
        for path_value in deletes:
            try:
                await sandbox.files.remove(f"{workspace_root}/{path_value}")
            except Exception:
                continue
        response = {key: value for key, value in result.items() if key not in {"writes", "deletes"}}
        response["metrics"] = {
            "patch_bytes": len(str(patch or "").encode("utf-8")),
            "applied_file_count": len(response.get("applied_files") or []),
            "failure_count": len(response.get("failures") or []),
            "edit_latency_ms": 0,
        }
        return response

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        normalized = self._normalize_runtime_path(path)
        await sandbox.files.write(f"{self._workspace_root(self.config.e2b_workspace_path)}/{normalized}", content)
        return {"sandbox_id": sandbox_id, "path": normalized, "status": "written"}

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        normalized = self._normalize_runtime_path(path)
        try:
            await sandbox.files.remove(f"{self._workspace_root(self.config.e2b_workspace_path)}/{normalized}")
        except Exception:
            pass
        return {"sandbox_id": sandbox_id, "path": normalized, "status": "deleted"}

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        src = self._normalize_runtime_path(from_path)
        dst = self._normalize_runtime_path(to_path)
        try:
            await sandbox.files.rename(
                f"{self._workspace_root(self.config.e2b_workspace_path)}/{src}",
                f"{self._workspace_root(self.config.e2b_workspace_path)}/{dst}",
            )
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Failed to rename file `{src}` to `{dst}`: {exc}") from exc
        return {"sandbox_id": sandbox_id, "from_path": src, "to_path": dst, "status": "renamed"}

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        files = await self._collect_workspace_files_from_root(
            sandbox,
            self._workspace_root(self.config.e2b_workspace_path),
        )
        return {"sandbox_id": sandbox_id, "files": files, "file_count": len(files)}

    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        workspace_root = self._workspace_root(self.config.e2b_workspace_path)
        stage_workspace = self._stage_workspace_dir()
        live_files: Dict[str, str] = {}
        if bool(reset) or not await sandbox.files.exists(stage_workspace):
            live_files = await self._collect_workspace_files_from_root(sandbox, workspace_root)
            await self._ensure_directory(sandbox, stage_workspace)
            await self._sync_workspace_tree(sandbox, stage_workspace, live_files)
        return {
            "sandbox_id": sandbox_id,
            "reset": bool(reset),
            "live_workspace_path": workspace_root,
            "stage_workspace_path": stage_workspace,
            "workspace_path": stage_workspace,
            "file_count": len(live_files),
        }

    async def snapshot_workspace(self, *, sandbox_id: str, workspace: str = "live") -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        workspace_key = str(workspace or "live").strip().lower() or "live"
        workspace_root = self._workspace_root(self.config.e2b_workspace_path)
        if workspace_key == "stage":
            workspace_root = self._stage_workspace_dir()
            if not await sandbox.files.exists(workspace_root):
                raise PublishedAppSandboxBackendError("Stage workspace is not prepared")
        elif workspace_key != "live":
            raise PublishedAppSandboxBackendError(f"Unsupported workspace scope: {workspace}")
        files = await self._collect_workspace_files_from_root(sandbox, workspace_root)
        return {
            "sandbox_id": sandbox_id,
            "workspace": workspace_key,
            "workspace_path": workspace_root,
            "files": files,
            "file_count": len(files),
        }

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        stage_workspace = self._stage_workspace_dir()
        if not await sandbox.files.exists(stage_workspace):
            raise PublishedAppSandboxBackendError("Stage workspace is not prepared")
        stage_files = await self._collect_workspace_files_from_root(sandbox, stage_workspace)
        await self._sync_workspace_tree(sandbox, self._workspace_root(self.config.e2b_workspace_path), stage_files)
        return {
            "sandbox_id": sandbox_id,
            "live_workspace_path": self._workspace_root(self.config.e2b_workspace_path),
            "stage_workspace_path": stage_workspace,
            "promoted_file_count": len(stage_files),
        }

    async def prepare_publish_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        live_files = await self._collect_workspace_files_from_root(
            sandbox,
            self._workspace_root(self.config.e2b_workspace_path),
        )
        publish_workspace = self._publish_workspace_dir()
        await self._ensure_directory(sandbox, publish_workspace)
        await self._sync_workspace_tree(sandbox, publish_workspace, live_files)
        return {
            "sandbox_id": sandbox_id,
            "workspace": "publish",
            "live_workspace_path": self._workspace_root(self.config.e2b_workspace_path),
            "publish_workspace_path": publish_workspace,
            "workspace_path": publish_workspace,
            "files": live_files,
            "file_count": len(live_files),
        }

    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        publish_workspace = await self._resolve_workspace_path(sandbox, workspace_path)
        live_workspace = self._workspace_root(self.config.e2b_workspace_path)

        publish_package_json_exists = await sandbox.files.exists(f"{publish_workspace}/package.json")
        live_package_json_exists = await sandbox.files.exists(f"{live_workspace}/package.json")
        if not publish_package_json_exists:
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": publish_workspace,
                "live_workspace_path": live_workspace,
                "status": "no_package_json",
                "strategy": "none",
                "reason": "publish workspace has no package.json",
            }
        if not live_package_json_exists:
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": publish_workspace,
                "live_workspace_path": live_workspace,
                "status": "fallback_required",
                "strategy": "none",
                "reason": "live workspace has no package.json",
            }
        live_package_json = await sandbox.files.read(f"{live_workspace}/package.json")
        publish_package_json = await sandbox.files.read(f"{publish_workspace}/package.json")
        if str(live_package_json) != str(publish_package_json):
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": publish_workspace,
                "live_workspace_path": live_workspace,
                "status": "incompatible_lockfile",
                "strategy": "none",
                "reason": "package.json differs between live and publish workspaces",
            }
        live_node_modules = f"{live_workspace}/node_modules"
        if not await sandbox.files.exists(live_node_modules):
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": publish_workspace,
                "live_workspace_path": live_workspace,
                "status": "missing_live_node_modules",
                "strategy": "none",
                "reason": "live workspace node_modules is missing",
            }
        publish_node_modules = f"{publish_workspace}/node_modules"
        command = (
            f"rm -rf {shlex.quote(publish_node_modules)} && "
            f"ln -s {shlex.quote(live_node_modules)} {shlex.quote(publish_node_modules)}"
        )
        result = await self._run_shell(sandbox, command, timeout_seconds=30)
        if int(result.exit_code or 0) == 0:
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": publish_workspace,
                "live_workspace_path": live_workspace,
                "status": "reused",
                "strategy": "symlink",
                "reason": "reused live workspace node_modules via symlink",
            }
        copy_result = await self._run_shell(
            sandbox,
            f"rm -rf {shlex.quote(publish_node_modules)} && cp -a {shlex.quote(live_node_modules)} {shlex.quote(publish_node_modules)}",
            timeout_seconds=120,
        )
        if int(copy_result.exit_code or 0) == 0:
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": publish_workspace,
                "live_workspace_path": live_workspace,
                "status": "reused",
                "strategy": "copy",
                "reason": "reused live workspace node_modules via copy fallback",
            }
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": publish_workspace,
            "live_workspace_path": live_workspace,
            "status": "fallback_required",
            "strategy": "none",
            "reason": "dependency reuse unavailable for publish workspace",
        }

    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        workspace_path: str | None = None,
    ) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        resolved_cwd = await self._resolve_workspace_path(sandbox, workspace_path)
        shell_command = " ".join(shlex.quote(part) for part in command)
        result = await self._run_shell(
            sandbox,
            shell_command,
            cwd=resolved_cwd,
            timeout_seconds=float(timeout_seconds),
        )
        stdout = str(result.stdout or "")
        stderr = str(result.stderr or "")
        if len(stdout) > int(max_output_bytes):
            stdout = stdout[: int(max_output_bytes)] + "... [truncated]"
        if len(stderr) > int(max_output_bytes):
            stderr = stderr[: int(max_output_bytes)] + "... [truncated]"
        return {
            "sandbox_id": sandbox_id,
            "command": command,
            "code": int(result.exit_code or 0),
            "stdout": stdout,
            "stderr": stderr,
            "workspace_path": resolved_cwd,
        }

    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        archive_root = await self._resolve_workspace_path(sandbox, workspace_path)
        fmt = str(format or "tar.gz").strip().lower()
        if fmt != "tar.gz":
            raise PublishedAppSandboxBackendError(f"Unsupported archive format: {format}")
        files = await self._collect_workspace_files_from_root(sandbox, archive_root)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for rel_path, content in files.items():
                payload = content.encode("utf-8")
                info = tarfile.TarInfo(name=rel_path)
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
        payload = buffer.getvalue()
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": archive_root,
            "format": "tar.gz",
            "archive_base64": base64.b64encode(payload).decode("ascii"),
            "size_bytes": len(payload),
        }

    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, Any]:
        sandbox = await self._connect_sandbox(sandbox_id=sandbox_id)
        target_workspace = str(workspace_path or "").strip() or self._workspace_root(self.config.e2b_workspace_path)
        await self._ensure_directory(sandbox, target_workspace)
        await self._sync_workspace_tree(sandbox, target_workspace, files)
        return {"sandbox_id": sandbox_id, "workspace_path": target_workspace, "file_count": len(files or {})}

    async def resolve_workspace_path(self, *, sandbox_id: str) -> str | None:
        _ = sandbox_id
        return self._workspace_root(self.config.e2b_workspace_path)
