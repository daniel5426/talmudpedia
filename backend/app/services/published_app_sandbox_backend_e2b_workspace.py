from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePosixPath
from typing import Any, Dict

from app.services.published_app_draft_dev_patching import hash_text
from app.services.published_app_sandbox_backend import PublishedAppSandboxBackendError


class E2BSandboxWorkspaceMixin:
    @staticmethod
    def _normalize_upstream_base_url(host: str) -> str:
        raw = str(host or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw.rstrip("/")
        return f"https://{raw}".rstrip("/")

    @staticmethod
    def _normalize_runtime_path(raw_path: str) -> str:
        cleaned = str(raw_path or "").replace("\\", "/").strip().lstrip("/")
        if not cleaned:
            raise PublishedAppSandboxBackendError("File path is required")
        parts: list[str] = []
        for part in cleaned.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise PublishedAppSandboxBackendError("Path traversal is not allowed")
            parts.append(part)
        normalized = "/".join(parts)
        if not normalized:
            raise PublishedAppSandboxBackendError("File path is required")
        segments = [segment for segment in normalized.split("/") if segment]
        if (
            "node_modules" in segments
            or normalized.startswith(".talmudpedia/")
            or normalized == ".talmudpedia"
            or normalized.startswith(".opencode/.bun/")
            or normalized == ".opencode/.bun"
            or normalized in {".draft-dev.log", ".draft-dev-dependency-hash"}
        ):
            raise PublishedAppSandboxBackendError(f"Path is not editable: {normalized}")
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
        if normalized.startswith(".opencode/.bun/") or normalized == ".opencode/.bun":
            return True
        segments = [segment for segment in normalized.split("/") if segment]
        return "node_modules" in segments

    @staticmethod
    def _workspace_root(config_workspace_path: str) -> str:
        root = str(config_workspace_path or "/workspace").strip() or "/workspace"
        if not root.startswith("/"):
            root = f"/{root}"
        return root.rstrip("/") or "/workspace"

    def _stage_workspace_dir(self) -> str:
        return f"{self._workspace_root(self.config.e2b_workspace_path)}/.talmudpedia/stage/shared/workspace"

    def _publish_workspace_dir(self) -> str:
        return f"{self._workspace_root(self.config.e2b_workspace_path)}/.talmudpedia/publish/current/workspace"

    async def _run_shell(
        self,
        sandbox,
        command: str,
        *,
        cwd: str | None = None,
        timeout_seconds: float = 60,
        background: bool = False,
    ):
        try:
            return await sandbox.commands.run(
                command,
                cwd=cwd,
                timeout=timeout_seconds,
                request_timeout=max(timeout_seconds, 30.0),
                background=background,
            )
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Sandbox command failed: {exc}") from exc

    async def _ensure_directory(self, sandbox, path: str) -> None:
        try:
            await sandbox.files.make_dir(path)
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Failed to create sandbox directory `{path}`: {exc}") from exc

    async def _spawn_detached_shell(
        self,
        sandbox,
        command: str,
        *,
        cwd: str | None = None,
        log_path: str,
    ) -> int:
        quoted_command = shlex.quote(command)
        quoted_log = shlex.quote(log_path)
        shell = (
            "sh -lc "
            + shlex.quote(
                f"nohup sh -lc {quoted_command} >> {quoted_log} 2>&1 < /dev/null & echo $!"
            )
        )
        result = await self._run_shell(
            sandbox,
            shell,
            cwd=cwd,
            timeout_seconds=30,
            background=False,
        )
        pid_raw = str(result.stdout or "").strip().splitlines()
        if not pid_raw:
            raise PublishedAppSandboxBackendError("Failed to start detached sandbox process: missing pid output")
        try:
            return int(pid_raw[-1].strip())
        except Exception as exc:
            raise PublishedAppSandboxBackendError(
                f"Failed to parse detached sandbox process pid from `{pid_raw[-1]}`"
            ) from exc

    async def _list_workspace_paths(self, sandbox, workspace_root: str) -> list[str]:
        quoted_root = shlex.quote(workspace_root)
        result = await self._run_shell(
            sandbox,
            f"cd {quoted_root} && find . -type f | sort",
            cwd=workspace_root,
            timeout_seconds=45,
        )
        stdout = str(result.stdout or "")
        rows: list[str] = []
        for raw in stdout.splitlines():
            line = raw.strip()
            if line.startswith("./"):
                normalized = line[2:]
            else:
                normalized = line.lstrip("/")
            if not normalized or self._is_runtime_ignored_artifact_path(normalized):
                continue
            rows.append(normalized)
        return rows

    async def _collect_workspace_files_from_root(self, sandbox, workspace_root: str) -> Dict[str, str]:
        files: Dict[str, str] = {}
        for rel_path in await self._list_workspace_paths(sandbox, workspace_root):
            content = await sandbox.files.read(f"{workspace_root}/{rel_path}")
            files[rel_path] = str(content)
        return files

    async def _sync_workspace_tree(self, sandbox, workspace_root: str, files: Dict[str, str]) -> None:
        normalized: Dict[str, str] = {}
        for path, content in (files or {}).items():
            clean = str(path or "").replace("\\", "/").strip().lstrip("/")
            if not clean or ".." in clean.split("/"):
                continue
            normalized[clean] = content if isinstance(content, str) else str(content)

        existing_paths = set(await self._list_workspace_paths(sandbox, workspace_root))
        desired_paths = set(normalized.keys())
        for rel_path in sorted(existing_paths - desired_paths, reverse=True):
            try:
                await sandbox.files.remove(f"{workspace_root}/{rel_path}")
            except Exception:
                continue

        if normalized:
            write_entries = [
                {"path": f"{workspace_root}/{path}", "data": content}
                for path, content in normalized.items()
            ]
            try:
                await sandbox.files.write_files(write_entries)
            except Exception as exc:
                raise PublishedAppSandboxBackendError(f"Failed to sync sandbox workspace: {exc}") from exc

    async def _read_dependency_hash_marker(self, sandbox, workspace_root: str) -> str:
        marker_path = f"{workspace_root}/.draft-dev-dependency-hash"
        try:
            content = await sandbox.files.read(marker_path)
        except Exception:
            return ""
        return str(content or "").strip()

    async def _write_dependency_hash_marker(self, sandbox, workspace_root: str, dependency_hash: str) -> None:
        await sandbox.files.write(f"{workspace_root}/.draft-dev-dependency-hash", str(dependency_hash or "").strip())

    async def _must_install_dependencies(self, sandbox, workspace_root: str, dependency_hash: str) -> bool:
        if not await sandbox.files.exists(f"{workspace_root}/node_modules"):
            return True
        return await self._read_dependency_hash_marker(sandbox, workspace_root) != dependency_hash

    async def _run_install(self, sandbox, workspace_root: str) -> None:
        package_lock_exists = await sandbox.files.exists(f"{workspace_root}/package-lock.json")
        command = "npm ci" if package_lock_exists else "npm install --no-audit --no-fund"
        result = await self._run_shell(
            sandbox,
            command,
            cwd=workspace_root,
            timeout_seconds=max(120, float(self.config.e2b_timeout_seconds)),
        )
        if int(result.exit_code or 0) != 0:
            output = str(result.stderr or result.stdout or "").strip()
            if len(output) > 1400:
                output = output[:1400] + "... [truncated]"
            raise PublishedAppSandboxBackendError(f"`{command}` failed with exit code {result.exit_code}: {output}")

    async def _wait_for_port(self, sandbox, port: int, *, timeout_seconds: float = 45) -> None:
        command = (
            "for i in $(seq 1 180); do "
            f"(echo > /dev/tcp/127.0.0.1/{int(port)}) >/dev/null 2>&1 && exit 0; "
            "sleep 0.25; "
            "done; "
            "exit 1"
        )
        result = await self._run_shell(sandbox, command, timeout_seconds=timeout_seconds)
        if int(result.exit_code or 0) != 0:
            raise PublishedAppSandboxBackendError(f"Sandbox service port {port} did not become ready in time.")

    async def _kill_pid_if_present(self, sandbox, pid: int | None) -> None:
        if not pid:
            return
        try:
            await sandbox.commands.kill(pid)
        except Exception:
            return

    def _dev_command(self, *, port: int, preview_base_path: str) -> str:
        template = (os.getenv("APPS_DRAFT_DEV_DEV_COMMAND") or "").strip()
        host = "0.0.0.0"
        if template:
            return template.format(host=host, port=port, base=preview_base_path)
        return " ".join(
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                host,
                "--port",
                str(port),
                "--strictPort",
                "--base",
                shlex.quote(preview_base_path),
            ]
        )

    async def _resolve_workspace_path(self, sandbox, workspace_path: str | None) -> str:
        requested = str(workspace_path or "").strip()
        project_dir = self._workspace_root(self.config.e2b_workspace_path)
        if not requested:
            return project_dir
        raw = requested
        if raw == "/workspace" or raw.startswith("/workspace/"):
            raw = raw[len("/workspace") :].lstrip("/")
        if raw.startswith("/"):
            candidate = PurePosixPath(raw)
        else:
            candidate = PurePosixPath(project_dir) / raw
        normalized = str(candidate)
        if not normalized.startswith(project_dir):
            raise PublishedAppSandboxBackendError("Requested workspace path is invalid or outside sandbox project scope")
        if not await sandbox.files.exists(normalized):
            raise PublishedAppSandboxBackendError(f"Workspace path not found: {normalized}")
        return normalized

    @staticmethod
    def _detect_language(path: str) -> str:
        suffix = PurePosixPath(path).suffix.lower()
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
    ) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        suffix = PurePosixPath(path).suffix.lower()
        patterns: list[tuple[str, str]] = []
        if suffix == ".py":
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
                if matched:
                    symbols.append({"name": matched.group(1), "kind": kind, "line": line_no})
                    break
            if len(symbols) >= max(1, int(max_symbols_per_file)):
                break
        return symbols
