from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
from typing import Any, AsyncGenerator, Dict
from urllib.parse import urlencode

import httpx

from app.services.published_app_sandbox_backend import (
    PublishedAppSandboxBackend,
    PublishedAppSandboxBackendError,
)
from app.services.published_app_sprite_proxy_tunnel import get_sprite_proxy_tunnel_manager


_EXIT_MARKER = "__CODEX_EXIT_CODE__="
_REVISION_FILE = ".talmudpedia/runtime-revision-token"
_DEPENDENCY_HASH_FILE = ".talmudpedia/dependency-hash"
_SYNC_IGNORE_PREFIXES = (".talmudpedia/", ".opencode/", "node_modules/")
_EXEC_CONTROL_TRANSLATION = {
    codepoint: None
    for codepoint in range(32)
    if chr(codepoint) not in {"\n", "\r", "\t"}
}


class SpriteSandboxBackend(PublishedAppSandboxBackend):
    backend_name = "sprite"
    is_remote = True

    def _api_base(self) -> str:
        return str(self.config.sprite_api_base_url or "https://api.sprites.dev").rstrip("/")

    def _api_token(self) -> str:
        token = str(self.config.sprite_api_token or "").strip()
        if not token:
            raise PublishedAppSandboxBackendError("Sprite API token is not configured.")
        return token

    def _headers(self, *, json_content: bool = True) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_token()}"}
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _sprite_name(*, prefix: str, app_id: str) -> str:
        digest = hashlib.sha256(str(app_id).encode("utf-8")).hexdigest()[:16]
        normalized_prefix = re.sub(r"[^a-z0-9-]+", "-", str(prefix or "app-builder").strip().lower()).strip("-")
        normalized_prefix = normalized_prefix[:32] or "app-builder"
        return f"{normalized_prefix}-{digest}"

    @staticmethod
    def _service_command(script: str) -> dict[str, Any]:
        return {"cmd": "bash", "args": ["-lc", script]}

    @staticmethod
    def _sanitize_exec_output(raw: str) -> str:
        return str(raw or "").translate(_EXEC_CONTROL_TRANSLATION)

    def _live_workspace_path(self) -> str:
        return str(self.config.sprite_workspace_path or "/home/sprite/app").rstrip("/") or "/home/sprite/app"

    def _stage_workspace_path(self) -> str:
        explicit = str(self.config.sprite_stage_workspace_path or "").strip()
        if explicit:
            return explicit.rstrip("/")
        return "/home/sprite/.talmudpedia/stage/current/workspace"

    def _publish_workspace_path(self) -> str:
        explicit = str(self.config.sprite_publish_workspace_path or "").strip()
        if explicit:
            return explicit.rstrip("/")
        return "/home/sprite/.talmudpedia/publish/current/workspace"

    def _preview_service_name(self) -> str:
        return str(self.config.sprite_preview_service_name or "builder-preview").strip() or "builder-preview"

    def _opencode_service_name(self) -> str:
        return str(self.config.sprite_opencode_service_name or "opencode").strip() or "opencode"

    def _preview_port(self) -> int:
        return max(1024, int(self.config.sprite_preview_port or 8080))

    def _opencode_port(self) -> int:
        return max(1024, int(self.config.sprite_opencode_port or 4141))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | None = None,
        json_payload: dict[str, Any] | None = None,
        content: bytes | None = None,
        expect_json: bool = True,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any] | str:
        url = f"{self._api_base()}{path}"
        timeout = httpx.Timeout(timeout_seconds or self.config.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=self._headers(json_content=(content is None)),
                    json=json_payload,
                    content=content,
                )
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Sprite request failed: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise PublishedAppSandboxBackendError(
                f"Sprite request failed ({response.status_code}) for {path}: {detail}"
            )
        if not expect_json:
            return response.text
        try:
            payload = response.json()
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Sprite returned invalid JSON for {path}") from exc
        if not isinstance(payload, dict):
            raise PublishedAppSandboxBackendError(f"Sprite returned invalid payload for {path}")
        return payload

    async def _get_sprite(self, *, sprite_name: str) -> dict[str, Any] | None:
        try:
            payload = await self._request("GET", f"/v1/sprites/{sprite_name}")
            if not isinstance(payload, dict):
                raise PublishedAppSandboxBackendError(f"Sprite returned invalid payload for {sprite_name}")
            return payload
        except PublishedAppSandboxBackendError as exc:
            if "(404)" in str(exc):
                return None
            raise

    async def _sprite_exists(self, *, sprite_name: str) -> bool:
        return await self._get_sprite(sprite_name=sprite_name) is not None

    async def _ensure_sprite(self, *, sprite_name: str) -> dict[str, Any]:
        existing = await self._get_sprite(sprite_name=sprite_name)
        if existing is not None:
            return existing
        created = await self._request(
            "POST",
            "/v1/sprites",
            json_payload={
                "name": sprite_name,
                "url_settings": {"auth": "sprite"},
            },
        )
        if not isinstance(created, dict):
            raise PublishedAppSandboxBackendError(f"Sprite create returned invalid payload for {sprite_name}")
        return created

    async def _put_service(self, *, sprite_name: str, service_name: str, payload: dict[str, Any]) -> None:
        await self._request(
            "PUT",
            f"/v1/sprites/{sprite_name}/services/{service_name}",
            json_payload=payload,
            expect_json=False,
        )

    async def _start_service(self, *, sprite_name: str, service_name: str) -> None:
        await self._request(
            "POST",
            f"/v1/sprites/{sprite_name}/services/{service_name}/start",
            expect_json=False,
        )

    async def _ensure_services(self, *, sprite_name: str) -> None:
        live_workspace_path = self._live_workspace_path()
        preview_script = (
            f"cd {shlex.quote(live_workspace_path)} && "
            f"npm run dev -- --host 0.0.0.0 --port {self._preview_port()}"
        )
        opencode_command = str(
            self.config.sprite_opencode_command
            or f"cd {shlex.quote(live_workspace_path)} && "
            f"(opencode serve --hostname 0.0.0.0 --port {self._opencode_port()} "
            f"|| npx -y opencode-ai serve --hostname 0.0.0.0 --port {self._opencode_port()})"
        ).strip()
        await self._put_service(
            sprite_name=sprite_name,
            service_name=self._preview_service_name(),
            payload={
                **self._service_command(preview_script),
                "http_port": self._preview_port(),
            },
        )
        await self._start_service(
            sprite_name=sprite_name,
            service_name=self._preview_service_name(),
        )
        await self._put_service(
            sprite_name=sprite_name,
            service_name=self._opencode_service_name(),
            payload=self._service_command(opencode_command),
        )
        await self._start_service(
            sprite_name=sprite_name,
            service_name=self._opencode_service_name(),
        )

    async def _wait_for_preview_ready(self, *, sprite_name: str) -> None:
        script = f"""
import sys
import time
import re
import urllib.error
import urllib.request

deadline = time.time() + 45
last_error = "preview service did not become ready"

def fetch(path: str):
    url = f"http://127.0.0.1:{self._preview_port()}{{path}}"
    with urllib.request.urlopen(url, timeout=4.0) as response:
        return response.status, response.read().decode("utf-8", errors="ignore")

while time.time() < deadline:
    try:
        client_status, client_body = fetch("/@vite/client")
        if client_status != 200 or "HMRContext" not in client_body:
            last_error = f"vite client not ready: status={{client_status}}"
            time.sleep(0.75)
            continue
        main_status, main_body = fetch("/src/main.tsx")
        if main_status != 200 or not main_body:
            last_error = f"main entry not ready: status={{main_status}}"
            time.sleep(0.75)
            continue
        style_status, style_body = fetch("/src/styles.css")
        if style_status != 200 or "Internal Server Error" in style_body:
            last_error = f"styles not ready: status={{style_status}}"
            time.sleep(0.75)
            continue
        dep_paths = []
        for match in re.finditer(r'\"(/node_modules/\\.vite/deps/[^\"?]+\\.js\\?v=[^\\\"]+)\"', main_body):
            dep_paths.append(match.group(1))
        dep_paths = dep_paths[:3]
        dep_error = None
        for dep_path in dep_paths:
            dep_status, _ = fetch(dep_path)
            if dep_status != 200:
                dep_error = f"optimized dep not ready: {{dep_path}} status={{dep_status}}"
                break
        if dep_error:
            last_error = dep_error
            time.sleep(0.75)
            continue
        print("ready")
        sys.exit(0)
    except Exception as exc:
        last_error = str(exc)
    time.sleep(0.75)
print(last_error)
sys.exit(1)
""".strip()
        await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=60,
            max_output_bytes=4000,
        )

    async def _mirror_workspace(self, *, sprite_name: str, source_workspace_path: str, target_workspace_path: str) -> None:
        script = f"""
import json
import pathlib
import shutil

source = pathlib.Path({json.dumps(source_workspace_path)})
target = pathlib.Path({json.dumps(target_workspace_path)})
source.mkdir(parents=True, exist_ok=True)
target.mkdir(parents=True, exist_ok=True)

managed = set()
for source_path in sorted(source.rglob("*")):
    rel = source_path.relative_to(source).as_posix()
    if not rel:
        continue
    managed.add(rel)
    target_path = target / rel
    if source_path.is_dir():
        target_path.mkdir(parents=True, exist_ok=True)
        continue
    target_path.parent.mkdir(parents=True, exist_ok=True)
    copy_required = True
    if target_path.exists() and target_path.is_file():
        source_stat = source_path.stat()
        target_stat = target_path.stat()
        copy_required = (
            source_stat.st_size != target_stat.st_size
            or source_stat.st_mtime_ns != target_stat.st_mtime_ns
        )
    if copy_required:
        shutil.copy2(source_path, target_path)

for existing in sorted(target.rglob("*"), reverse=True):
    rel = existing.relative_to(target).as_posix()
    if rel in managed:
        continue
    if existing.is_file() or existing.is_symlink():
        existing.unlink(missing_ok=True)
    elif existing.is_dir():
        try:
            existing.rmdir()
        except OSError:
            pass

print(json.dumps({{"status": "ok"}}, sort_keys=True))
""".strip()
        await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=max(180, self.config.sprite_command_timeout_seconds),
            max_output_bytes=12_000,
        )

    async def _exec(
        self,
        *,
        sprite_name: str,
        command: list[str],
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        cwd: str | None = None,
        allow_nonzero: bool = False,
    ) -> tuple[str, int]:
        shell_command = " ".join(shlex.quote(part) for part in command)
        script = (
            "set +e\n"
            f"{shell_command} 2>&1\n"
            "status=$?\n"
            f"printf '\\n{_EXIT_MARKER}%s\\n' \"$status\"\n"
            "exit 0\n"
        )
        raw = await self._request(
            "POST",
            f"/v1/sprites/{sprite_name}/exec",
            params=(
                [("cmd", "bash"), ("cmd", "-s"), ("stdin", "true")]
                + ([("dir", cwd)] if cwd else [])
            ),
            content=script.encode("utf-8"),
            expect_json=False,
            timeout_seconds=max(30.0, float(timeout_seconds)),
        )
        if not isinstance(raw, str):
            raise PublishedAppSandboxBackendError("Sprite exec returned invalid output.")
        marker_index = raw.rfind(_EXIT_MARKER)
        if marker_index >= 0:
            body = raw[:marker_index].rstrip("\n")
            exit_code_raw = raw[marker_index + len(_EXIT_MARKER) :].strip().splitlines()[0]
            try:
                exit_code = int(exit_code_raw)
            except Exception:
                exit_code = 0
        else:
            body = raw
            exit_code = 0
        body = self._sanitize_exec_output(body)
        if len(body.encode("utf-8")) > max_output_bytes:
            body = body.encode("utf-8")[:max_output_bytes].decode("utf-8", errors="ignore")
        if exit_code != 0 and not allow_nonzero:
            raise PublishedAppSandboxBackendError(body or f"Sprite command failed with exit code {exit_code}.")
        return body, exit_code

    async def _exec_json(
        self,
        *,
        sprite_name: str,
        script: str,
        cwd: str | None = None,
        timeout_seconds: int = 180,
    ) -> dict[str, Any]:
        output, _ = await self._exec(
            sprite_name=sprite_name,
            command=["python3", "-c", script],
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            max_output_bytes=2_000_000,
        )
        try:
            payload = json.loads(output or "{}")
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Sprite command returned invalid JSON: {output[:280]}") from exc
        if not isinstance(payload, dict):
            raise PublishedAppSandboxBackendError("Sprite command returned non-dict JSON payload.")
        return payload

    async def _exec_with_stdin(
        self,
        *,
        sprite_name: str,
        command: list[str],
        stdin_text: str,
        cwd: str | None = None,
        timeout_seconds: int = 180,
        max_output_bytes: int = 12000,
        allow_nonzero: bool = False,
    ) -> tuple[str, int]:
        shell_command = " ".join(shlex.quote(part) for part in command)
        script = (
            "set +e\n"
            f"cat <<'__CODEX_STDIN__' | {shell_command} 2>&1\n"
            f"{stdin_text}\n"
            "__CODEX_STDIN__\n"
            "status=$?\n"
            f"printf '\\n{_EXIT_MARKER}%s\\n' \"$status\"\n"
            "exit 0\n"
        )
        raw = await self._request(
            "POST",
            f"/v1/sprites/{sprite_name}/exec",
            params=(
                [("cmd", "bash"), ("cmd", "-s"), ("stdin", "true")]
                + ([("dir", cwd)] if cwd else [])
            ),
            content=script.encode("utf-8"),
            expect_json=False,
            timeout_seconds=max(30.0, float(timeout_seconds)),
        )
        if not isinstance(raw, str):
            raise PublishedAppSandboxBackendError("Sprite exec returned invalid output.")
        marker_index = raw.rfind(_EXIT_MARKER)
        if marker_index >= 0:
            body = raw[:marker_index].rstrip("\n")
            exit_code_raw = raw[marker_index + len(_EXIT_MARKER) :].strip().splitlines()[0]
            try:
                exit_code = int(exit_code_raw)
            except Exception:
                exit_code = 0
        else:
            body = raw
            exit_code = 0
        body = self._sanitize_exec_output(body)
        if len(body.encode("utf-8")) > max_output_bytes:
            body = body.encode("utf-8")[:max_output_bytes].decode("utf-8", errors="ignore")
        if exit_code != 0 and not allow_nonzero:
            raise PublishedAppSandboxBackendError(body or f"Sprite command failed with exit code {exit_code}.")
        return body, exit_code

    async def _ensure_workspace_dirs(self, *, sprite_name: str) -> None:
        await self._exec(
            sprite_name=sprite_name,
            command=[
                "mkdir",
                "-p",
                self._live_workspace_path(),
                self._stage_workspace_path(),
                self._publish_workspace_path(),
                os.path.dirname(f"{self._live_workspace_path()}/{_REVISION_FILE}"),
            ],
            timeout_seconds=60,
            max_output_bytes=2000,
        )

    async def _sync_files_to_workspace(self, *, sprite_name: str, workspace_path: str, files: Dict[str, str]) -> str:
        encoded = base64.b64encode(json.dumps(files, ensure_ascii=True, sort_keys=True).encode("utf-8")).decode("ascii")
        script = f"""
import base64
import json
import os
import pathlib

workspace = pathlib.Path({json.dumps(workspace_path)})
workspace.mkdir(parents=True, exist_ok=True)
payload = json.loads(base64.b64decode({json.dumps(encoded)}).decode("utf-8"))
managed = set()
for rel_path, content in payload.items():
    rel = str(rel_path or "").replace("\\\\", "/").lstrip("/")
    if not rel:
        continue
    managed.add(rel)
    target = workspace / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")

ignore_prefixes = tuple(
    prefix for prefix in {json.dumps(":".join(_SYNC_IGNORE_PREFIXES))}.split(":") if prefix
)
for existing in sorted(workspace.rglob("*")):
    if not existing.is_file():
        continue
    rel = existing.relative_to(workspace).as_posix()
    if rel in managed:
        continue
    if any(rel.startswith(prefix) for prefix in ignore_prefixes):
        continue
    existing.unlink(missing_ok=True)
    parent = existing.parent
    while parent != workspace and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent

revision_token = base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")
revision_path = workspace / {json.dumps(_REVISION_FILE)}
revision_path.parent.mkdir(parents=True, exist_ok=True)
revision_path.write_text(revision_token, encoding="utf-8")
print(json.dumps({{"revision_token": revision_token}}, sort_keys=True))
""".strip()
        output, _ = await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=max(180, self.config.sprite_command_timeout_seconds),
            max_output_bytes=2_000_000,
        )
        try:
            normalized = json.loads(output or "{}")
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Sprite sync failed: {output[:280]}") from exc
        return str(normalized.get("revision_token") or "").strip()

    async def _read_revision_token(self, *, sprite_name: str, workspace_path: str) -> str | None:
        output, exit_code = await self._exec(
            sprite_name=sprite_name,
            command=["cat", f"{workspace_path}/{_REVISION_FILE}"],
            timeout_seconds=30,
            max_output_bytes=512,
            allow_nonzero=True,
        )
        if exit_code != 0:
            return None
        token = str(output or "").strip()
        return token or None

    async def _read_dependency_hash(self, *, sprite_name: str, workspace_path: str) -> str | None:
        output, exit_code = await self._exec(
            sprite_name=sprite_name,
            command=["cat", f"{workspace_path}/{_DEPENDENCY_HASH_FILE}"],
            timeout_seconds=30,
            max_output_bytes=512,
            allow_nonzero=True,
        )
        if exit_code != 0:
            return None
        value = str(output or "").strip()
        return value or None

    async def _write_dependency_hash(self, *, sprite_name: str, workspace_path: str, dependency_hash: str) -> None:
        await self._exec(
            sprite_name=sprite_name,
            command=[
                "bash",
                "-lc",
                f"mkdir -p {shlex.quote(os.path.dirname(f'{workspace_path}/{_DEPENDENCY_HASH_FILE}'))} "
                f"&& printf %s {shlex.quote(dependency_hash)} > {shlex.quote(f'{workspace_path}/{_DEPENDENCY_HASH_FILE}')}",
            ],
            timeout_seconds=30,
            max_output_bytes=1024,
        )

    async def _install_dependencies_if_needed(
        self,
        *,
        sprite_name: str,
        workspace_path: str,
        dependency_hash: str,
        force_install: bool,
    ) -> None:
        current_hash = await self._read_dependency_hash(sprite_name=sprite_name, workspace_path=workspace_path)
        if not force_install and current_hash == dependency_hash:
            return
        command = ["bash", "-lc", "if [ -f package-lock.json ]; then npm ci; elif [ -f package.json ]; then npm install --no-audit --no-fund; fi"]
        await self._exec(
            sprite_name=sprite_name,
            command=command,
            cwd=workspace_path,
            timeout_seconds=max(300, self.config.sprite_command_timeout_seconds),
            max_output_bytes=80_000,
        )
        await self._exec(
            sprite_name=sprite_name,
            command=["rm", "-rf", f"{workspace_path}/node_modules/.vite"],
            timeout_seconds=30,
            max_output_bytes=4000,
            allow_nonzero=True,
        )
        await self._write_dependency_hash(
            sprite_name=sprite_name,
            workspace_path=workspace_path,
            dependency_hash=dependency_hash,
        )

    async def _ensure_preview_ready_with_repair(
        self,
        *,
        sprite_name: str,
        workspace_path: str,
        dependency_hash: str,
    ) -> None:
        try:
            await self._wait_for_preview_ready(sprite_name=sprite_name)
            return
        except Exception:
            await self._install_dependencies_if_needed(
                sprite_name=sprite_name,
                workspace_path=workspace_path,
                dependency_hash=dependency_hash,
                force_install=True,
            )
            await self._ensure_services(sprite_name=sprite_name)
            await self._wait_for_preview_ready(sprite_name=sprite_name)

    def _backend_metadata(
        self,
        *,
        sprite_name: str,
        sprite_url: str,
        preview_base_path: str,
        revision_token: str | None,
    ) -> dict[str, Any]:
        return {
            "provider": "sprite",
            "preview": {
                "upstream_base_url": str(sprite_url).rstrip("/"),
                "base_path": preview_base_path,
                "upstream_path": "/",
                "auth_kind": "bearer_env",
                "auth_header_name": "Authorization",
                "auth_token_env": "APPS_SPRITE_API_TOKEN",
                "auth_token_prefix": "Bearer ",
            },
            "workspace": {
                "sprite_name": sprite_name,
                "live_workspace_path": self._live_workspace_path(),
                "stage_workspace_path": self._stage_workspace_path(),
                "publish_workspace_path": self._publish_workspace_path(),
                "revision_token": revision_token,
            },
            "services": {
                "preview_service_name": self._preview_service_name(),
                "preview_port": self._preview_port(),
                "opencode_service_name": self._opencode_service_name(),
                "opencode_port": self._opencode_port(),
                "opencode_base_url": f"{str(sprite_url).rstrip('/')}:{self._opencode_port()}",
            },
        }

    async def _snapshot_workspace_files(self, *, sprite_name: str, workspace_path: str) -> dict[str, Any]:
        script = f"""
import hashlib
import json
import pathlib

root = pathlib.Path({json.dumps(workspace_path)})
files = {{}}
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(root).as_posix()
    files[rel] = path.read_text(encoding="utf-8", errors="replace")
revision_token_path = root / {json.dumps(_REVISION_FILE)}
revision_token = revision_token_path.read_text(encoding="utf-8", errors="replace").strip() if revision_token_path.exists() else ""
print(json.dumps({{
    "files": files,
    "file_count": len(files),
    "revision_token": revision_token or None,
}}, sort_keys=True))
""".strip()
        output, _ = await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=max(180, self.config.sprite_command_timeout_seconds),
            max_output_bytes=8_000_000,
        )
        try:
            payload = json.loads(output or "{}")
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Sprite snapshot failed: {output[:280]}") from exc
        if not isinstance(payload, dict):
            raise PublishedAppSandboxBackendError("Sprite snapshot returned invalid payload.")
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
        _ = tenant_id, user_id, revision_id, entry_file, idle_timeout_seconds, draft_dev_token
        sprite_name = self._sprite_name(prefix=self.config.sprite_name_prefix, app_id=app_id)
        sprite = await self._ensure_sprite(sprite_name=sprite_name)
        sprite_url = str(sprite.get("url") or "").strip() or f"https://{sprite_name}.sprites.app"
        await self._ensure_workspace_dirs(sprite_name=sprite_name)
        revision_token = await self._sync_files_to_workspace(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            files=files,
        )
        await self._install_dependencies_if_needed(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
            force_install=False,
        )
        await self._ensure_services(sprite_name=sprite_name)
        await self._ensure_preview_ready_with_repair(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
        )
        return {
            "sandbox_id": sprite_name,
            "status": "serving",
            "runtime_backend": self.backend_name,
            "runtime_generation": int(runtime_generation or 0),
            "workspace_path": self._live_workspace_path(),
            "live_workspace_path": self._live_workspace_path(),
            "stage_workspace_path": self._stage_workspace_path(),
            "publish_workspace_path": self._publish_workspace_path(),
            "preview_service_name": self._preview_service_name(),
            "opencode_service_name": self._opencode_service_name(),
            "preview_url": preview_base_path,
            "backend_metadata": self._backend_metadata(
                sprite_name=sprite_name,
                sprite_url=sprite_url,
                preview_base_path=preview_base_path,
                revision_token=revision_token,
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
        _ = entry_file, idle_timeout_seconds
        sprite_name = str(sandbox_id or "").strip()
        sprite = await self._ensure_sprite(sprite_name=sprite_name)
        sprite_url = str(sprite.get("url") or "").strip() or f"https://{sprite_name}.sprites.app"
        await self._ensure_workspace_dirs(sprite_name=sprite_name)
        revision_token = await self._sync_files_to_workspace(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            files=files,
        )
        await self._install_dependencies_if_needed(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
            force_install=bool(install_dependencies),
        )
        await self._ensure_services(sprite_name=sprite_name)
        await self._ensure_preview_ready_with_repair(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
        )
        metadata = self._backend_metadata(
            sprite_name=sprite_name,
            sprite_url=sprite_url,
            preview_base_path=preview_base_path or "/",
            revision_token=revision_token,
        )
        return {
            "sandbox_id": sprite_name,
            "status": "serving",
            "runtime_backend": self.backend_name,
            "backend_metadata": metadata,
        }

    async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int) -> Dict[str, Any]:
        _ = idle_timeout_seconds
        sprite_name = str(sandbox_id or "").strip()
        if not await self._sprite_exists(sprite_name=sprite_name):
            raise PublishedAppSandboxBackendError(f"Sprite request failed (404) for /v1/sprites/{sprite_name}: not found")
        await self._wait_for_preview_ready(sprite_name=sprite_name)
        return {
            "sandbox_id": sprite_name,
            "status": "serving",
            "runtime_backend": self.backend_name,
        }

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        sprite_name = str(sandbox_id or "").strip()
        await self._request("DELETE", f"/v1/sprites/{sprite_name}", json_payload={}, expect_json=False)
        return {
            "sandbox_id": sprite_name,
            "status": "stopped",
            "runtime_backend": self.backend_name,
        }

    async def list_files(self, *, sandbox_id: str, limit: int = 500) -> Dict[str, Any]:
        output, _ = await self._exec(
            sprite_name=sandbox_id,
            command=[
                "bash",
                "-lc",
                f"cd {shlex.quote(self._live_workspace_path())} && find . -type f | sed 's#^./##' | sort | head -n {max(1, int(limit))}",
            ],
            timeout_seconds=60,
            max_output_bytes=80_000,
        )
        paths = [line.strip() for line in output.splitlines() if line.strip()]
        return {"sandbox_id": sandbox_id, "paths": paths, "count": len(paths)}

    async def read_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        normalized = str(path or "").strip().lstrip("/")
        output, _ = await self._exec(
            sprite_name=sandbox_id,
            command=["cat", f"{self._live_workspace_path()}/{normalized}"],
            timeout_seconds=30,
            max_output_bytes=2_000_000,
        )
        return {
            "sandbox_id": sandbox_id,
            "path": normalized,
            "content": output,
            "size_bytes": len(output.encode("utf-8")),
            "sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "revision_token": await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path()),
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
        normalized = str(path or "").strip().lstrip("/")
        script = (
            "import hashlib, json, pathlib\n"
            f"path = pathlib.Path({json.dumps(self._live_workspace_path())}) / {json.dumps(normalized)}\n"
            "source = path.read_text(encoding='utf-8', errors='replace')\n"
            "lines = source.splitlines()\n"
            f"start_line = {int(start_line or 1)}\n"
            f"end_line = {int(end_line or (start_line or 1))}\n"
            f"context_before = {max(0, int(context_before or 0))}\n"
            f"context_after = {max(0, int(context_after or 0))}\n"
            f"with_numbers = {json.dumps(bool(with_line_numbers))}\n"
            "if not lines:\n"
            "    payload = {'start_line': 1, 'end_line': 1, 'content': '', 'line_count': 0, 'truncated': False}\n"
            "else:\n"
            "    start = max(1, start_line - context_before)\n"
            "    end = min(len(lines), max(start_line, end_line) + context_after)\n"
            "    selected = lines[start - 1:end]\n"
            "    if with_numbers:\n"
            "        rendered = [f'{start + idx}: {line}' for idx, line in enumerate(selected)]\n"
            "    else:\n"
            "        rendered = selected\n"
            "    content = '\\n'.join(rendered)\n"
            f"    encoded = content.encode('utf-8')[:{max(256, int(max_bytes or 12000))}]\n"
            "    payload = {\n"
            "        'start_line': start,\n"
            "        'end_line': end,\n"
            "        'content': encoded.decode('utf-8', errors='ignore'),\n"
            "        'line_count': len(selected),\n"
            "        'truncated': len(content.encode('utf-8')) > len(encoded),\n"
            "    }\n"
            "payload['size_bytes'] = len(payload['content'].encode('utf-8'))\n"
            "payload['sha256'] = hashlib.sha256(source.encode('utf-8')).hexdigest()\n"
            "print(json.dumps(payload, sort_keys=True))\n"
        )
        output, _ = await self._exec_with_stdin(
            sprite_name=sandbox_id,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=30,
            max_output_bytes=max(20_000, int(max_bytes or 12000) * 2),
        )
        payload = json.loads(output or "{}")
        payload["sandbox_id"] = sandbox_id
        payload["path"] = normalized
        payload["revision_token"] = await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path())
        return payload

    async def search_code(self, *, sandbox_id: str, query: str, max_results: int = 30) -> Dict[str, Any]:
        output, _ = await self._exec(
            sprite_name=sandbox_id,
            command=[
                "bash",
                "-lc",
                f"cd {shlex.quote(self._live_workspace_path())} && "
                f"rg -n --no-heading --color never -S {shlex.quote(str(query or ''))} . | head -n {max(1, int(max_results))}",
            ],
            timeout_seconds=60,
            max_output_bytes=80_000,
            allow_nonzero=True,
        )
        matches: list[dict[str, Any]] = []
        for line in output.splitlines():
            raw = line.strip()
            if not raw or raw.startswith("rg:"):
                continue
            match = re.match(r"^\./?(.*?):(\d+):(.*)$", raw)
            if not match:
                continue
            matches.append(
                {
                    "path": match.group(1),
                    "line": int(match.group(2)),
                    "preview": match.group(3)[:220],
                }
            )
        return {
            "sandbox_id": sandbox_id,
            "query": query,
            "matches": matches,
            "revision_token": await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path()),
        }

    async def workspace_index(
        self,
        *,
        sandbox_id: str,
        limit: int = 500,
        query: str | None = None,
        max_symbols_per_file: int = 16,
    ) -> Dict[str, Any]:
        _ = max_symbols_per_file
        snapshot = await self._snapshot_workspace_files(sprite_name=sandbox_id, workspace_path=self._live_workspace_path())
        query_text = str(query or "").strip().lower()
        files_payload = snapshot.get("files") if isinstance(snapshot.get("files"), dict) else {}
        rows: list[dict[str, Any]] = []
        total_size = 0
        for rel_path, source in files_payload.items():
            content = str(source if isinstance(source, str) else "")
            size_bytes = len(content.encode("utf-8"))
            total_size += size_bytes
            score = 0
            if query_text:
                if query_text in rel_path.lower():
                    score += 4
                if query_text in content.lower():
                    score += 2
                if score <= 0:
                    continue
            rows.append(
                {
                    "path": rel_path,
                    "size_bytes": size_bytes,
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "language": os.path.splitext(rel_path)[1].lstrip(".") or "text",
                    "symbol_outline": [],
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
            "revision_token": snapshot.get("revision_token"),
        }

    async def apply_patch(
        self,
        *,
        sandbox_id: str,
        patch: str,
        options: dict[str, Any] | None = None,
        preconditions: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        _ = options, preconditions
        patch_b64 = base64.b64encode(str(patch or "").encode("utf-8")).decode("ascii")
        command = [
            "bash",
            "-lc",
            f"cd {shlex.quote(self._live_workspace_path())} && "
            "tmp_patch=$(mktemp) && "
            f"python3 - <<'PY' > \"$tmp_patch\"\nimport base64; print(base64.b64decode({json.dumps(patch_b64)}).decode('utf-8'), end='')\nPY\n"
            "patch -p0 --forward --reject-file=- < \"$tmp_patch\" >/tmp/sprite-patch.log 2>&1; "
            "status=$?; "
            "cat /tmp/sprite-patch.log; "
            "rm -f \"$tmp_patch\"; "
            "exit $status",
        ]
        output, exit_code = await self._exec(
            sprite_name=sandbox_id,
            command=command,
            timeout_seconds=120,
            max_output_bytes=80_000,
            allow_nonzero=True,
        )
        revision_token = await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path())
        if exit_code != 0:
            return {
                "ok": False,
                "code": "PATCH_APPLY_FAILED",
                "summary": output or "Patch apply failed.",
                "failures": [{"message": output or "Patch apply failed."}],
                "applied_files": [],
                "revision_token": revision_token,
            }
        return {
            "ok": True,
            "summary": "Patch applied.",
            "failures": [],
            "applied_files": [],
            "revision_token": revision_token,
            "metrics": {"patch_bytes": len(str(patch or "").encode("utf-8")), "applied_file_count": 0, "failure_count": 0, "edit_latency_ms": 0},
        }

    async def write_file(self, *, sandbox_id: str, path: str, content: str) -> Dict[str, Any]:
        normalized = str(path or "").strip().lstrip("/")
        encoded = base64.b64encode(str(content if isinstance(content, str) else str(content)).encode("utf-8")).decode("ascii")
        await self._exec(
            sprite_name=sandbox_id,
            command=[
                "bash",
                "-lc",
                f"mkdir -p {shlex.quote(os.path.dirname(f'{self._live_workspace_path()}/{normalized}') or self._live_workspace_path())} && "
                f"python3 - <<'PY' > {shlex.quote(f'{self._live_workspace_path()}/{normalized}')}\n"
                f"import base64; print(base64.b64decode({json.dumps(encoded)}).decode('utf-8'), end='')\nPY",
            ],
            timeout_seconds=30,
            max_output_bytes=4000,
        )
        return {
            "sandbox_id": sandbox_id,
            "path": normalized,
            "status": "written",
            "revision_token": await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path()),
        }

    async def delete_file(self, *, sandbox_id: str, path: str) -> Dict[str, Any]:
        normalized = str(path or "").strip().lstrip("/")
        await self._exec(
            sprite_name=sandbox_id,
            command=["rm", "-f", f"{self._live_workspace_path()}/{normalized}"],
            timeout_seconds=30,
            max_output_bytes=2000,
            allow_nonzero=True,
        )
        return {
            "sandbox_id": sandbox_id,
            "path": normalized,
            "status": "deleted",
            "revision_token": await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path()),
        }

    async def rename_file(self, *, sandbox_id: str, from_path: str, to_path: str) -> Dict[str, Any]:
        src = str(from_path or "").strip().lstrip("/")
        dst = str(to_path or "").strip().lstrip("/")
        await self._exec(
            sprite_name=sandbox_id,
            command=[
                "bash",
                "-lc",
                f"mkdir -p {shlex.quote(os.path.dirname(f'{self._live_workspace_path()}/{dst}') or self._live_workspace_path())} && "
                f"mv {shlex.quote(f'{self._live_workspace_path()}/{src}')} {shlex.quote(f'{self._live_workspace_path()}/{dst}')}",
            ],
            timeout_seconds=30,
            max_output_bytes=4000,
        )
        return {
            "sandbox_id": sandbox_id,
            "from_path": src,
            "to_path": dst,
            "status": "renamed",
            "revision_token": await self._read_revision_token(sprite_name=sandbox_id, workspace_path=self._live_workspace_path()),
        }

    async def snapshot_files(self, *, sandbox_id: str) -> Dict[str, Any]:
        payload = await self._snapshot_workspace_files(sprite_name=sandbox_id, workspace_path=self._live_workspace_path())
        payload["sandbox_id"] = sandbox_id
        return payload

    async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool) -> Dict[str, Any]:
        if reset:
            await self._exec(
                sprite_name=sandbox_id,
                command=[
                    "bash",
                    "-lc",
                    f"rm -rf {shlex.quote(self._stage_workspace_path())} && "
                    f"mkdir -p {shlex.quote(self._stage_workspace_path())} && "
                    f"cp -a {shlex.quote(self._live_workspace_path())}/. {shlex.quote(self._stage_workspace_path())}/",
                ],
                timeout_seconds=120,
                max_output_bytes=12_000,
            )
        else:
            _, exit_code = await self._exec(
                sprite_name=sandbox_id,
                command=["test", "-d", self._stage_workspace_path()],
                timeout_seconds=10,
                max_output_bytes=512,
                allow_nonzero=True,
            )
            if exit_code != 0:
                await self.prepare_stage_workspace(sandbox_id=sandbox_id, reset=True)
        return {
            "sandbox_id": sandbox_id,
            "live_workspace_path": self._live_workspace_path(),
            "stage_workspace_path": self._stage_workspace_path(),
            "workspace_path": self._stage_workspace_path(),
        }

    async def snapshot_workspace(self, *, sandbox_id: str, workspace: str = "live") -> Dict[str, Any]:
        workspace_name = str(workspace or "live").strip().lower()
        workspace_path = self._live_workspace_path() if workspace_name == "live" else self._stage_workspace_path()
        payload = await self._snapshot_workspace_files(sprite_name=sandbox_id, workspace_path=workspace_path)
        payload["sandbox_id"] = sandbox_id
        payload["workspace"] = workspace_name
        payload["workspace_path"] = workspace_path
        return payload

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        await self._mirror_workspace(
            sprite_name=sandbox_id,
            source_workspace_path=self._stage_workspace_path(),
            target_workspace_path=self._live_workspace_path(),
        )
        return {
            "sandbox_id": sandbox_id,
            "status": "promoted",
            "live_workspace_path": self._live_workspace_path(),
            "stage_workspace_path": self._stage_workspace_path(),
        }

    async def prepare_publish_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        await self._exec(
            sprite_name=sandbox_id,
            command=[
                "bash",
                "-lc",
                f"rm -rf {shlex.quote(self._publish_workspace_path())} && "
                f"mkdir -p {shlex.quote(self._publish_workspace_path())} && "
                f"cp -a {shlex.quote(self._live_workspace_path())}/. {shlex.quote(self._publish_workspace_path())}/",
            ],
            timeout_seconds=120,
            max_output_bytes=12_000,
        )
        payload = await self._snapshot_workspace_files(sprite_name=sandbox_id, workspace_path=self._publish_workspace_path())
        payload["sandbox_id"] = sandbox_id
        payload["workspace_path"] = self._publish_workspace_path()
        payload["publish_workspace_path"] = self._publish_workspace_path()
        payload["live_workspace_path"] = self._live_workspace_path()
        return payload

    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        await self._exec(
            sprite_name=sandbox_id,
            command=["bash", "-lc", "if [ -f package-lock.json ]; then npm ci; elif [ -f package.json ]; then npm install --no-audit --no-fund; fi"],
            cwd=workspace_path,
            timeout_seconds=max(300, self.config.sprite_command_timeout_seconds),
            max_output_bytes=120_000,
        )
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "status": "prepared",
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
        output, exit_code = await self._exec(
            sprite_name=sandbox_id,
            command=command,
            cwd=workspace_path,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            allow_nonzero=True,
        )
        return {
            "sandbox_id": sandbox_id,
            "command": command,
            "workspace_path": workspace_path,
            "stdout": output,
            "stderr": "",
            "output": output,
            "exit_code": exit_code,
            "ok": exit_code == 0,
        }

    async def export_workspace_archive(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        format: str = "tar.gz",
    ) -> Dict[str, Any]:
        if format != "tar.gz":
            raise PublishedAppSandboxBackendError("Only tar.gz workspace export is supported.")
        output, _ = await self._exec(
            sprite_name=sandbox_id,
            command=[
                "bash",
                "-lc",
                f"cd {shlex.quote(workspace_path)} && tar -czf - . | base64 | tr -d '\\n'",
            ],
            timeout_seconds=max(300, self.config.sprite_command_timeout_seconds),
            max_output_bytes=40_000_000,
        )
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "format": format,
            "archive_base64": output.strip(),
        }

    async def sync_workspace_files(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
        files: Dict[str, str],
    ) -> Dict[str, Any]:
        revision_token = await self._sync_files_to_workspace(
            sprite_name=sandbox_id,
            workspace_path=workspace_path,
            files=files,
        )
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "file_count": len(files or {}),
            "revision_token": revision_token,
        }

    async def resolve_workspace_path(self, *, sandbox_id: str) -> str | None:
        _ = sandbox_id
        return self._live_workspace_path()

    async def _build_opencode_client(self, *, sandbox_id: str):
        from app.services.opencode_server_client import OpenCodeServerClient, OpenCodeServerClientConfig

        tunnel_base_url = await get_sprite_proxy_tunnel_manager().ensure_tunnel(
            api_base_url=self._api_base(),
            api_token=self._api_token(),
            sprite_name=sandbox_id,
            remote_host="127.0.0.1",
            remote_port=self._opencode_port(),
        )
        client = OpenCodeServerClient(
            OpenCodeServerClientConfig(
                enabled=True,
                base_url=tunnel_base_url,
                api_key=None,
                request_timeout_seconds=float(max(20, self.config.request_timeout_seconds)),
                connect_timeout_seconds=5.0,
                health_cache_seconds=3,
                sandbox_controller_mode_override=False,
                skip_workspace_bootstrap=True,
            )
        )
        client._api_mode = None
        return client

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
        client = await self._build_opencode_client(sandbox_id=sandbox_id)
        run_ref = await client.start_run(
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            model_id=model_id,
            prompt=prompt,
            messages=messages,
        )
        return {"run_ref": run_ref, "sandbox_id": sandbox_id, "status": "started"}

    async def stream_opencode_events(self, *, sandbox_id: str, run_ref: str) -> AsyncGenerator[dict[str, Any], None]:
        client = await self._build_opencode_client(sandbox_id=sandbox_id)
        async for item in client.stream_run_events(run_ref=run_ref):
            if isinstance(item, dict):
                yield item

    async def cancel_opencode_run(self, *, sandbox_id: str, run_ref: str) -> Dict[str, Any]:
        client = await self._build_opencode_client(sandbox_id=sandbox_id)
        cancelled = await client.cancel_run(run_ref=run_ref, sandbox_id=sandbox_id)
        return {"ok": bool(cancelled), "cancelled": bool(cancelled), "sandbox_id": sandbox_id, "run_ref": run_ref}

    async def answer_opencode_question(
        self,
        *,
        sandbox_id: str,
        run_ref: str,
        question_id: str,
        answers: list[list[str]],
    ) -> Dict[str, Any]:
        client = await self._build_opencode_client(sandbox_id=sandbox_id)
        ok = await client.answer_question(
            run_ref=run_ref,
            question_id=question_id,
            answers=answers,
            sandbox_id=sandbox_id,
        )
        return {"ok": bool(ok), "sandbox_id": sandbox_id, "run_ref": run_ref, "question_id": question_id}
