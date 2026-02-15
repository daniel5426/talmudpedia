from __future__ import annotations

import asyncio
import logging
import os
import shlex
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


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
            )
            return {
                "sandbox_id": session_id,
                "preview_url": self._preview_url(port, draft_dev_token),
                "status": "running",
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
                )
            else:
                state.dependency_hash = dependency_hash

            return {"status": "running", "sandbox_id": sandbox_id}

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

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            files = self._collect_project_files(state.project_dir)
            return {
                "sandbox_id": sandbox_id,
                "count": len(files),
                "paths": files[:max(1, int(limit))],
            }

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            if not target.exists() or not target.is_file():
                raise LocalDraftDevRuntimeError(f"File not found: {normalized}")
            content = target.read_text(encoding="utf-8")
            return {"sandbox_id": sandbox_id, "path": normalized, "content": content}

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
                            return {"sandbox_id": sandbox_id, "query": query, "matches": matches}
            return {"sandbox_id": sandbox_id, "query": query, "matches": matches}

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content if isinstance(content, str) else str(content), encoding="utf-8")
            return {"sandbox_id": sandbox_id, "path": normalized, "status": "written"}

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            normalized = self._normalize_runtime_path(path)
            target = state.project_dir / normalized
            if target.exists() and target.is_file():
                target.unlink(missing_ok=True)
                self._prune_empty_dirs(target.parent, state.project_dir)
            return {"sandbox_id": sandbox_id, "path": normalized, "status": "deleted"}

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
            return {"sandbox_id": sandbox_id, "from_path": src, "to_path": dst, "status": "renamed"}

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, object]:
        async with self._lock:
            state = self._require_running_session_locked(sandbox_id)
            files: Dict[str, str] = {}
            for rel_path in self._collect_project_files(state.project_dir):
                files[rel_path] = (state.project_dir / rel_path).read_text(encoding="utf-8", errors="replace")
            return {"sandbox_id": sandbox_id, "files": files, "file_count": len(files)}

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
