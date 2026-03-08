from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.published_app_draft_dev_patching import apply_unified_patch_transaction, hash_text


logger = logging.getLogger(__name__)


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_port_open(host: str, port: int, timeout_seconds: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            return True
    except OSError:
        return False


async def _wait_for_port(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if _is_port_open(host, port):
            return True
        await asyncio.sleep(0.25)
    return _is_port_open(host, port)


@dataclass
class _SessionProcess:
    sandbox_id: str
    project_dir: Path
    port: int
    process: subprocess.Popen
    dependency_hash: str
    preview_base_path: str = "/"
    revision_seq: int = 1


class LocalDraftDevRuntimeError(Exception):
    pass


class LocalDraftDevRuntimeManager:
    def __init__(self) -> None:
        root_dir = (os.getenv("APPS_DRAFT_DEV_LOCAL_ROOT_DIR") or "/tmp/talmudpedia-draft-dev").strip()
        self._root_dir = Path(root_dir).expanduser().resolve()
        self._install_timeout_seconds = int(os.getenv("APPS_DRAFT_DEV_NPM_INSTALL_TIMEOUT_SECONDS", "240"))
        self._startup_timeout_seconds = int(os.getenv("APPS_DRAFT_DEV_STARTUP_TIMEOUT_SECONDS", "45"))
        self._host = (os.getenv("APPS_DRAFT_DEV_HOST") or "127.0.0.1").strip()
        self._state: Dict[str, _SessionProcess] = {}
        self._lock = asyncio.Lock()
        self._bootstrapped = False

    def bootstrap(self) -> None:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        if self._bootstrapped:
            return
        self._reclaim_orphaned_sessions()
        self._bootstrapped = True

    async def stop_all(self) -> None:
        async with self._lock:
            for sandbox_id in list(self._state.keys()):
                await self._stop_session_locked(sandbox_id)

    async def start_session(
        self,
        *,
        session_id: str,
        files: Dict[str, str],
        dependency_hash: str,
        draft_dev_token: str,
        preview_base_path: str = "/",
    ) -> Dict[str, str]:
        async with self._lock:
            self.bootstrap()
            project_dir = self._root_dir / session_id
            project_dir.mkdir(parents=True, exist_ok=True)
            await self._sync_files_locked(project_dir, files)

            must_install = await self._must_install_dependencies_locked(project_dir, dependency_hash)
            if must_install:
                await self._run_install_locked(project_dir)
                self._write_dependency_hash_marker(project_dir, dependency_hash)

            current = self._state.get(session_id)
            if current and current.process.poll() is None:
                return {
                    "sandbox_id": session_id,
                    "preview_url": self._preview_url(current.port, draft_dev_token),
                    "status": "running",
                    "workspace_path": str(current.project_dir),
                    "revision_token": self._current_revision_token(current),
                }
            if current:
                await self._stop_session_locked(session_id)

            port = _pick_free_port()
            process = await self._spawn_vite_process_locked(project_dir, port, preview_base_path=preview_base_path)
            self._state[session_id] = _SessionProcess(
                sandbox_id=session_id,
                project_dir=project_dir,
                port=port,
                process=process,
                dependency_hash=dependency_hash,
                preview_base_path=preview_base_path,
                revision_seq=1,
            )
            return {
                "sandbox_id": session_id,
                "preview_url": self._preview_url(port, draft_dev_token),
                "status": "running",
                "workspace_path": str(project_dir),
                "revision_token": "sandbox-seq-1",
            }

    async def sync_session(
        self,
        *,
        sandbox_id: str,
        files: Dict[str, str],
        dependency_hash: str,
        install_dependencies: bool,
    ) -> Dict[str, str]:
        async with self._lock:
            state = self._state.get(sandbox_id)
            if state is None or state.process.poll() is not None:
                raise LocalDraftDevRuntimeError("Draft dev sandbox is not running")

            await self._sync_files_locked(state.project_dir, files)

            if install_dependencies or dependency_hash != state.dependency_hash:
                await self._run_install_locked(state.project_dir)
                self._write_dependency_hash_marker(state.project_dir, dependency_hash)
                await self._stop_process_locked(state.process)
                restarted = await self._spawn_vite_process_locked(
                    state.project_dir,
                    state.port,
                    preview_base_path=state.preview_base_path,
                )
                self._state[sandbox_id] = _SessionProcess(
                    sandbox_id=sandbox_id,
                    project_dir=state.project_dir,
                    port=state.port,
                    process=restarted,
                    dependency_hash=dependency_hash,
                    preview_base_path=state.preview_base_path,
                    revision_seq=max(1, int(state.revision_seq)) + 1,
                )
            else:
                state.dependency_hash = dependency_hash
                state.revision_seq = max(1, int(state.revision_seq)) + 1

            state = self._require_running_session_locked(sandbox_id)
            return {
                "status": "running",
                "sandbox_id": sandbox_id,
                "revision_token": self._current_revision_token(state),
            }

    async def heartbeat_session(self, *, sandbox_id: str) -> Dict[str, str]:
        async with self._lock:
            state = self._state.get(sandbox_id)
            if state is None or state.process.poll() is not None:
                raise LocalDraftDevRuntimeError("Draft dev sandbox is not running")
            return {"status": "running", "sandbox_id": sandbox_id}

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, str]:
        async with self._lock:
            await self._stop_session_locked(sandbox_id)
            return {"status": "stopped", "sandbox_id": sandbox_id}

    async def resolve_project_dir(self, *, sandbox_id: str) -> str | None:
        async with self._lock:
            state = self._state.get(sandbox_id)
            if state is None or state.process.poll() is not None:
                return None
            return str(state.project_dir)

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            files = self._collect_project_files(state.project_dir)
            return {
                "sandbox_id": sandbox_id,
                "count": len(files),
                "paths": files[:max(1, int(limit))],
                "revision_token": self._current_revision_token(state),
            }

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            if not target.exists() or not target.is_file():
                raise LocalDraftDevRuntimeError(f"File not found: {normalized}")
            content = target.read_text(encoding="utf-8")
            return {
                "sandbox_id": sandbox_id,
                "path": normalized,
                "content": content,
                "size_bytes": len(content.encode("utf-8")),
                "sha256": hash_text(content),
                "revision_token": self._current_revision_token(state),
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
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            if not target.exists() or not target.is_file():
                raise LocalDraftDevRuntimeError(f"File not found: {normalized}")
            source = target.read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
            if not lines:
                return {
                    "sandbox_id": sandbox_id,
                    "path": normalized,
                    "start_line": 1,
                    "end_line": 1,
                    "content": "",
                    "line_count": 0,
                    "truncated": False,
                    "size_bytes": 0,
                    "sha256": hash_text(source),
                    "revision_token": self._current_revision_token(state),
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
            if with_line_numbers:
                rendered = [f"{effective_start + idx}: {line}" for idx, line in enumerate(selected)]
            else:
                rendered = selected

            limit = max(256, int(max_bytes or 12000))
            content = "\n".join(rendered)
            encoded = content.encode("utf-8")
            truncated = False
            if len(encoded) > limit:
                content = encoded[:limit].decode("utf-8", errors="ignore")
                truncated = True

            return {
                "sandbox_id": sandbox_id,
                "path": normalized,
                "start_line": effective_start,
                "end_line": effective_end,
                "content": content,
                "line_count": len(selected),
                "truncated": truncated,
                "size_bytes": len(content.encode("utf-8")),
                "sha256": hash_text(source),
                "revision_token": self._current_revision_token(state),
            }

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            needle = (query or "").strip().lower()
            if not needle:
                return {"sandbox_id": sandbox_id, "query": query, "matches": []}
            matches: list[dict[str, object]] = []
            for rel_path in self._collect_project_files(state.project_dir):
                source = (state.project_dir / rel_path).read_text(encoding="utf-8", errors="replace")
                for line_no, line in enumerate(source.splitlines(), start=1):
                    if needle in line.lower():
                        matches.append({"path": rel_path, "line": line_no, "preview": line[:220]})
                        if len(matches) >= max(1, int(max_results)):
                            return {
                                "sandbox_id": sandbox_id,
                                "query": query,
                                "matches": matches,
                                "revision_token": self._current_revision_token(state),
                            }
            return {
                "sandbox_id": sandbox_id,
                "query": query,
                "matches": matches,
                "revision_token": self._current_revision_token(state),
            }

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            limit_value = max(1, int(limit))
            query_text = (query or "").strip().lower()
            rows: list[dict[str, object]] = []
            total_size = 0
            for rel_path in self._collect_project_files(state.project_dir):
                source = (state.project_dir / rel_path).read_text(encoding="utf-8", errors="replace")
                size_bytes = len(source.encode("utf-8"))
                total_size += size_bytes
                symbols = self._extract_symbol_outline(source, rel_path, max_symbols_per_file=max_symbols_per_file)
                language = self._detect_language(rel_path)
                score = 0
                if query_text:
                    if query_text in rel_path.lower():
                        score += 4
                    if query_text in source.lower():
                        score += 2
                    if any(query_text in str(item.get("name", "")).lower() for item in symbols):
                        score += 3
                    if score <= 0:
                        continue
                rows.append(
                    {
                        "path": rel_path,
                        "size_bytes": size_bytes,
                        "sha256": hash_text(source),
                        "language": language,
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
                "files": rows[:limit_value],
                "revision_token": self._current_revision_token(state),
            }

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content if isinstance(content, str) else str(content), encoding="utf-8")
            revision_token = self._bump_revision_token(state)
            return {"sandbox_id": sandbox_id, "path": normalized, "status": "written", "revision_token": revision_token}

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            if target.exists() and target.is_file():
                target.unlink(missing_ok=True)
                self._prune_empty_dirs(target.parent, state.project_dir)
                revision_token = self._bump_revision_token(state)
            else:
                revision_token = self._current_revision_token(state)
            return {"sandbox_id": sandbox_id, "path": normalized, "status": "deleted", "revision_token": revision_token}

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            src = self._normalize_runtime_path(from_path)
            dst = self._normalize_runtime_path(to_path)
            source = state.project_dir / src
            target = state.project_dir / dst
            if not source.exists() or not source.is_file():
                raise LocalDraftDevRuntimeError(f"Source file not found: {src}")
            if target.exists() and target != source:
                raise LocalDraftDevRuntimeError(f"Target already exists: {dst}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            self._prune_empty_dirs(source.parent, state.project_dir)
            revision_token = self._bump_revision_token(state)
            return {
                "sandbox_id": sandbox_id,
                "from_path": src,
                "to_path": dst,
                "status": "renamed",
                "revision_token": revision_token,
            }

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, object] | None = None,
        preconditions: dict[str, object] | None = None,
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            patch_text = patch if isinstance(patch, str) else str(patch or "")
            max_patch_bytes = int(os.getenv("APPS_CODING_AGENT_MAX_PATCH_BYTES", "240000"))
            if len(patch_text.encode("utf-8")) > max_patch_bytes:
                return {
                    "ok": False,
                    "code": "PATCH_TOO_LARGE",
                    "summary": f"Patch exceeds size limit ({max_patch_bytes} bytes)",
                    "failures": [],
                    "applied_files": [],
                    "revision_token": self._current_revision_token(state),
                }

            def _normalize_path(path_value: str) -> str:
                return self._normalize_runtime_path(path_value)

            def _read_file(path_value: str) -> str | None:
                target = state.project_dir / path_value
                if not target.exists() or not target.is_file():
                    return None
                return target.read_text(encoding="utf-8", errors="replace")

            try:
                result = apply_unified_patch_transaction(
                    patch=patch_text,
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
                    "revision_token": self._current_revision_token(state),
                }

            writes = result.get("writes") if isinstance(result.get("writes"), dict) else {}
            deletes = result.get("deletes") if isinstance(result.get("deletes"), list) else []
            has_changes = False
            for path_value, content in writes.items():
                target = state.project_dir / str(path_value)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content if isinstance(content, str) else str(content), encoding="utf-8")
                has_changes = True
            for path_value in deletes:
                target = state.project_dir / str(path_value)
                if target.exists() and target.is_file():
                    target.unlink(missing_ok=True)
                    self._prune_empty_dirs(target.parent, state.project_dir)
                    has_changes = True

            response = {key: value for key, value in result.items() if key not in {"writes", "deletes"}}
            response["revision_token"] = self._bump_revision_token(state) if has_changes else self._current_revision_token(state)
            response["metrics"] = {
                "patch_bytes": len(patch_text.encode("utf-8")),
                "applied_file_count": len(response.get("applied_files") or []),
                "failure_count": len(response.get("failures") or []),
                "edit_latency_ms": 0,
            }
            return response

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            files = self._collect_workspace_files_from_root(state.project_dir)
            return {
                "sandbox_id": sandbox_id,
                "files": files,
                "file_count": len(files),
                "revision_token": self._current_revision_token(state),
            }

    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            stage_workspace = self._stage_workspace_dir(project_dir=state.project_dir)
            live_files: Dict[str, str] = {}
            if bool(reset):
                live_files = self._collect_workspace_files_from_root(state.project_dir)
                await self._sync_files_locked(stage_workspace, live_files)
            elif not stage_workspace.exists() or not stage_workspace.is_dir():
                live_files = self._collect_workspace_files_from_root(state.project_dir)
                await self._sync_files_locked(stage_workspace, live_files)
            return {
                "sandbox_id": sandbox_id,
                "reset": bool(reset),
                "live_workspace_path": str(state.project_dir),
                "stage_workspace_path": str(stage_workspace),
                "workspace_path": str(stage_workspace),
                "file_count": len(live_files),
                "revision_token": self._current_revision_token(state),
            }

    async def snapshot_workspace(
        self,
        *,
        sandbox_id: str,
        workspace: str = "live",
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            workspace_key = str(workspace or "live").strip().lower() or "live"
            workspace_root = state.project_dir
            if workspace_key == "stage":
                workspace_root = self._stage_workspace_dir(project_dir=state.project_dir)
                if not workspace_root.exists() or not workspace_root.is_dir():
                    raise LocalDraftDevRuntimeError("Stage workspace is not prepared")
            elif workspace_key != "live":
                raise LocalDraftDevRuntimeError(f"Unsupported workspace scope: {workspace}")
            files = self._collect_workspace_files_from_root(workspace_root)
            return {
                "sandbox_id": sandbox_id,
                "workspace": workspace_key,
                "workspace_path": str(workspace_root),
                "files": files,
                "file_count": len(files),
                "revision_token": self._current_revision_token(state),
            }

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            stage_workspace = self._stage_workspace_dir(project_dir=state.project_dir)
            if not stage_workspace.exists() or not stage_workspace.is_dir():
                raise LocalDraftDevRuntimeError("Stage workspace is not prepared")
            stage_files = self._collect_workspace_files_from_root(stage_workspace)
            await self._sync_files_locked(state.project_dir, stage_files)
            return {
                "sandbox_id": sandbox_id,
                "live_workspace_path": str(state.project_dir),
                "stage_workspace_path": str(stage_workspace),
                "promoted_file_count": len(stage_files),
                "revision_token": self._bump_revision_token(state),
            }

    async def prepare_publish_workspace(self, *, sandbox_id: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            publish_workspace = self._publish_workspace_dir(project_dir=state.project_dir)
            live_files = self._collect_workspace_files_from_root(state.project_dir)
            await self._sync_files_locked(publish_workspace, live_files)
            return {
                "sandbox_id": sandbox_id,
                "workspace": "publish",
                "live_workspace_path": str(state.project_dir),
                "publish_workspace_path": str(publish_workspace),
                "workspace_path": str(publish_workspace),
                "files": live_files,
                "file_count": len(live_files),
                "revision_token": self._current_revision_token(state),
            }

    async def prepare_publish_dependencies(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            publish_workspace = self._resolve_workspace_path_locked(
                state=state,
                workspace_path=workspace_path,
                require_exists=True,
                require_dir=True,
            )
            live_workspace = state.project_dir

            publish_package_json = publish_workspace / "package.json"
            live_package_json = live_workspace / "package.json"
            if not publish_package_json.exists():
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "no_package_json",
                    "strategy": "none",
                    "reason": "publish workspace has no package.json",
                    "revision_token": self._current_revision_token(state),
                }
            if not live_package_json.exists():
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "fallback_required",
                    "strategy": "none",
                    "reason": "live workspace has no package.json",
                    "revision_token": self._current_revision_token(state),
                }

            manifests_match, manifest_reason = self._publish_dependency_manifests_match(
                live_workspace=live_workspace,
                publish_workspace=publish_workspace,
            )
            if not manifests_match:
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "incompatible_lockfile",
                    "strategy": "none",
                    "reason": manifest_reason,
                    "revision_token": self._current_revision_token(state),
                }

            live_node_modules = live_workspace / "node_modules"
            if not live_node_modules.exists() or not live_node_modules.is_dir():
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "missing_live_node_modules",
                    "strategy": "none",
                    "reason": "live workspace node_modules is missing",
                    "revision_token": self._current_revision_token(state),
                }

            publish_node_modules = publish_workspace / "node_modules"
            try:
                if (
                    publish_node_modules.is_symlink()
                    and publish_node_modules.resolve(strict=False) == live_node_modules.resolve(strict=False)
                ):
                    return {
                        "sandbox_id": sandbox_id,
                        "workspace_path": str(publish_workspace),
                        "live_workspace_path": str(live_workspace),
                        "status": "reused",
                        "strategy": "symlink",
                        "reason": "publish workspace already links to live node_modules",
                        "revision_token": self._current_revision_token(state),
                    }
            except Exception:
                pass

            self._remove_path_if_exists(publish_node_modules)

            symlink_error: str | None = None
            try:
                publish_node_modules.parent.mkdir(parents=True, exist_ok=True)
                publish_node_modules.symlink_to(live_node_modules, target_is_directory=True)
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "reused",
                    "strategy": "symlink",
                    "reason": "reused live workspace node_modules via symlink",
                    "revision_token": self._current_revision_token(state),
                }
            except Exception as exc:
                symlink_error = str(exc)
                self._remove_path_if_exists(publish_node_modules)

            try:
                shutil.copytree(live_node_modules, publish_node_modules, symlinks=True)
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "reused",
                    "strategy": "copy",
                    "reason": "reused live workspace node_modules via copy fallback",
                    "revision_token": self._current_revision_token(state),
                }
            except Exception as exc:
                self._remove_path_if_exists(publish_node_modules)
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": str(publish_workspace),
                    "live_workspace_path": str(live_workspace),
                    "status": "fallback_required",
                    "strategy": "none",
                    "reason": (
                        "dependency reuse unavailable; "
                        f"symlink_error={symlink_error or 'unknown'}; copy_error={exc}"
                    ),
                    "revision_token": self._current_revision_token(state),
                }

    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            archive_root = self._resolve_workspace_path_locked(
                state=state,
                workspace_path=workspace_path,
                require_exists=True,
                require_dir=True,
            )
            fmt = str(format or "tar.gz").strip().lower()
            if fmt != "tar.gz":
                raise LocalDraftDevRuntimeError(f"Unsupported archive format: {format}")
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
                tar.add(str(archive_root), arcname=".")
            payload = buffer.getvalue()
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": str(archive_root),
                "format": "tar.gz",
                "archive_base64": base64.b64encode(payload).decode("ascii"),
                "size_bytes": len(payload),
                "revision_token": self._current_revision_token(state),
            }

    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            target_workspace = self._resolve_workspace_path_locked(
                state=state,
                workspace_path=workspace_path,
                require_exists=False,
                require_dir=False,
            )
            target_workspace.mkdir(parents=True, exist_ok=True)
            await self._sync_files_locked(target_workspace, files)
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": str(target_workspace),
                "file_count": len(files or {}),
                "revision_token": self._current_revision_token(state),
            }

    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        workspace_path: str | None = None,
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            if not command:
                raise LocalDraftDevRuntimeError("Command is required")
            resolved_cwd = self._resolve_workspace_path_locked(
                state=state,
                workspace_path=workspace_path,
                require_exists=True,
                require_dir=True,
            )
            revision_token = self._current_revision_token(state)

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(resolved_cwd),
            env=dict(os.environ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=float(timeout_seconds))
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise LocalDraftDevRuntimeError(
                f"Command timed out after {timeout_seconds}s: {' '.join(command)}"
            )
        out_text = (stdout or b"").decode("utf-8", errors="replace")
        err_text = (stderr or b"").decode("utf-8", errors="replace")
        if len(out_text) > max_output_bytes:
            out_text = out_text[:max_output_bytes] + "... [truncated]"
        if len(err_text) > max_output_bytes:
            err_text = err_text[:max_output_bytes] + "... [truncated]"
        return {
            "sandbox_id": sandbox_id,
            "command": command,
            "code": int(process.returncode or 0),
            "stdout": out_text,
            "stderr": err_text,
            "workspace_path": str(resolved_cwd),
            "revision_token": revision_token,
        }

    def _preview_url(self, port: int, draft_dev_token: str) -> str:
        return f"http://{self._host}:{port}/?draft_dev_token={draft_dev_token}"

    def _stage_workspace_dir(self, *, project_dir: Path) -> Path:
        return project_dir / ".talmudpedia" / "stage" / "shared" / "workspace"

    def _publish_workspace_dir(self, *, project_dir: Path) -> Path:
        return project_dir / ".talmudpedia" / "publish" / "current" / "workspace"

    def _resolve_workspace_path_locked(
        self,
        *,
        state: _SessionProcess,
        workspace_path: str | None,
        require_exists: bool = True,
        require_dir: bool = True,
    ) -> Path:
        requested = str(workspace_path or "").strip()
        project_dir = state.project_dir.resolve()
        if not requested:
            candidate = project_dir
        else:
            raw = requested
            if raw == "/workspace" or raw.startswith("/workspace/"):
                raw = raw[len("/workspace") :].lstrip("/")
            if os.path.isabs(raw):
                candidate = Path(raw).expanduser().resolve()
            else:
                candidate = (project_dir / raw).resolve()
        try:
            in_scope = os.path.commonpath([str(project_dir), str(candidate)]) == str(project_dir)
        except Exception:
            in_scope = False
        if not in_scope:
            raise LocalDraftDevRuntimeError("Requested workspace path is invalid or outside sandbox project scope")
        if require_exists and not candidate.exists():
            raise LocalDraftDevRuntimeError(f"Workspace path not found: {candidate}")
        if require_dir and require_exists and not candidate.is_dir():
            raise LocalDraftDevRuntimeError(f"Workspace path is not a directory: {candidate}")
        return candidate

    def _collect_workspace_files_from_root(self, workspace_root: Path) -> Dict[str, str]:
        files: Dict[str, str] = {}
        if not workspace_root.exists() or not workspace_root.is_dir():
            return files
        for existing in sorted(workspace_root.rglob("*")):
            if not existing.is_file():
                continue
            relative = existing.relative_to(workspace_root).as_posix()
            if self._is_runtime_ignored_artifact_path(relative):
                continue
            files[relative] = existing.read_text(encoding="utf-8", errors="replace")
        return files

    def _normalize_runtime_path(self, raw_path: str) -> str:
        cleaned = (raw_path or "").replace("\\", "/").strip().lstrip("/")
        if not cleaned:
            raise LocalDraftDevRuntimeError("File path is required")
        parts: list[str] = []
        for part in cleaned.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise LocalDraftDevRuntimeError("Path traversal is not allowed")
            parts.append(part)
        normalized = "/".join(parts)
        if not normalized:
            raise LocalDraftDevRuntimeError("File path is required")
        segments = [segment for segment in normalized.split("/") if segment]
        if (
            "node_modules" in segments
            or normalized.startswith(".talmudpedia/")
            or normalized == ".talmudpedia"
            or normalized.startswith(".opencode/.bun/")
            or normalized == ".opencode/.bun"
            or normalized in {".draft-dev.log", ".draft-dev-dependency-hash"}
        ):
            raise LocalDraftDevRuntimeError(f"Path is not editable: {normalized}")
        return normalized

    @staticmethod
    def _is_runtime_ignored_artifact_path(path: str) -> bool:
        normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
        if not normalized:
            return True
        if normalized in {".draft-dev.log", ".draft-dev-dependency-hash"}:
            return True
        if normalized.startswith(".talmudpedia/") or normalized == ".talmudpedia":
            return True
        segments = [segment for segment in normalized.split("/") if segment]
        if "node_modules" in segments:
            return True
        if normalized.startswith(".opencode/.bun/") or normalized == ".opencode/.bun":
            return True
        return False

    def _collect_project_files(self, project_dir: Path) -> list[str]:
        paths: list[str] = []
        for existing in sorted(project_dir.rglob("*")):
            if not existing.is_file():
                continue
            relative = existing.relative_to(project_dir).as_posix()
            if self._is_runtime_ignored_artifact_path(relative):
                continue
            paths.append(relative)
        return paths

    def _detect_language(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        mapping = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".json": "json",
            ".md": "markdown",
            ".css": "css",
            ".scss": "scss",
            ".html": "html",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".sql": "sql",
            ".sh": "shell",
        }
        return mapping.get(suffix, "text")

    def _extract_symbol_outline(
        self,
        source: str,
        path: str,
        *,
        max_symbols_per_file: int = 16,
    ) -> list[dict[str, object]]:
        symbols: list[dict[str, object]] = []
        suffix = Path(path).suffix.lower()
        patterns: list[tuple[str, str]] = []
        if suffix in {".py"}:
            patterns = [
                (r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
                (r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "function"),
            ]
        elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
            patterns = [
                (r"^\s*export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
                (r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
                (r"^\s*export\s+function\s+([A-Za-z_][A-Za-z0-9_]*)", "function"),
                (r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)", "function"),
                (r"^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(", "function"),
            ]
        if not patterns:
            return symbols

        for line_no, line in enumerate(source.splitlines(), start=1):
            for pattern, kind in patterns:
                matched = re.search(pattern, line)
                if not matched:
                    continue
                symbols.append({"name": matched.group(1), "kind": kind, "line": line_no})
                break
            if len(symbols) >= max(1, int(max_symbols_per_file)):
                break
        return symbols

    def _current_revision_token(self, state: _SessionProcess) -> str:
        return f"sandbox-seq-{max(1, int(state.revision_seq))}"

    def _bump_revision_token(self, state: _SessionProcess) -> str:
        state.revision_seq = max(1, int(state.revision_seq)) + 1
        return self._current_revision_token(state)

    def _require_running_session_locked(self, sandbox_id: str) -> _SessionProcess:
        state = self._state.get(sandbox_id)
        if state is None or state.process.poll() is not None:
            raise LocalDraftDevRuntimeError("Draft dev sandbox is not running")
        return state

    def _prune_empty_dirs(self, start_dir: Path, root_dir: Path) -> None:
        current = start_dir
        while current != root_dir and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    async def _stop_session_locked(self, sandbox_id: str) -> None:
        state = self._state.pop(sandbox_id, None)
        if state is None:
            return
        await self._stop_process_locked(state.process)
        self._clear_process_metadata(state.project_dir)

    async def _stop_process_locked(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        self._terminate_process_group(process.pid, sig=signal.SIGTERM)
        try:
            await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=8)
        except asyncio.TimeoutError:
            self._terminate_process_group(process.pid, sig=signal.SIGKILL)
            await asyncio.to_thread(process.wait)

    async def _spawn_vite_process_locked(
        self,
        project_dir: Path,
        port: int,
        *,
        preview_base_path: str = "/",
    ) -> subprocess.Popen:
        command = self._resolve_dev_command(port, preview_base_path=preview_base_path)
        log_path = project_dir / ".draft-dev.log"
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(project_dir),
                env=os.environ.copy(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        ready = await _wait_for_port(self._host, port, timeout_seconds=float(self._startup_timeout_seconds))
        if not ready:
            await self._stop_process_locked(process)
            raise LocalDraftDevRuntimeError(
                f"Draft dev Vite server did not become ready on {self._host}:{port}. "
                f"See {log_path} for details."
            )
        self._write_process_metadata(project_dir=project_dir, pid=process.pid, port=port)
        return process

    def _resolve_dev_command(self, port: int, *, preview_base_path: str = "/") -> list[str]:
        template = (os.getenv("APPS_DRAFT_DEV_DEV_COMMAND") or "").strip()
        if template:
            return shlex.split(template.format(host=self._host, port=port, base=preview_base_path))
        return [
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            self._host,
            "--port",
            str(port),
            "--strictPort",
            "--base",
            preview_base_path,
        ]

    async def _must_install_dependencies_locked(self, project_dir: Path, dependency_hash: str) -> bool:
        node_modules = project_dir / "node_modules"
        marker = self._read_dependency_hash_marker(project_dir)
        if not node_modules.exists() or not node_modules.is_dir():
            return True
        return marker != dependency_hash

    async def _run_install_locked(self, project_dir: Path) -> None:
        has_lockfile = (project_dir / "package-lock.json").exists()
        command = ["npm", "ci"] if has_lockfile else ["npm", "install", "--no-audit", "--no-fund"]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=float(self._install_timeout_seconds),
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise LocalDraftDevRuntimeError(
                f"`{' '.join(command)}` timed out after {self._install_timeout_seconds}s"
            )
        if (process.returncode or 0) != 0:
            output = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            if len(output) > 1400:
                output = output[:1400] + "... [truncated]"
            raise LocalDraftDevRuntimeError(
                f"`{' '.join(command)}` failed with exit code {process.returncode}: {output}"
            )

    async def _sync_files_locked(self, project_dir: Path, files: Dict[str, str]) -> None:
        normalized: Dict[str, str] = {}
        for path, content in (files or {}).items():
            clean = (path or "").replace("\\", "/").strip().lstrip("/")
            if not clean or ".." in clean.split("/"):
                continue
            normalized[clean] = content if isinstance(content, str) else str(content)

        for existing in sorted(project_dir.rglob("*"), reverse=True):
            relative = existing.relative_to(project_dir).as_posix()
            if self._is_runtime_ignored_artifact_path(relative):
                continue
            if existing.is_file() and relative not in normalized:
                existing.unlink(missing_ok=True)
            elif existing.is_dir() and relative and not any(
                item.startswith(relative + "/") for item in normalized.keys()
            ):
                try:
                    existing.rmdir()
                except OSError:
                    pass

        for path, content in normalized.items():
            target = project_dir / path
            if target.exists() and target.is_file():
                try:
                    if target.read_text(encoding="utf-8") == content:
                        continue
                except Exception:
                    # Fall through to rewrite if we cannot read as UTF-8.
                    pass
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    @staticmethod
    def _publish_dependency_manifests_match(*, live_workspace: Path, publish_workspace: Path) -> tuple[bool, str]:
        paths_to_compare = ["package.json", "package-lock.json"]
        for relative in paths_to_compare:
            live_path = live_workspace / relative
            publish_path = publish_workspace / relative
            live_exists = live_path.exists()
            publish_exists = publish_path.exists()
            if live_exists != publish_exists:
                return False, f"{relative} presence differs between live and publish workspaces"
            if not live_exists:
                continue
            try:
                live_bytes = live_path.read_bytes()
                publish_bytes = publish_path.read_bytes()
            except Exception as exc:
                return False, f"failed to read {relative} for dependency reuse validation: {exc}"
            if live_bytes != publish_bytes:
                return False, f"{relative} differs between live and publish workspaces"
        return True, "dependency manifests match"

    @staticmethod
    def _remove_path_if_exists(target: Path) -> None:
        try:
            if target.is_symlink() or target.is_file():
                target.unlink(missing_ok=True)
                return
            if target.exists() and target.is_dir():
                shutil.rmtree(target)
        except FileNotFoundError:
            return

    def _read_dependency_hash_marker(self, project_dir: Path) -> str:
        marker = project_dir / ".draft-dev-dependency-hash"
        try:
            return marker.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _write_dependency_hash_marker(self, project_dir: Path, dependency_hash: str) -> None:
        marker = project_dir / ".draft-dev-dependency-hash"
        marker.write_text((dependency_hash or "").strip(), encoding="utf-8")

    @staticmethod
    def _terminate_process_group(pid: int, *, sig: signal.Signals) -> None:
        try:
            os.killpg(int(pid), sig)
        except ProcessLookupError:
            return
        except Exception:
            try:
                os.kill(int(pid), sig)
            except ProcessLookupError:
                return
            except Exception:
                return

    @staticmethod
    def _process_exists(pid: int) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return True

    @staticmethod
    def _process_metadata_path(project_dir: Path) -> Path:
        return project_dir / ".talmudpedia" / "draft-dev-process.json"

    def _write_process_metadata(self, *, project_dir: Path, pid: int, port: int) -> None:
        payload = {
            "pid": int(pid),
            "port": int(port),
            "project_dir": str(project_dir),
        }
        target = self._process_metadata_path(project_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _clear_process_metadata(self, project_dir: Path) -> None:
        self._process_metadata_path(project_dir).unlink(missing_ok=True)

    def _reclaim_orphaned_sessions(self) -> None:
        for child in self._root_dir.iterdir():
            if not child.is_dir():
                continue
            metadata_path = self._process_metadata_path(child)
            if not metadata_path.exists():
                continue
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                metadata_path.unlink(missing_ok=True)
                continue
            pid = int(payload.get("pid") or 0)
            if pid > 0 and self._process_exists(pid):
                logger.info(
                    "Reclaiming orphaned local draft-dev process pid=%s project_dir=%s",
                    pid,
                    child,
                )
                self._terminate_process_group(pid, sig=signal.SIGTERM)
            metadata_path.unlink(missing_ok=True)


_LOCAL_RUNTIME_MANAGER: Optional[LocalDraftDevRuntimeManager] = None


def get_local_draft_dev_runtime_manager() -> LocalDraftDevRuntimeManager:
    global _LOCAL_RUNTIME_MANAGER
    if _LOCAL_RUNTIME_MANAGER is None:
        _LOCAL_RUNTIME_MANAGER = LocalDraftDevRuntimeManager()
    return _LOCAL_RUNTIME_MANAGER
