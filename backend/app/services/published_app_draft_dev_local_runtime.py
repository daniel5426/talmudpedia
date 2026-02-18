from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

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

    def bootstrap(self) -> None:
        self._root_dir.mkdir(parents=True, exist_ok=True)

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
                    "revision_token": self._current_revision_token(current),
                }
            if current:
                await self._stop_session_locked(session_id)

            port = _pick_free_port()
            process = await self._spawn_vite_process_locked(project_dir, port)
            self._state[session_id] = _SessionProcess(
                sandbox_id=session_id,
                project_dir=project_dir,
                port=port,
                process=process,
                dependency_hash=dependency_hash,
                revision_seq=1,
            )
            return {
                "sandbox_id": session_id,
                "preview_url": self._preview_url(port, draft_dev_token),
                "status": "running",
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
                restarted = await self._spawn_vite_process_locked(state.project_dir, state.port)
                self._state[sandbox_id] = _SessionProcess(
                    sandbox_id=sandbox_id,
                    project_dir=state.project_dir,
                    port=state.port,
                    process=restarted,
                    dependency_hash=dependency_hash,
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
            files: Dict[str, str] = {}
            for rel_path in self._collect_project_files(state.project_dir):
                files[rel_path] = (state.project_dir / rel_path).read_text(encoding="utf-8", errors="replace")
            return {
                "sandbox_id": sandbox_id,
                "files": files,
                "file_count": len(files),
                "revision_token": self._current_revision_token(state),
            }

    async def run_command(
        self,
        *,
        sandbox_id: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
    ) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            if not command:
                raise LocalDraftDevRuntimeError("Command is required")
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(state.project_dir),
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
                "revision_token": self._current_revision_token(state),
            }

    def _preview_url(self, port: int, draft_dev_token: str) -> str:
        return f"http://{self._host}:{port}/?draft_dev_token={draft_dev_token}"

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
        if normalized.startswith("node_modules/") or normalized in {".draft-dev.log", ".draft-dev-dependency-hash"}:
            raise LocalDraftDevRuntimeError(f"Path is not editable: {normalized}")
        return normalized

    def _collect_project_files(self, project_dir: Path) -> list[str]:
        paths: list[str] = []
        for existing in sorted(project_dir.rglob("*")):
            if not existing.is_file():
                continue
            relative = existing.relative_to(project_dir).as_posix()
            if relative.startswith("node_modules/") or relative == "node_modules":
                continue
            if relative in {".draft-dev.log", ".draft-dev-dependency-hash"}:
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

    async def _stop_process_locked(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=8)
        except asyncio.TimeoutError:
            process.kill()
            await asyncio.to_thread(process.wait)

    async def _spawn_vite_process_locked(self, project_dir: Path, port: int) -> subprocess.Popen:
        command = self._resolve_dev_command(port)
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
        return process

    def _resolve_dev_command(self, port: int) -> list[str]:
        template = (os.getenv("APPS_DRAFT_DEV_DEV_COMMAND") or "").strip()
        if template:
            return shlex.split(template.format(host=self._host, port=port))
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
            if relative.startswith("node_modules/") or relative == "node_modules":
                continue
            if relative in {".draft-dev.log", ".draft-dev-dependency-hash"}:
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

    def _read_dependency_hash_marker(self, project_dir: Path) -> str:
        marker = project_dir / ".draft-dev-dependency-hash"
        try:
            return marker.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _write_dependency_hash_marker(self, project_dir: Path, dependency_hash: str) -> None:
        marker = project_dir / ".draft-dev-dependency-hash"
        marker.write_text((dependency_hash or "").strip(), encoding="utf-8")


_LOCAL_RUNTIME_MANAGER: Optional[LocalDraftDevRuntimeManager] = None


def get_local_draft_dev_runtime_manager() -> LocalDraftDevRuntimeManager:
    global _LOCAL_RUNTIME_MANAGER
    if _LOCAL_RUNTIME_MANAGER is None:
        _LOCAL_RUNTIME_MANAGER = LocalDraftDevRuntimeManager()
    return _LOCAL_RUNTIME_MANAGER
