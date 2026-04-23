from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shlex
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict
from urllib.parse import urlencode

import httpx

from app.services.apps_builder_trace import apps_builder_trace
from app.services.opencode_server_launch import build_official_opencode_bootstrap_command
from app.services.published_app_live_preview import (
    LIVE_PREVIEW_MODE,
    LIVE_PREVIEW_STATUS_BUILDING,
    LIVE_PREVIEW_STATUS_BOOTING,
    LIVE_PREVIEW_STATUS_FAILED_KEEP_LAST_GOOD,
    LIVE_PREVIEW_STATUS_FAILED_NO_BUILD,
    LIVE_PREVIEW_STATUS_READY,
    build_live_preview_context_payload,
    build_live_preview_overlay_workspace_fingerprint,
    build_live_preview_static_server_script,
    build_live_preview_watch_script,
    normalize_live_preview_payload,
)
from app.services.published_app_builder_snapshot_filter import (
    BUILDER_SNAPSHOT_IGNORED_FILE_NAMES,
    BUILDER_SNAPSHOT_IGNORED_SUFFIXES,
)
from app.services.published_app_sandbox_backend import (
    PublishedAppOpenCodeEndpoint,
    PublishedAppSandboxBackend,
    PublishedAppSandboxBackendError,
)
from app.services.published_app_sprite_proxy_tunnel import get_sprite_proxy_tunnel_manager
from app.services.published_app_templates import TemplateRuntimeContext


logger = logging.getLogger(__name__)
_EXIT_MARKER = "__CODEX_EXIT_CODE__="
_REVISION_FILE = ".talmudpedia/runtime-revision-token"
_DEPENDENCY_HASH_FILE = ".talmudpedia/dependency-hash"
_LIVE_PREVIEW_ROOT = ".talmudpedia/live-preview"
_SYNC_IGNORE_PREFIXES = (".talmudpedia/", ".opencode/", "node_modules/")
_EXEC_CONTROL_TRANSLATION = {
    codepoint: None
    for codepoint in range(32)
    if chr(codepoint) not in {"\n", "\r", "\t"}
}
_SNAPSHOT_IGNORE_PREFIXES = (
    ".talmudpedia/",
    ".cache/",
    ".git/",
    ".next/",
    ".npm/",
    ".opencode/.bun/",
    ".parcel-cache/",
    ".pnpm-store/",
    ".turbo/",
    ".vite/",
    ".yarn/",
    "__pycache__/",
    "build/",
    "coverage/",
    "dist/",
)
_SPRITE_REQUEST_MAX_ATTEMPTS = max(1, int(os.getenv("APPS_SPRITE_REQUEST_MAX_ATTEMPTS", "6")))
_SPRITE_REQUEST_RETRY_DELAY_SECONDS = max(
    0.05,
    float(os.getenv("APPS_SPRITE_REQUEST_RETRY_DELAY_SECONDS", "0.2")),
)


class SpriteSandboxBackend(PublishedAppSandboxBackend):
    backend_name = "sprite"
    is_remote = True

    def __init__(self, config):
        super().__init__(config)
        self._opencode_clients_by_sandbox: dict[str, Any] = {}

    @staticmethod
    def _trace(event: str, **fields: Any) -> None:
        apps_builder_trace(
            event,
            domain="sprite.preview_service",
            **fields,
        )

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
    def _is_retryable_request_error(exc: Exception) -> bool:
        return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError))

    @staticmethod
    def _request_error_detail(exc: Exception) -> str:
        raw = str(exc).strip()
        if raw:
            return f"{exc.__class__.__name__}({raw})"
        return repr(exc) or exc.__class__.__name__

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

    def _preview_service_name(self) -> str:
        return str(self.config.sprite_preview_service_name or "builder-preview").strip() or "builder-preview"

    def _build_watch_service_name(self) -> str:
        return "builder-build-watch"

    def _opencode_service_name(self) -> str:
        return str(self.config.sprite_opencode_service_name or "opencode").strip() or "opencode"

    def _preview_port(self) -> int:
        return max(1024, int(self.config.sprite_preview_port or 8080))

    def _opencode_port(self) -> int:
        return max(1024, int(self.config.sprite_opencode_port or 4141))

    def _preview_poll_interval_ms(self) -> int:
        return max(100, int(os.getenv("APPS_SPRITE_VITE_POLL_INTERVAL_MS", "250")))

    def _live_preview_root_path(self) -> str:
        return f"{self._live_workspace_path()}/{_LIVE_PREVIEW_ROOT}"

    def _live_preview_status_path(self) -> str:
        return f"{self._live_preview_root_path()}/status.json"

    def _live_preview_context_path(self) -> str:
        return f"{self._live_preview_root_path()}/context.json"

    def _live_preview_build_watch_script_path(self) -> str:
        return f"{self._live_preview_root_path()}/build-watch.mjs"

    def _live_preview_static_server_script_path(self) -> str:
        return f"{self._live_preview_root_path()}/static-preview-server.py"

    def _live_preview_scripts_version(self) -> str:
        payload = "\n---\n".join(
            [
                build_live_preview_watch_script(
                    live_workspace_path=self._live_workspace_path(),
                    live_preview_root_path=self._live_preview_root_path(),
                ),
                build_live_preview_static_server_script(
                    live_preview_root_path=self._live_preview_root_path(),
                    preview_port=self._preview_port(),
                ),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _live_preview_supervisor_summary(
        self,
        *,
        build_watch_service: dict[str, Any] | None,
        static_preview_service: dict[str, Any] | None,
        restart_reason: str | None = None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "build_watch_status": self._service_runtime_status(build_watch_service) or "unknown",
            "static_server_status": self._service_runtime_status(static_preview_service) or "unknown",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "restart_reason": str(restart_reason or "").strip() or None,
            "failure_reason": str(failure_reason or "").strip() or None,
        }

    @staticmethod
    def _service_runtime_status(service: dict[str, Any] | None) -> str:
        if not isinstance(service, dict):
            return ""
        state = service.get("state")
        if isinstance(state, dict):
            return str(state.get("status") or "").strip().lower()
        return str(state or "").strip().lower()

    @staticmethod
    def _service_runtime_pid(service: dict[str, Any] | None) -> int | None:
        if not isinstance(service, dict):
            return None
        state = service.get("state")
        if isinstance(state, dict):
            raw_pid = state.get("pid")
            try:
                pid = int(raw_pid)
            except Exception:
                return None
            return pid if pid > 0 else None
        return None

    def _with_live_preview_supervisor(
        self,
        *,
        live_preview: dict[str, Any] | None,
        supervisor: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(live_preview or {})
        merged["supervisor"] = dict(supervisor or {})
        return normalize_live_preview_payload(merged)

    def _live_preview_needs_service_refresh(self, *, live_preview: dict[str, Any] | None) -> bool:
        if not isinstance(live_preview, dict) or not live_preview:
            return True
        payload = normalize_live_preview_payload(live_preview)
        supervisor = dict(payload.get("supervisor") or {}) if isinstance(payload.get("supervisor"), dict) else {}
        build_watch_status = str(supervisor.get("build_watch_status") or "").strip().lower()
        static_server_status = str(supervisor.get("static_server_status") or "").strip().lower()
        if build_watch_status and build_watch_status != "running":
            return True
        if static_server_status and static_server_status != "running":
            return True
        return False

    def _live_preview_requires_rebuild(
        self,
        *,
        revision_token: str | None,
        live_preview: dict[str, Any] | None,
    ) -> bool:
        resolved_revision_token = str(revision_token or "").strip()
        if not resolved_revision_token or not isinstance(live_preview, dict) or not live_preview:
            return False
        payload = normalize_live_preview_payload(live_preview)
        status = str(payload.get("status") or "").strip().lower()
        if status in {LIVE_PREVIEW_STATUS_BOOTING, LIVE_PREVIEW_STATUS_BUILDING}:
            return False
        last_trigger_revision_token = str(payload.get("debug_last_trigger_revision_token") or "").strip()
        return bool(last_trigger_revision_token) and last_trigger_revision_token != resolved_revision_token

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
        response: httpx.Response | None = None
        last_exc: Exception | None = None
        for attempt in range(1, _SPRITE_REQUEST_MAX_ATTEMPTS + 1):
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
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= _SPRITE_REQUEST_MAX_ATTEMPTS or not self._is_retryable_request_error(exc):
                    detail = self._request_error_detail(exc)
                    raise PublishedAppSandboxBackendError(
                        f"Sprite request failed for {method.upper()} {path}: {detail}"
                    ) from exc
                self._trace(
                    "sprite.api.request.retry",
                    method=method.upper(),
                    path=path,
                    attempt=attempt,
                    max_attempts=_SPRITE_REQUEST_MAX_ATTEMPTS,
                    error_type=exc.__class__.__name__,
                )
                await asyncio.sleep(_SPRITE_REQUEST_RETRY_DELAY_SECONDS * attempt)
        if response is None:
            detail = self._request_error_detail(last_exc or RuntimeError("missing Sprite response"))
            raise PublishedAppSandboxBackendError(
                f"Sprite request failed for {method.upper()} {path}: {detail}"
            )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise PublishedAppSandboxBackendError(
                f"Sprite request failed ({response.status_code}) for {method.upper()} {path}: {detail}"
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
        try:
            created = await self._request(
                "POST",
                "/v1/sprites",
                json_payload={
                    "name": sprite_name,
                    "url_settings": {"auth": "sprite"},
                },
            )
        except PublishedAppSandboxBackendError as exc:
            if "(409)" not in str(exc):
                raise
            existing = await self._get_sprite(sprite_name=sprite_name)
            if existing is not None:
                return existing
            raise
        if not isinstance(created, dict):
            raise PublishedAppSandboxBackendError(f"Sprite create returned invalid payload for {sprite_name}")
        return created

    async def _put_service(self, *, sprite_name: str, service_name: str, payload: dict[str, Any]) -> None:
        self._trace(
            "sprite.service.put.begin",
            sprite_name=sprite_name,
            service_name=service_name,
            http_port=payload.get("http_port"),
            cmd=payload.get("cmd"),
            args=payload.get("args"),
        )
        await self._request(
            "PUT",
            f"/v1/sprites/{sprite_name}/services/{service_name}",
            json_payload=payload,
            expect_json=False,
        )
        self._trace(
            "sprite.service.put.done",
            sprite_name=sprite_name,
            service_name=service_name,
        )

    async def _start_service(self, *, sprite_name: str, service_name: str) -> None:
        self._trace(
            "sprite.service.start.begin",
            sprite_name=sprite_name,
            service_name=service_name,
        )
        await self._request(
            "POST",
            f"/v1/sprites/{sprite_name}/services/{service_name}/start",
            expect_json=False,
        )
        self._trace(
            "sprite.service.start.done",
            sprite_name=sprite_name,
            service_name=service_name,
        )

    async def _get_service(self, *, sprite_name: str, service_name: str) -> dict[str, Any] | None:
        try:
            payload = await self._request("GET", f"/v1/sprites/{sprite_name}/services/{service_name}")
        except PublishedAppSandboxBackendError as exc:
            if "(404)" in str(exc):
                return None
            raise
        return payload if isinstance(payload, dict) else None

    async def _install_live_preview_scripts(self, *, sprite_name: str) -> None:
        script = f"""
import json
import pathlib

root = pathlib.Path({json.dumps(self._live_preview_root_path())})
root.mkdir(parents=True, exist_ok=True)
(root / "build-watch.mjs").write_text({json.dumps(build_live_preview_watch_script(
    live_workspace_path=self._live_workspace_path(),
    live_preview_root_path=self._live_preview_root_path(),
))}, encoding="utf-8")
(root / "static-preview-server.py").write_text({json.dumps(build_live_preview_static_server_script(
    live_preview_root_path=self._live_preview_root_path(),
    preview_port=self._preview_port(),
))}, encoding="utf-8")
print(json.dumps({{"status": "ok"}}, sort_keys=True))
""".strip()
        await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=60,
            max_output_bytes=8_000,
        )

    async def _ensure_service_running(
        self,
        *,
        sprite_name: str,
        service_name: str,
        payload: dict[str, Any],
        force_restart: bool = False,
    ) -> None:
        service = await self._get_service(sprite_name=sprite_name, service_name=service_name)
        expected_http_port = payload.get("http_port")
        if service is None:
            await self._put_service(sprite_name=sprite_name, service_name=service_name, payload=payload)
            await self._start_service(sprite_name=sprite_name, service_name=service_name)
            return
        if force_restart:
            pid = self._service_runtime_pid(service)
            if pid is not None:
                await self._exec(
                    sprite_name=sprite_name,
                    command=["bash", "-lc", f"kill -TERM {pid} >/dev/null 2>&1 || true"],
                    timeout_seconds=10,
                    max_output_bytes=512,
                    allow_nonzero=True,
                )
            await self._put_service(sprite_name=sprite_name, service_name=service_name, payload=payload)
            await self._start_service(sprite_name=sprite_name, service_name=service_name)
            return
        current_cmd = service.get("cmd") if isinstance(service, dict) else None
        current_args = service.get("args") if isinstance(service, dict) else None
        current_http_port = service.get("http_port") if isinstance(service, dict) else None
        needs_reconfigure = (
            current_cmd != payload.get("cmd")
            or current_args != payload.get("args")
            or current_http_port != expected_http_port
        )
        if needs_reconfigure:
            await self._put_service(sprite_name=sprite_name, service_name=service_name, payload=payload)
            await self._start_service(sprite_name=sprite_name, service_name=service_name)
            return
        if self._service_runtime_status(service) != "running":
            await self._start_service(sprite_name=sprite_name, service_name=service_name)

    async def _ensure_preview_service(self, *, sprite_name: str, force_restart: bool = False) -> None:
        await self._install_live_preview_scripts(sprite_name=sprite_name)
        scripts_version = self._live_preview_scripts_version()
        restart_nonce_prefix = ""
        if force_restart:
            restart_nonce = datetime.now(timezone.utc).isoformat()
            restart_nonce_prefix = (
                f"export TALMUDPEDIA_LIVE_PREVIEW_RESTART_NONCE={shlex.quote(restart_nonce)} && "
            )
        build_watch_command = (
            f"export TALMUDPEDIA_LIVE_PREVIEW_SCRIPTS_VERSION={shlex.quote(scripts_version)} && "
            f"{restart_nonce_prefix}"
            f"cd {shlex.quote(self._live_workspace_path())} && "
            f"node {shlex.quote(self._live_preview_build_watch_script_path())}"
        )
        static_preview_command = (
            f"export TALMUDPEDIA_LIVE_PREVIEW_SCRIPTS_VERSION={shlex.quote(scripts_version)} && "
            f"{restart_nonce_prefix}"
            f"cd {shlex.quote(self._live_workspace_path())} && "
            f"python3 {shlex.quote(self._live_preview_static_server_script_path())}"
        )
        self._trace(
            "sprite.ensure_services.preview_plan",
            sprite_name=sprite_name,
            build_watch_service_name=self._build_watch_service_name(),
            preview_service_name=self._preview_service_name(),
            preview_port=self._preview_port(),
            scripts_version=scripts_version,
        )
        await self._ensure_service_running(
            sprite_name=sprite_name,
            service_name=self._build_watch_service_name(),
            payload=self._service_command(build_watch_command),
            force_restart=force_restart,
        )
        await self._ensure_service_running(
            sprite_name=sprite_name,
            service_name=self._preview_service_name(),
            payload={
                **self._service_command(static_preview_command),
                "http_port": self._preview_port(),
            },
            force_restart=force_restart,
        )
        preview_service = await self._get_service(sprite_name=sprite_name, service_name=self._preview_service_name())
        self._trace(
            "sprite.ensure_services.preview_live_service",
            sprite_name=sprite_name,
            service_name=self._preview_service_name(),
            live_cmd=preview_service.get("cmd") if isinstance(preview_service, dict) else None,
            live_args=preview_service.get("args") if isinstance(preview_service, dict) else None,
            live_http_port=preview_service.get("http_port") if isinstance(preview_service, dict) else None,
            live_state=preview_service.get("state") if isinstance(preview_service, dict) else None,
        )

    async def _ensure_opencode_service(self, *, sprite_name: str) -> None:
        live_workspace_path = self._live_workspace_path()
        opencode_command = str(
            self.config.sprite_opencode_command
            or f"cd {shlex.quote(live_workspace_path)} && "
            f"{build_official_opencode_bootstrap_command(host='0.0.0.0', port=self._opencode_port())}"
        ).strip()
        self._trace(
            "sprite.ensure_services.opencode_plan",
            sprite_name=sprite_name,
            opencode_service_name=self._opencode_service_name(),
            opencode_port=self._opencode_port(),
            opencode_command=opencode_command,
        )
        await self._ensure_service_running(
            sprite_name=sprite_name,
            service_name=self._opencode_service_name(),
            payload=self._service_command(opencode_command),
        )

    async def _wait_for_preview_ready(self, *, sprite_name: str) -> None:
        self._trace(
            "sprite.preview.wait_ready.begin",
            sprite_name=sprite_name,
            preview_service_name=self._preview_service_name(),
            preview_port=self._preview_port(),
        )
        script = f"""
import sys
import time
import json
import urllib.request

deadline = time.time() + 45
last_error = "preview service did not become ready"

def fetch(path: str):
    url = f"http://127.0.0.1:{self._preview_port()}{{path}}"
    with urllib.request.urlopen(url, timeout=4.0) as response:
        return response.status, response.read().decode("utf-8", errors="ignore")

while time.time() < deadline:
    try:
        status_code, raw_status = fetch("/_talmudpedia/status")
        payload = json.loads(raw_status or "{{}}") if raw_status else {{}}
        live_status = str(payload.get("status") or "").strip().lower()
        last_successful_build_id = str(payload.get("last_successful_build_id") or "").strip()
        if status_code == 200 and last_successful_build_id:
            root_status, _ = fetch("/")
            if root_status == 200:
                print("ready")
                sys.exit(0)
            last_error = f"preview root not ready: status={{root_status}}"
            time.sleep(0.75)
            continue
        if status_code == 200 and live_status in {{"failed_keep_last_good", "failed_no_build"}}:
            last_error = str(payload.get("error") or "preview build failed")
        else:
            last_error = f"preview status not ready: status={{status_code}} payload={{payload}}"
    except Exception as exc:
        last_error = str(exc)
    time.sleep(0.75)
print(last_error)
sys.exit(1)
""".strip()
        try:
            await self._exec_with_stdin(
                sprite_name=sprite_name,
                command=["python3", "-"],
                stdin_text=script,
                timeout_seconds=60,
                max_output_bytes=4000,
            )
        except Exception as exc:
            self._trace(
                "sprite.preview.wait_ready.failed",
                sprite_name=sprite_name,
                preview_service_name=self._preview_service_name(),
                preview_port=self._preview_port(),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise
        self._trace(
            "sprite.preview.wait_ready.done",
            sprite_name=sprite_name,
            preview_service_name=self._preview_service_name(),
            preview_port=self._preview_port(),
        )

    async def _read_live_preview_status(self, *, sprite_name: str) -> dict[str, Any]:
        script = f"""
import json
import pathlib

status_path = pathlib.Path({json.dumps(self._live_preview_status_path())})
if not status_path.exists():
    print(json.dumps({{"mode": "build_watch_static", "status": "booting"}}, sort_keys=True))
else:
    print(status_path.read_text(encoding="utf-8", errors="replace"))
""".strip()
        output, _ = await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=30,
            max_output_bytes=64_000,
        )
        try:
            payload = json.loads(output or "{}")
        except Exception as exc:
            raise PublishedAppSandboxBackendError(f"Invalid live preview status payload: {output[:280]}") from exc
        if not isinstance(payload, dict):
            raise PublishedAppSandboxBackendError("Live preview status payload is invalid.")
        return normalize_live_preview_payload(payload)

    async def _write_live_preview_context(
        self,
        *,
        sprite_name: str,
        workspace_fingerprint: str | None,
    ) -> None:
        payload = build_live_preview_context_payload(workspace_fingerprint=workspace_fingerprint)
        script = f"""
import json
import pathlib

context_path = pathlib.Path({json.dumps(self._live_preview_context_path())})
context_path.parent.mkdir(parents=True, exist_ok=True)
context_path.write_text({json.dumps(json.dumps(payload, sort_keys=True, indent=2))}, encoding="utf-8")
print(json.dumps({{"status": "ok"}}, sort_keys=True))
""".strip()
        await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=30,
            max_output_bytes=4_000,
        )

    async def _trigger_live_preview_rebuild(self, *, sprite_name: str) -> None:
        await self._exec(
            sprite_name=sprite_name,
            command=[
                "bash",
                "-lc",
                (
                    f"touch {shlex.quote(f'{self._live_workspace_path()}/index.html')} "
                    f"|| touch {shlex.quote(f'{self._live_workspace_path()}/src/main.tsx')}"
                ),
            ],
            timeout_seconds=30,
            max_output_bytes=2_000,
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
                os.path.dirname(f"{self._live_workspace_path()}/{_REVISION_FILE}"),
                self._stage_workspace_path(),
                self._live_preview_root_path(),
            ],
            timeout_seconds=60,
            max_output_bytes=2000,
        )

    async def _sync_files_to_workspace(self, *, sprite_name: str, workspace_path: str, files: Dict[str, str]) -> dict[str, Any]:
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
wrote_count = 0
skipped_count = 0
deleted_count = 0
for rel_path, content in payload.items():
    rel = str(rel_path or "").replace("\\\\", "/").lstrip("/")
    if not rel:
        continue
    managed.add(rel)
    target = workspace / rel
    rendered = str(content)
    if target.exists() and target.is_file():
        try:
            if target.read_text(encoding="utf-8") == rendered:
                skipped_count += 1
                continue
        except Exception:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    wrote_count += 1

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
    deleted_count += 1
    parent = existing.parent
    while parent != workspace and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent

revision_path = workspace / {json.dumps(_REVISION_FILE)}
revision_path.parent.mkdir(parents=True, exist_ok=True)
existing_revision_token = revision_path.read_text(encoding="utf-8", errors="replace").strip() if revision_path.exists() else ""
if wrote_count or deleted_count or not existing_revision_token:
    revision_token = base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")
    revision_path.write_text(revision_token, encoding="utf-8")
else:
    revision_token = existing_revision_token
print(json.dumps({{
    "revision_token": revision_token,
    "wrote_count": wrote_count,
    "skipped_count": skipped_count,
    "deleted_count": deleted_count,
}}, sort_keys=True))
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
        revision_token = str(normalized.get("revision_token") or "").strip()
        if not revision_token:
            raise PublishedAppSandboxBackendError("Sprite sync did not return a revision token.")
        return {
            "revision_token": revision_token,
            "wrote_count": max(0, int(normalized.get("wrote_count") or 0)),
            "skipped_count": max(0, int(normalized.get("skipped_count") or 0)),
            "deleted_count": max(0, int(normalized.get("deleted_count") or 0)),
        }

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

    async def _bump_revision_token(self, *, sprite_name: str, workspace_path: str) -> str:
        script = f"""
import base64
import json
import os
import pathlib

workspace = pathlib.Path({json.dumps(workspace_path)})
revision_path = workspace / {json.dumps(_REVISION_FILE)}
revision_path.parent.mkdir(parents=True, exist_ok=True)
revision_token = base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")
revision_path.write_text(revision_token, encoding="utf-8")
print(json.dumps({{"revision_token": revision_token}}, sort_keys=True))
""".strip()
        output, _ = await self._exec_with_stdin(
            sprite_name=sprite_name,
            command=["python3", "-"],
            stdin_text=script,
            timeout_seconds=30,
            max_output_bytes=2048,
        )
        normalized = json.loads(output or "{}")
        token = str(normalized.get("revision_token") or "").strip()
        if not token:
            raise PublishedAppSandboxBackendError("Sprite revision token update returned an empty token.")
        return token

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

    @staticmethod
    def _dependency_install_shell_command(*, prefer_offline: bool = True) -> str:
        npm_args = "--no-audit --no-fund"
        if prefer_offline:
            npm_args = f"{npm_args} --prefer-offline"
        pnpm_args = "--no-frozen-lockfile"
        if prefer_offline:
            pnpm_args = f"{pnpm_args} --prefer-offline"
        pnpm_cmd = f"pnpm install {pnpm_args}".strip()
        pnpm_corepack_cmd = f"corepack pnpm install {pnpm_args}".strip()
        yarn_cmd = "yarn install"
        yarn_corepack_cmd = "corepack yarn install"
        npm_ci_cmd = f"npm ci {npm_args}".strip()
        npm_install_cmd = f"npm install {npm_args}".strip()
        return (
            "if [ -f pnpm-lock.yaml ]; then "
            f"if command -v pnpm >/dev/null 2>&1; then {pnpm_cmd}; "
            f"elif command -v corepack >/dev/null 2>&1; then {pnpm_corepack_cmd}; "
            f"else {npm_install_cmd}; fi; "
            "elif [ -f yarn.lock ]; then "
            f"if command -v yarn >/dev/null 2>&1; then {yarn_cmd}; "
            f"elif command -v corepack >/dev/null 2>&1; then {yarn_corepack_cmd}; "
            f"else {npm_install_cmd}; fi; "
            f"elif [ -f package-lock.json ]; then {npm_ci_cmd}; "
            f"elif [ -f package.json ]; then {npm_install_cmd}; "
            "fi"
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
            self._trace(
                "sprite.dependencies.install_skipped",
                sprite_name=sprite_name,
                workspace_path=workspace_path,
                dependency_hash=dependency_hash,
            )
            return
        self._trace(
            "sprite.dependencies.install_begin",
            sprite_name=sprite_name,
            workspace_path=workspace_path,
            dependency_hash=dependency_hash,
            force_install=bool(force_install),
            has_existing_hash=bool(current_hash),
        )
        command = [
            "bash",
            "-lc",
            self._dependency_install_shell_command(prefer_offline=True),
        ]
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
        self._trace(
            "sprite.dependencies.install_done",
            sprite_name=sprite_name,
            workspace_path=workspace_path,
            dependency_hash=dependency_hash,
            force_install=bool(force_install),
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
        except Exception as exc:
            self._trace(
                "sprite.preview.repair.begin",
                sprite_name=sprite_name,
                workspace_path=workspace_path,
                dependency_hash=dependency_hash,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            await self._install_dependencies_if_needed(
                sprite_name=sprite_name,
                workspace_path=workspace_path,
                dependency_hash=dependency_hash,
                force_install=True,
            )
            await self._ensure_preview_service(sprite_name=sprite_name)
            await self._wait_for_preview_ready(sprite_name=sprite_name)
            self._trace(
                "sprite.preview.repair.done",
                sprite_name=sprite_name,
                workspace_path=workspace_path,
            )

    def _backend_metadata(
        self,
        *,
        sprite_name: str,
        sprite_url: str,
        preview_base_path: str,
        revision_token: str | None,
        live_preview: dict[str, Any] | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        normalized_live_preview = normalize_live_preview_payload(live_preview or {})
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
                "revision_token": revision_token,
            },
            "services": {
                "preview_service_name": self._preview_service_name(),
                "preview_port": self._preview_port(),
                "build_watch_service_name": self._build_watch_service_name(),
                "opencode_service_name": self._opencode_service_name(),
                "opencode_port": self._opencode_port(),
                "opencode_base_url": f"{str(sprite_url).rstrip('/')}:{self._opencode_port()}",
            },
            "preview_runtime": {
                "mode": LIVE_PREVIEW_MODE,
                "workspace_revision_token": revision_token,
                "last_error": str(last_error or "").strip() or None,
            },
            "live_preview": normalized_live_preview,
        }

    async def _heartbeat_metadata(self, *, sprite_name: str) -> dict[str, Any]:
        sprite = await self._get_sprite(sprite_name=sprite_name)
        if sprite is None:
            raise PublishedAppSandboxBackendError(f"Sprite request failed (404) for /v1/sprites/{sprite_name}: not found")
        sprite_url = str(sprite.get("url") or "").strip() or f"https://{sprite_name}.sprites.app"
        preview_service = await self._get_service(
            sprite_name=sprite_name,
            service_name=self._preview_service_name(),
        )
        build_watch_service = await self._get_service(
            sprite_name=sprite_name,
            service_name=self._build_watch_service_name(),
        )
        self._trace(
            "sprite.preview.heartbeat_state",
            sprite_name=sprite_name,
            preview_service_name=self._preview_service_name(),
            preview_state=preview_service.get("state") if isinstance(preview_service, dict) else None,
            preview_http_port=preview_service.get("http_port") if isinstance(preview_service, dict) else None,
            build_watch_state=build_watch_service.get("state") if isinstance(build_watch_service, dict) else None,
        )
        live_preview = self._with_live_preview_supervisor(
            live_preview=await self._read_live_preview_status(sprite_name=sprite_name),
            supervisor=self._live_preview_supervisor_summary(
                build_watch_service=build_watch_service,
                static_preview_service=preview_service,
            ),
        )
        return self._backend_metadata(
            sprite_name=sprite_name,
            sprite_url=sprite_url,
            preview_base_path="/",
            revision_token=await self._read_revision_token(
                sprite_name=sprite_name,
                workspace_path=self._live_workspace_path(),
            ),
            live_preview=live_preview,
        )

    async def _snapshot_workspace_files(self, *, sprite_name: str, workspace_path: str) -> dict[str, Any]:
        script = f"""
import hashlib
import json
import pathlib

root = pathlib.Path({json.dumps(workspace_path)})
files = {{}}
ignore_prefixes = tuple({json.dumps(list(_SNAPSHOT_IGNORE_PREFIXES))})
ignore_file_names = set({json.dumps(sorted(BUILDER_SNAPSHOT_IGNORED_FILE_NAMES))})
ignore_suffixes = tuple({json.dumps(list(BUILDER_SNAPSHOT_IGNORED_SUFFIXES))})
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(root).as_posix()
    lowered = rel.lower()
    if any(lowered == prefix.rstrip("/") or lowered.startswith(prefix) for prefix in ignore_prefixes):
        continue
    segments = [segment for segment in lowered.split("/") if segment]
    if "node_modules" in segments:
        continue
    name = path.name.lower()
    if name in ignore_file_names:
        continue
    if any(name.endswith(suffix) for suffix in ignore_suffixes):
        continue
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
        _ = organization_id, user_id, revision_id, idle_timeout_seconds
        sprite_name = self._sprite_name(prefix=self.config.sprite_name_prefix, app_id=app_id)
        workspace_fingerprint = build_live_preview_overlay_workspace_fingerprint(
            entry_file=entry_file,
            files=files,
            runtime_context=TemplateRuntimeContext(
                app_id=str(app_id or ""),
                app_public_id=str(app_public_id or ""),
                agent_id=str(agent_id or ""),
            ),
        )
        self._trace("sprite.start_session.begin", sprite_name=sprite_name, app_id=app_id, runtime_generation=runtime_generation)
        sprite = await self._ensure_sprite(sprite_name=sprite_name)
        sprite_url = str(sprite.get("url") or "").strip() or f"https://{sprite_name}.sprites.app"
        self._trace("sprite.start_session.sprite_ready", sprite_name=sprite_name, sprite_url=sprite_url)
        await self._ensure_workspace_dirs(sprite_name=sprite_name)
        self._trace("sprite.start_session.workspace_dirs_ready", sprite_name=sprite_name)
        sync_result = await self._sync_files_to_workspace(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            files=dict(files or {}),
        )
        revision_token = str(sync_result.get("revision_token") or "").strip()
        self._trace(
            "sprite.start_session.files_synced",
            sprite_name=sprite_name,
            revision_token=revision_token,
            wrote_count=int(sync_result.get("wrote_count") or 0),
            skipped_count=int(sync_result.get("skipped_count") or 0),
            deleted_count=int(sync_result.get("deleted_count") or 0),
        )
        await self._install_dependencies_if_needed(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
            force_install=False,
        )
        await self._write_live_preview_context(
            sprite_name=sprite_name,
            workspace_fingerprint=workspace_fingerprint,
        )
        await self._ensure_preview_service(sprite_name=sprite_name)
        await self._ensure_preview_ready_with_repair(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
        )
        live_preview = self._with_live_preview_supervisor(
            live_preview=await self._read_live_preview_status(sprite_name=sprite_name),
            supervisor=self._live_preview_supervisor_summary(
                build_watch_service=await self._get_service(
                    sprite_name=sprite_name,
                    service_name=self._build_watch_service_name(),
                ),
                static_preview_service=await self._get_service(
                    sprite_name=sprite_name,
                    service_name=self._preview_service_name(),
                ),
            ),
        )
        self._trace("sprite.start_session.preview_ready", sprite_name=sprite_name, revision_token=revision_token)
        return {
            "sandbox_id": sprite_name,
            "status": "serving",
            "runtime_backend": self.backend_name,
            "runtime_generation": int(runtime_generation or 0),
            "workspace_path": self._live_workspace_path(),
            "live_workspace_path": self._live_workspace_path(),
            "preview_service_name": self._preview_service_name(),
            "opencode_service_name": self._opencode_service_name(),
            "preview_url": preview_base_path,
            "backend_metadata": self._backend_metadata(
                sprite_name=sprite_name,
                sprite_url=sprite_url,
                preview_base_path=preview_base_path,
                revision_token=revision_token,
                live_preview=live_preview,
            ),
        }

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
        _ = idle_timeout_seconds
        sprite_name = str(sandbox_id or "").strip()
        workspace_fingerprint = build_live_preview_overlay_workspace_fingerprint(
            entry_file=entry_file,
            files=files,
            runtime_context=TemplateRuntimeContext(
                app_id=str(app_id or ""),
                app_public_id=str(app_public_id or ""),
                agent_id=str(agent_id or ""),
            ),
        )
        self._trace("sprite.sync_session.begin", sprite_name=sprite_name, sandbox_id=sandbox_id)
        sprite = await self._ensure_sprite(sprite_name=sprite_name)
        sprite_url = str(sprite.get("url") or "").strip() or f"https://{sprite_name}.sprites.app"
        self._trace("sprite.sync_session.sprite_ready", sprite_name=sprite_name, sprite_url=sprite_url)
        await self._ensure_workspace_dirs(sprite_name=sprite_name)
        self._trace("sprite.sync_session.workspace_dirs_ready", sprite_name=sprite_name)
        sync_result = await self._sync_files_to_workspace(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            files=dict(files or {}),
        )
        revision_token = str(sync_result.get("revision_token") or "").strip()
        self._trace(
            "sprite.sync_session.files_synced",
            sprite_name=sprite_name,
            revision_token=revision_token,
            wrote_count=int(sync_result.get("wrote_count") or 0),
            skipped_count=int(sync_result.get("skipped_count") or 0),
            deleted_count=int(sync_result.get("deleted_count") or 0),
        )
        await self._install_dependencies_if_needed(
            sprite_name=sprite_name,
            workspace_path=self._live_workspace_path(),
            dependency_hash=dependency_hash,
            force_install=bool(install_dependencies),
        )
        await self._write_live_preview_context(
            sprite_name=sprite_name,
            workspace_fingerprint=workspace_fingerprint,
        )
        live_preview = self._with_live_preview_supervisor(
            live_preview=await self._read_live_preview_status(sprite_name=sprite_name),
            supervisor=self._live_preview_supervisor_summary(
                build_watch_service=await self._get_service(
                    sprite_name=sprite_name,
                    service_name=self._build_watch_service_name(),
                ),
                static_preview_service=await self._get_service(
                    sprite_name=sprite_name,
                    service_name=self._preview_service_name(),
                ),
            ),
        )
        self._trace(
            "sprite.sync_session.preview_status",
            sprite_name=sprite_name,
            revision_token=revision_token,
            live_preview_status=live_preview.get("status"),
            last_successful_build_id=live_preview.get("last_successful_build_id"),
        )
        metadata = self._backend_metadata(
            sprite_name=sprite_name,
            sprite_url=sprite_url,
            preview_base_path=preview_base_path or "/",
            revision_token=revision_token,
            live_preview=live_preview,
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
        metadata = await self._heartbeat_metadata(sprite_name=sprite_name)
        workspace_metadata = (
            dict(metadata.get("workspace") or {})
            if isinstance(metadata.get("workspace"), dict)
            else {}
        )
        revision_token = str(workspace_metadata.get("revision_token") or "").strip() or None
        if self._live_preview_needs_service_refresh(live_preview=metadata.get("live_preview")):
            self._trace(
                "sprite.preview.heartbeat_refresh.begin",
                sprite_name=sprite_name,
                reason="service_not_running_or_status_missing",
            )
            await self._ensure_preview_service(sprite_name=sprite_name)
            metadata = await self._heartbeat_metadata(sprite_name=sprite_name)
            workspace_metadata = (
                dict(metadata.get("workspace") or {})
                if isinstance(metadata.get("workspace"), dict)
                else {}
            )
            revision_token = str(workspace_metadata.get("revision_token") or "").strip() or None
            if isinstance(metadata.get("live_preview"), dict):
                metadata["live_preview"] = self._with_live_preview_supervisor(
                    live_preview=metadata.get("live_preview"),
                    supervisor={
                        **dict(metadata["live_preview"].get("supervisor") or {}),
                        "restart_reason": "heartbeat_refresh",
                    },
                )
            self._trace(
                "sprite.preview.heartbeat_refresh.done",
                sprite_name=sprite_name,
            )
        if self._live_preview_requires_rebuild(
            revision_token=revision_token,
            live_preview=metadata.get("live_preview"),
        ):
            self._trace(
                "sprite.preview.heartbeat_rebuild.begin",
                sprite_name=sprite_name,
                revision_token=revision_token,
                last_trigger_revision_token=str(
                    (metadata.get("live_preview") or {}).get("debug_last_trigger_revision_token") or ""
                ).strip()
                or None,
            )
            await self._ensure_preview_service(
                sprite_name=sprite_name,
                force_restart=True,
            )
            await self._trigger_live_preview_rebuild(sprite_name=sprite_name)
            metadata = await self._heartbeat_metadata(sprite_name=sprite_name)
            if isinstance(metadata.get("live_preview"), dict):
                metadata["live_preview"] = self._with_live_preview_supervisor(
                    live_preview=metadata.get("live_preview"),
                    supervisor={
                        **dict(metadata["live_preview"].get("supervisor") or {}),
                        "restart_reason": "heartbeat_rebuild",
                    },
                )
            self._trace(
                "sprite.preview.heartbeat_rebuild.done",
                sprite_name=sprite_name,
                revision_token=revision_token,
            )
        try:
            await self._wait_for_preview_ready(sprite_name=sprite_name)
        except Exception as exc:
            self._trace(
                "sprite.preview.heartbeat_repair.begin",
                sprite_name=sprite_name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            await self._ensure_preview_service(sprite_name=sprite_name)
            await self._wait_for_preview_ready(sprite_name=sprite_name)
            metadata = await self._heartbeat_metadata(sprite_name=sprite_name)
            if isinstance(metadata.get("live_preview"), dict):
                metadata["live_preview"] = self._with_live_preview_supervisor(
                    live_preview=metadata.get("live_preview"),
                    supervisor={
                        **dict(metadata["live_preview"].get("supervisor") or {}),
                        "restart_reason": "heartbeat_repair",
                        "failure_reason": str(exc),
                    },
                )
            self._trace(
                "sprite.preview.heartbeat_repair.done",
                sprite_name=sprite_name,
            )
        return {
            "sandbox_id": sprite_name,
            "status": "serving",
            "runtime_backend": self.backend_name,
            "backend_metadata": metadata,
        }

    async def stop_session(self, *, sandbox_id: str) -> Dict[str, Any]:
        sprite_name = str(sandbox_id or "").strip()
        self._opencode_clients_by_sandbox.pop(sprite_name, None)
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
        revision_token = await self._bump_revision_token(
            sprite_name=sandbox_id,
            workspace_path=self._live_workspace_path(),
        )
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
        destination = f"{self._live_workspace_path()}/{normalized}"
        write_script = "\n".join(
            [
                "import pathlib",
                "import sys",
                f"destination = pathlib.Path({json.dumps(destination)})",
                "destination.parent.mkdir(parents=True, exist_ok=True)",
                "destination.write_text(sys.stdin.read(), encoding='utf-8')",
            ]
        )
        await self._exec_with_stdin(
            sprite_name=sandbox_id,
            command=["python3", "-c", write_script],
            stdin_text=str(content if isinstance(content, str) else str(content)),
            timeout_seconds=30,
            max_output_bytes=4000,
        )
        revision_token = await self._bump_revision_token(
            sprite_name=sandbox_id,
            workspace_path=self._live_workspace_path(),
        )
        return {
            "sandbox_id": sandbox_id,
            "path": normalized,
            "status": "written",
            "revision_token": revision_token,
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
        revision_token = await self._bump_revision_token(
            sprite_name=sandbox_id,
            workspace_path=self._live_workspace_path(),
        )
        return {
            "sandbox_id": sandbox_id,
            "path": normalized,
            "status": "deleted",
            "revision_token": revision_token,
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
        revision_token = await self._bump_revision_token(
            sprite_name=sandbox_id,
            workspace_path=self._live_workspace_path(),
        )
        return {
            "sandbox_id": sandbox_id,
            "from_path": src,
            "to_path": dst,
            "status": "renamed",
            "revision_token": revision_token,
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
        workspace_path = self._live_workspace_path()
        if workspace_name == "stage":
            workspace_path = self._stage_workspace_path()
        elif workspace_name != "live":
            raise PublishedAppSandboxBackendError(f"Unsupported workspace scope: {workspace}")
        payload = await self._snapshot_workspace_files(sprite_name=sandbox_id, workspace_path=workspace_path)
        payload["sandbox_id"] = sandbox_id
        payload["workspace"] = workspace_name
        payload["workspace_path"] = workspace_path
        return payload

    async def promote_stage_workspace(self, *, sandbox_id: str) -> Dict[str, Any]:
        return {
            "sandbox_id": sandbox_id,
            "status": "promoted",
            "live_workspace_path": self._live_workspace_path(),
            "stage_workspace_path": self._live_workspace_path(),
        }

    async def update_live_preview_context(
        self,
        *,
        sandbox_id: str,
        workspace_fingerprint: str | None,
    ) -> Dict[str, Any]:
        await self._write_live_preview_context(
            sprite_name=sandbox_id,
            workspace_fingerprint=workspace_fingerprint,
        )
        return {
            "sandbox_id": sandbox_id,
            "status": "updated",
            "workspace_fingerprint": str(workspace_fingerprint or "").strip() or None,
        }

    async def prepare_publish_dependencies(self, *, sandbox_id: str, workspace_path: str) -> Dict[str, Any]:
        live_workspace_path = self._live_workspace_path()
        normalized_workspace_path = str(workspace_path or "").strip() or live_workspace_path
        if normalized_workspace_path == live_workspace_path:
            _, node_modules_exit = await self._exec(
                sprite_name=sandbox_id,
                command=["test", "-d", f"{live_workspace_path}/node_modules"],
                timeout_seconds=10,
                max_output_bytes=256,
                allow_nonzero=True,
            )
            if node_modules_exit == 0:
                return {
                    "sandbox_id": sandbox_id,
                    "workspace_path": normalized_workspace_path,
                    "live_workspace_path": live_workspace_path,
                    "status": "reused",
                    "strategy": "live",
                    "reason": "reused live workspace node_modules",
                    "revision_token": await self._read_revision_token(
                        sprite_name=sandbox_id,
                        workspace_path=live_workspace_path,
                    ),
                }
        await self._exec(
            sprite_name=sandbox_id,
            command=["bash", "-lc", self._dependency_install_shell_command(prefer_offline=False)],
            cwd=normalized_workspace_path,
            timeout_seconds=max(300, self.config.sprite_command_timeout_seconds),
            max_output_bytes=120_000,
        )
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": normalized_workspace_path,
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
        sync_result = await self._sync_files_to_workspace(
            sprite_name=sandbox_id,
            workspace_path=workspace_path,
            files=files,
        )
        return {
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "file_count": len(files or {}),
            "revision_token": str(sync_result.get("revision_token") or "").strip() or None,
            "wrote_count": max(0, int(sync_result.get("wrote_count") or 0)),
            "skipped_count": max(0, int(sync_result.get("skipped_count") or 0)),
            "deleted_count": max(0, int(sync_result.get("deleted_count") or 0)),
        }

    async def resolve_workspace_path(self, *, sandbox_id: str) -> str | None:
        _ = sandbox_id
        return self._live_workspace_path()

    async def _build_opencode_client(self, *, sandbox_id: str, force_refresh: bool = False):
        from app.services.opencode_server_client import OpenCodeServerClient, OpenCodeServerClientConfig

        cache_key = str(sandbox_id or "").strip()
        if not cache_key:
            raise PublishedAppSandboxBackendError("Sandbox id is required for Sprite OpenCode client.")
        if not force_refresh:
            await self._ensure_opencode_service(sprite_name=cache_key)
            cached = self._opencode_clients_by_sandbox.get(cache_key)
            if cached is not None:
                return cached

        await self._ensure_opencode_service(sprite_name=cache_key)
        tunnel_base_url = await get_sprite_proxy_tunnel_manager().ensure_tunnel(
            api_base_url=self._api_base(),
            api_token=self._api_token(),
            sprite_name=cache_key,
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
        self._opencode_clients_by_sandbox[cache_key] = client
        return client

    @staticmethod
    def _is_refreshable_opencode_transport_error(exc: Exception) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if isinstance(current, httpx.HTTPError):
                return True
            name = current.__class__.__name__
            message = str(current or "").strip().lower()
            if name in {"RemoteProtocolError", "ConnectError", "ReadError", "WriteError", "PoolTimeout"}:
                return True
            if "server disconnected without sending a response" in message:
                return True
            current = current.__cause__ or current.__context__
        return False

    async def _retry_opencode_call_after_refresh(
        self,
        *,
        sandbox_id: str,
        operation: str,
        exc: Exception,
    ):
        if not self._is_refreshable_opencode_transport_error(exc):
            raise exc
        self._trace(
            "sprite.opencode.retrying_after_refresh",
            sprite_name=sandbox_id,
            service_name=self._opencode_service_name(),
            operation=operation,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        return await self._build_opencode_client(sandbox_id=sandbox_id, force_refresh=True)

    async def ensure_opencode_endpoint(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> PublishedAppOpenCodeEndpoint:
        client = await self._build_opencode_client(sandbox_id=sandbox_id)
        base_url = str(getattr(getattr(client, "_config", None), "base_url", "") or "").strip()
        resolved_workspace_path = str(workspace_path or self._live_workspace_path()).strip() or self._live_workspace_path()
        if not base_url:
            raise PublishedAppSandboxBackendError("Sprite OpenCode tunnel did not provide a base URL.")
        return PublishedAppOpenCodeEndpoint(
            sandbox_id=str(sandbox_id),
            base_url=base_url,
            workspace_path=resolved_workspace_path,
        )
