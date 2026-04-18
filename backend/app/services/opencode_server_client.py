from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, AsyncGenerator
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientError,
)
from app.services.published_app_templates import (
    OPENCODE_BOOTSTRAP_CONTEXT_PATH,
    build_opencode_bootstrap_files,
)
from app.services.published_app_coding_pipeline_trace import pipeline_trace


class OpenCodeServerClientError(Exception):
    pass


logger = logging.getLogger(__name__)

OPENCODE_DEPRECATED_TOOL_PATHS = (
    ".opencode/tools/coding_agent_get_agent_integration_contract.ts",
    ".opencode/tools/coding_agent_describe_selected_agent_contract.ts",
)

_OFFICIAL_ID_PREFIXES = {
    "message": "msg",
    "part": "prt",
}
_OFFICIAL_ID_LOCK = Lock()
_OFFICIAL_ID_LAST_TIMESTAMP_MS = 0
_OFFICIAL_ID_COUNTER = 0
_OFFICIAL_ID_RANDOM_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _opencode_trace(event: str, **fields: Any) -> None:
    pipeline_trace(event, pipeline="opencode_client", **fields)


@dataclass(frozen=True)
class OpenCodeServerClientConfig:
    enabled: bool
    base_url: str | None
    api_key: str | None
    request_timeout_seconds: float
    connect_timeout_seconds: float
    health_cache_seconds: int
    sandbox_controller_mode_override: bool | None = None
    extra_headers: dict[str, str] | None = None
    skip_workspace_bootstrap: bool = False


class OpenCodeServerClient:
    def __init__(self, config: OpenCodeServerClientConfig):
        self._config = config
        self._health_checked_at: datetime | None = None
        self._health_ok = False
        self._api_mode: str | None = None
        self._official_run_state: dict[tuple[str, str], dict[str, Any]] = {}
        self._official_latest_turn_ref_by_session: dict[str, str] = {}
        self._official_latest_assistant_message_id_by_session: dict[str, str] = {}
        self._official_request_kind_by_session: dict[str, dict[str, str]] = {}
        self._sandbox_runtime_client = PublishedAppDraftDevRuntimeClient.from_env()
        self._sandbox_official_clients: dict[str, OpenCodeServerClient] = {}
        self._sandbox_turn_ref_to_sandbox_id: dict[str, str] = {}
        self._sandbox_turn_ref_to_session_id: dict[str, str] = {}
        self._sandbox_bootstrap_hash: dict[str, str] = {}
        self._sandbox_context_hash: dict[str, str] = {}
        self._host_bootstrap_hash: dict[str, str] = {}
        self._host_context_hash: dict[str, str] = {}
        self._bootstrap_cleanup_done_targets: set[str] = set()

    @staticmethod
    def _official_state_key(*, session_id: str, turn_ref: str) -> tuple[str, str]:
        return (str(session_id or "").strip(), str(turn_ref or "").strip())

    def _official_state_get(self, *, session_id: str, turn_ref: str) -> dict[str, Any] | None:
        return self._official_run_state.get(self._official_state_key(session_id=session_id, turn_ref=turn_ref))

    def _official_state_setdefault(
        self,
        *,
        session_id: str,
        turn_ref: str,
        default: dict[str, Any],
    ) -> dict[str, Any]:
        key = self._official_state_key(session_id=session_id, turn_ref=turn_ref)
        return self._official_run_state.setdefault(key, default)

    def _official_state_pop(self, *, session_id: str, turn_ref: str) -> dict[str, Any] | None:
        key = self._official_state_key(session_id=session_id, turn_ref=turn_ref)
        if self._official_latest_turn_ref_by_session.get(str(session_id)) == str(turn_ref):
            self._official_latest_turn_ref_by_session.pop(str(session_id), None)
        return self._official_run_state.pop(key, None)

    def _remember_latest_assistant_message_id(self, *, session_id: str, message_id: str | None) -> None:
        resolved_session_id = str(session_id or "").strip()
        resolved_message_id = str(message_id or "").strip()
        if not resolved_session_id or not resolved_message_id:
            return
        self._official_latest_assistant_message_id_by_session[resolved_session_id] = resolved_message_id

    def _remember_request_kind(self, *, session_id: str, request_id: str, kind: str) -> None:
        resolved_session_id = str(session_id or "").strip()
        resolved_request_id = str(request_id or "").strip()
        resolved_kind = str(kind or "").strip().lower()
        if not resolved_session_id or not resolved_request_id or resolved_kind not in {"permission", "question"}:
            return
        self._official_request_kind_by_session.setdefault(resolved_session_id, {})[resolved_request_id] = resolved_kind

    def _pop_request_kind(self, *, session_id: str, request_id: str) -> str | None:
        resolved_session_id = str(session_id or "").strip()
        resolved_request_id = str(request_id or "").strip()
        if not resolved_session_id or not resolved_request_id:
            return None
        session_requests = self._official_request_kind_by_session.get(resolved_session_id)
        if not isinstance(session_requests, dict):
            return None
        kind = str(session_requests.pop(resolved_request_id, "") or "").strip().lower() or None
        if not session_requests:
            self._official_request_kind_by_session.pop(resolved_session_id, None)
        return kind

    @staticmethod
    def _infer_request_kind_from_id(request_id: str) -> str | None:
        normalized = str(request_id or "").strip().lower()
        if normalized.startswith("que_"):
            return "question"
        if normalized.startswith("per_"):
            return "permission"
        return None

    @staticmethod
    def _official_id_prefix(kind: str) -> str:
        prefix = _OFFICIAL_ID_PREFIXES.get(str(kind or "").strip().lower())
        if not prefix:
            raise OpenCodeServerClientError(f"Unsupported OpenCode identifier kind: {kind}")
        return prefix

    @staticmethod
    def _random_base62(length: int) -> str:
        if length <= 0:
            return ""
        raw = os.urandom(length)
        return "".join(_OFFICIAL_ID_RANDOM_ALPHABET[item % len(_OFFICIAL_ID_RANDOM_ALPHABET)] for item in raw)

    @classmethod
    def generate_official_id(cls, kind: str) -> str:
        global _OFFICIAL_ID_LAST_TIMESTAMP_MS, _OFFICIAL_ID_COUNTER

        prefix = cls._official_id_prefix(kind)
        with _OFFICIAL_ID_LOCK:
            current_timestamp_ms = int(time.time() * 1000)
            if current_timestamp_ms != _OFFICIAL_ID_LAST_TIMESTAMP_MS:
                _OFFICIAL_ID_LAST_TIMESTAMP_MS = current_timestamp_ms
                _OFFICIAL_ID_COUNTER = 0
            _OFFICIAL_ID_COUNTER += 1
            now = current_timestamp_ms * 0x1000 + _OFFICIAL_ID_COUNTER
        time_hex = f"{now:012x}"[-12:]
        return f"{prefix}_{time_hex}{cls._random_base62(14)}"

    @classmethod
    def normalize_message_id(cls, raw_message_id: str | None) -> str:
        candidate = str(raw_message_id or "").strip()
        if candidate.startswith(f"{cls._official_id_prefix('message')}_"):
            return candidate
        return cls.generate_official_id("message")

    @classmethod
    def normalize_request_parts(cls, parts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in parts or []:
            if not isinstance(item, dict):
                continue
            part = dict(item)
            part_id = str(part.get("id") or "").strip()
            if not part_id.startswith(f"{cls._official_id_prefix('part')}_"):
                part["id"] = cls.generate_official_id("part")
            normalized.append(part)
        return normalized

    @staticmethod
    def _merge_official_extra_headers(
        extra_headers: dict[str, str] | None,
        *,
        workspace_path: str,
    ) -> dict[str, str] | None:
        merged = {
            str(key): str(value)
            for key, value in (extra_headers or {}).items()
            if str(key).strip() and str(value).strip()
        }
        resolved_workspace_path = str(workspace_path or "").strip()
        if resolved_workspace_path and "x-opencode-directory" not in {key.lower(): value for key, value in merged.items()}:
            merged["x-opencode-directory"] = quote(resolved_workspace_path, safe="")
        return merged or None

    async def _get_sandbox_official_client(
        self,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> tuple["OpenCodeServerClient", str]:
        resolved_sandbox_id = str(sandbox_id or "").strip()
        if not resolved_sandbox_id:
            raise OpenCodeServerClientError("OpenCode sandbox mode requires sandbox_id.")
        try:
            endpoint = await self._sandbox_runtime_client.ensure_opencode_endpoint(
                sandbox_id=resolved_sandbox_id,
                workspace_path=workspace_path,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            raise OpenCodeServerClientError(f"OpenCode sandbox endpoint discovery failed: {exc}") from exc

        base_url = str(getattr(endpoint, "base_url", "") or "").strip()
        resolved_workspace_path = str(getattr(endpoint, "workspace_path", "") or workspace_path or "").strip()
        extra_headers = self._merge_official_extra_headers(
            getattr(endpoint, "extra_headers", None),
            workspace_path=resolved_workspace_path,
        )
        api_key = str(getattr(endpoint, "api_key", "") or "").strip() or None
        if not base_url:
            raise OpenCodeServerClientError("OpenCode sandbox endpoint discovery returned no base_url.")

        cached = self._sandbox_official_clients.get(resolved_sandbox_id)
        cached_config = getattr(cached, "_config", None)
        cached_base_url = str(getattr(cached_config, "base_url", "") or "").strip()
        cached_api_key = str(getattr(cached_config, "api_key", "") or "").strip() or None
        cached_headers = getattr(cached_config, "extra_headers", None)
        if (
            cached is not None
            and cached_base_url == base_url
            and cached_api_key == api_key
            and cached_headers == extra_headers
        ):
            return cached, resolved_workspace_path

        client = OpenCodeServerClient(
            OpenCodeServerClientConfig(
                enabled=True,
                base_url=base_url,
                api_key=api_key,
                request_timeout_seconds=self._config.request_timeout_seconds,
                connect_timeout_seconds=self._config.connect_timeout_seconds,
                health_cache_seconds=self._config.health_cache_seconds,
                sandbox_controller_mode_override=False,
                extra_headers=extra_headers if isinstance(extra_headers, dict) else None,
                skip_workspace_bootstrap=True,
            )
        )
        self._sandbox_official_clients[resolved_sandbox_id] = client
        return client, resolved_workspace_path

    @staticmethod
    def _seed_bootstrap_files_on_run_start() -> bool:
        raw = str(
            os.getenv("APPS_CODING_AGENT_OPENCODE_SEED_BOOTSTRAP_ON_RUN_START", "0")
            or "0"
        ).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @classmethod
    def from_env(cls) -> "OpenCodeServerClient":
        enabled = (os.getenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "0").strip().lower() not in {"0", "false", "off", "no"})
        base_url = (os.getenv("APPS_CODING_AGENT_OPENCODE_BASE_URL") or "").strip() or None
        api_key = (os.getenv("APPS_CODING_AGENT_OPENCODE_API_KEY") or "").strip() or None
        request_timeout = float(os.getenv("APPS_CODING_AGENT_OPENCODE_REQUEST_TIMEOUT_SECONDS", "20").strip())
        connect_timeout = float(os.getenv("APPS_CODING_AGENT_OPENCODE_CONNECT_TIMEOUT_SECONDS", "5").strip())
        health_cache_seconds = int(os.getenv("APPS_CODING_AGENT_OPENCODE_HEALTH_CACHE_SECONDS", "15").strip())
        return cls(
            OpenCodeServerClientConfig(
                enabled=enabled,
                base_url=base_url,
                api_key=api_key,
                request_timeout_seconds=max(3.0, request_timeout),
                connect_timeout_seconds=max(1.0, connect_timeout),
                health_cache_seconds=max(3, health_cache_seconds),
            )
        )

    @property
    def is_enabled(self) -> bool:
        if self._sandbox_runtime_mode_enabled():
            return True
        if not self._config.enabled:
            return False
        return bool(self._config.base_url)

    def _sandbox_runtime_mode_enabled(self) -> bool:
        if self._config.sandbox_controller_mode_override is not None:
            return bool(self._config.sandbox_controller_mode_override)
        backend_name = str(getattr(self._sandbox_runtime_client, "backend_name", "") or "").strip().lower()
        if backend_name == "sprite":
            return True
        explicit = (os.getenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER") or "").strip().lower()
        if explicit:
            return explicit in {"1", "true", "yes", "on"}
        if backend_name in {"local", "controller", "sprite", "e2b"}:
            return True
        return bool((os.getenv("APPS_SANDBOX_CONTROLLER_URL") or "").strip())

    async def ensure_healthy(self, *, force: bool = False) -> None:
        if not self.is_enabled:
            raise OpenCodeServerClientError(
                "OpenCode engine is disabled. Configure sandbox mode via "
                "APPS_SANDBOX_CONTROLLER_URL/APPS_DRAFT_DEV_CONTROLLER_URL, "
                "or set APPS_CODING_AGENT_OPENCODE_ENABLED=1 with "
                "APPS_CODING_AGENT_OPENCODE_BASE_URL for host mode."
            )
        if self._sandbox_runtime_mode_enabled():
            if not str(getattr(self._sandbox_runtime_client, "backend_name", "") or "").strip():
                raise OpenCodeServerClientError(
                    "OpenCode sandbox mode is enabled but no draft-dev sandbox backend is configured."
                )
            self._health_checked_at = datetime.now(timezone.utc)
            self._health_ok = True
            return

        now = datetime.now(timezone.utc)
        if not force and self._health_checked_at is not None:
            if now - self._health_checked_at <= timedelta(seconds=self._config.health_cache_seconds):
                if self._health_ok:
                    return
                raise OpenCodeServerClientError("OpenCode engine health check is currently failing.")

        if force:
            self._api_mode = None
        await self._ensure_api_mode()
        await self._request("GET", "/global/health", json_payload={}, retries=1, expect_json=True)
        self._health_checked_at = now
        self._health_ok = True

    async def create_session(
        self,
        *,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
        selected_agent_contract: dict[str, Any] | None = None,
    ) -> str:
        _ = model_id
        _opencode_trace(
            "opencode.session.create.requested",
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id or None,
            workspace_path=workspace_path,
            mode="sandbox" if self._sandbox_runtime_mode_enabled() else "host",
        )
        if self._sandbox_runtime_mode_enabled():
            sandbox_client, resolved_workspace_path = await self._get_sandbox_official_client(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
            )
            session_id = await sandbox_client.create_session(
                run_id=run_id,
                app_id=app_id,
                sandbox_id=sandbox_id,
                workspace_path=resolved_workspace_path,
                model_id=model_id,
                selected_agent_contract=selected_agent_contract,
            )
            _opencode_trace(
                "opencode.session.create.confirmed",
                run_id=run_id,
                app_id=app_id,
                sandbox_id=sandbox_id or None,
                session_id=session_id,
                mode="sandbox",
            )
            return session_id

        self._validate_official_workspace_path(workspace_path)
        await self._ensure_api_mode()
        session_payload: dict[str, Any] = {"title": f"App {app_id} session {run_id}"}
        permission_rules = self._build_official_session_permission_rules(workspace_path)
        if permission_rules:
            session_payload["permission"] = permission_rules
        session = await self._request("POST", "/session", json_payload=session_payload, retries=0)
        session_id = str(session.get("id") or session.get("sessionID") or session.get("sessionId") or "").strip()
        if not session_id:
            raise OpenCodeServerClientError("OpenCode server returned invalid session response (missing id).")
        self._official_latest_assistant_message_id_by_session[session_id] = ""
        _opencode_trace(
            "opencode.session.create.confirmed",
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id or None,
            session_id=session_id,
            mode="host",
        )
        return session_id

    async def get_session(
        self,
        *,
        session_id: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        resolved_session_id = str(session_id or "").strip()
        if not resolved_session_id:
            raise OpenCodeServerClientError("OpenCode session lookup requires session_id.")
        resolved_sandbox_id = str(sandbox_id or "").strip() or None
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            return await sandbox_client.get_session(session_id=resolved_session_id)
        await self._ensure_api_mode()
        payload = await self._request("GET", f"/session/{resolved_session_id}", json_payload={}, retries=0)
        if not isinstance(payload, dict):
            raise OpenCodeServerClientError("OpenCode session lookup returned invalid payload.")
        return payload

    async def list_messages(
        self,
        *,
        session_id: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        resolved_session_id = str(session_id or "").strip()
        if not resolved_session_id:
            raise OpenCodeServerClientError("OpenCode message listing requires session_id.")
        resolved_sandbox_id = str(sandbox_id or "").strip() or None
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            return await sandbox_client.list_messages(
                session_id=resolved_session_id,
                limit=limit,
            )
        await self._ensure_api_mode()
        path = f"/session/{resolved_session_id}/message"
        if limit is not None and int(limit) > 0:
            path = f"{path}?limit={int(limit)}"
        payload = await self._request("GET", path, json_payload={}, retries=0, expect_dict=False)
        if not isinstance(payload, list):
            raise OpenCodeServerClientError("OpenCode message listing returned invalid payload.")
        return [item for item in payload if isinstance(item, dict)]

    async def prompt_async(
        self,
        *,
        session_id: str,
        app_id: str,
        message_id: str,
        parts: list[dict[str, Any]],
        model_id: str | None = None,
        agent: str | None = None,
        no_reply: bool = False,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
        selected_agent_contract: dict[str, Any] | None = None,
    ) -> None:
        resolved_session_id = str(session_id or "").strip()
        resolved_message_id = str(message_id or "").strip()
        resolved_sandbox_id = str(sandbox_id or "").strip() or None
        resolved_workspace_path = str(workspace_path or "").strip()
        if not resolved_session_id:
            raise OpenCodeServerClientError("OpenCode prompt_async requires session_id.")
        resolved_message_id = self.normalize_message_id(resolved_message_id)
        normalized_parts = self.normalize_request_parts(parts)
        if not normalized_parts:
            raise OpenCodeServerClientError("OpenCode prompt_async requires at least one part.")
        if resolved_workspace_path:
            await self._seed_custom_tools_and_context(
                run_id=resolved_message_id,
                app_id=app_id,
                sandbox_id=resolved_sandbox_id or "",
                workspace_path=resolved_workspace_path,
                selected_agent_contract=selected_agent_contract,
            )
        payload: dict[str, Any] = {
            "messageID": resolved_message_id,
            "parts": normalized_parts,
        }
        model = self._to_official_model(str(model_id or "").strip())
        if model:
            payload["model"] = model
        if str(agent or "").strip():
            payload["agent"] = str(agent).strip()
        if no_reply:
            payload["noReply"] = True
        if str(system or "").strip():
            payload["system"] = str(system).strip()
        if isinstance(tools, dict) and tools:
            payload["tools"] = {str(key): bool(value) for key, value in tools.items()}
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=resolved_workspace_path,
            )
            await sandbox_client.prompt_async(
                session_id=resolved_session_id,
                app_id=app_id,
                message_id=resolved_message_id,
                parts=normalized_parts,
                model_id=model_id,
                agent=agent,
                no_reply=no_reply,
                system=system,
                tools=tools,
                selected_agent_contract=selected_agent_contract,
            )
            return
        await self._ensure_api_mode()
        await self._request(
            "POST",
            f"/session/{resolved_session_id}/prompt_async",
            json_payload=payload,
            retries=0,
            expect_json=False,
        )

    async def abort_session(
        self,
        *,
        session_id: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> bool:
        resolved_session_id = str(session_id or "").strip()
        if not resolved_session_id:
            raise OpenCodeServerClientError("OpenCode abort requires session_id.")
        resolved_sandbox_id = str(sandbox_id or "").strip() or None
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            return await sandbox_client.abort_session(session_id=resolved_session_id)
        await self._ensure_api_mode()
        payload = await self._request(
            "POST",
            f"/session/{resolved_session_id}/abort",
            json_payload={},
            retries=0,
            expect_json=False,
        )
        if payload in (None, "", b""):
            return True
        if isinstance(payload, bool):
            return payload
        if isinstance(payload, dict):
            for key in ("ok", "aborted", "cancelled"):
                if isinstance(payload.get(key), bool):
                    return bool(payload.get(key))
        return True

    async def reply_permission(
        self,
        *,
        session_id: str,
        permission_id: str,
        response: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> bool:
        resolved_session_id = str(session_id or "").strip()
        resolved_permission_id = str(permission_id or "").strip()
        resolved_response = str(response or "").strip().lower()
        resolved_sandbox_id = str(sandbox_id or "").strip() or None
        if resolved_response not in {"once", "always", "reject"}:
            raise OpenCodeServerClientError("OpenCode permission response must be one of once, always, reject.")
        if not resolved_session_id or not resolved_permission_id:
            raise OpenCodeServerClientError("OpenCode permission response requires session_id and permission_id.")
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            return await sandbox_client.reply_permission(
                session_id=resolved_session_id,
                permission_id=resolved_permission_id,
                response=resolved_response,
            )
        await self._ensure_api_mode()
        payload = await self._request(
            "POST",
            f"/session/{resolved_session_id}/permissions/{resolved_permission_id}",
            json_payload={"response": resolved_response},
            retries=0,
        )
        if isinstance(payload, bool):
            return payload
        if isinstance(payload, dict):
            ok = payload.get("ok")
            if isinstance(ok, bool):
                return ok
        return True

    async def reply_request(
        self,
        *,
        session_id: str,
        request_id: str,
        answers: list[list[str]],
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> bool:
        resolved_session_id = str(session_id or "").strip()
        resolved_request_id = str(request_id or "").strip()
        if not resolved_session_id or not resolved_request_id:
            raise OpenCodeServerClientError("OpenCode request response requires session_id and request_id.")
        normalized_answers: list[list[str]] = []
        for row in answers or []:
            if not isinstance(row, list):
                continue
            normalized_row = [str(item).strip() for item in row if str(item).strip()]
            if normalized_row:
                normalized_answers.append(normalized_row)
        if not normalized_answers:
            raise OpenCodeServerClientError("OpenCode request response requires at least one answer.")

        request_kind = self._pop_request_kind(session_id=resolved_session_id, request_id=resolved_request_id)
        if request_kind is None:
            request_kind = self._infer_request_kind_from_id(resolved_request_id)
        if request_kind == "question":
            return await self.answer_question(
                session_id=resolved_session_id,
                question_id=resolved_request_id,
                answers=normalized_answers,
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
            )

        first_answer = normalized_answers[0][0].strip().lower()
        response = "reject" if first_answer in {"deny", "reject", "no"} else "once"
        return await self.reply_permission(
            session_id=resolved_session_id,
            permission_id=resolved_request_id,
            response=response,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
        )

    async def stream_session_events(
        self,
        *,
        session_id: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        resolved_session_id = str(session_id or "").strip()
        if not resolved_session_id:
            raise OpenCodeServerClientError("OpenCode event stream requires session_id.")
        resolved_sandbox_id = str(sandbox_id or "").strip() or None
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            async for event in sandbox_client.stream_session_events(session_id=resolved_session_id):
                if isinstance(event, dict):
                    yield event
            return
        await self._ensure_api_mode()
        url = f"{self._config.base_url.rstrip('/')}/global/event"
        reconnect_delay_seconds = 0.25
        read_timeout_seconds = max(
            10.0,
            float((os.getenv("APPS_CODING_AGENT_OPENCODE_SESSION_EVENT_READ_TIMEOUT_SECONDS") or "30").strip()),
        )
        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_seconds,
            read=read_timeout_seconds,
            write=self._config.request_timeout_seconds,
            pool=self._config.request_timeout_seconds,
        )
        while True:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream("GET", url, headers=self._headers()) as response:
                        if response.status_code >= 400:
                            body = (await response.aread()).decode("utf-8", errors="replace").strip()
                            raise OpenCodeServerClientError(
                                f"OpenCode global event stream failed ({response.status_code}): {body or response.reason_phrase}"
                            )
                        async for line in response.aiter_lines():
                            raw = str(line or "").strip()
                            if not raw or raw.startswith(":"):
                                continue
                            if raw.startswith("data:"):
                                raw = raw[5:].strip()
                            if not raw:
                                continue
                            try:
                                event_wrapper = json.loads(raw)
                            except Exception:
                                continue
                            payload = self._extract_global_event_payload(event_wrapper)
                            if not isinstance(payload, dict):
                                continue
                            event_type = str(payload.get("type") or "").strip()
                            properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
                            if not event_type or not properties:
                                continue
                            event_session_id = self._extract_session_id_from_global_event_properties(properties)
                            if event_session_id != resolved_session_id:
                                continue
                            normalized = self._normalize_session_event(
                                session_id=resolved_session_id,
                                event_type=event_type,
                                properties=properties,
                            )
                            if normalized is not None:
                                yield normalized
            except asyncio.CancelledError:
                raise
            except GeneratorExit:
                raise
            except Exception as exc:
                _opencode_trace(
                    "opencode.session_event_stream.reconnect",
                    session_id=resolved_session_id,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                await asyncio.sleep(reconnect_delay_seconds)

    def _normalize_session_event(
        self,
        *,
        session_id: str,
        event_type: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        normalized_type = str(event_type or "").strip()
        if normalized_type == "message.updated":
            info = properties.get("info") if isinstance(properties.get("info"), dict) else {}
            return {
                "event": "message.updated",
                "session_id": session_id,
                "payload": {"info": info},
            }
        if normalized_type == "message.part.updated":
            part = properties.get("part") if isinstance(properties.get("part"), dict) else {}
            if not part:
                return None
            payload: dict[str, Any] = {"part": part}
            if "delta" in properties:
                payload["delta"] = properties.get("delta")
            return {
                "event": "message.part.updated",
                "session_id": session_id,
                "payload": payload,
            }
        if normalized_type == "message.part.removed":
            return {
                "event": "message.part.removed",
                "session_id": session_id,
                "payload": dict(properties),
            }
        if normalized_type == "session.status":
            return {
                "event": "session.status",
                "session_id": session_id,
                "payload": {"status": properties.get("status")},
            }
        if normalized_type == "session.idle":
            return {
                "event": "session.idle",
                "session_id": session_id,
                "payload": {},
            }
        if normalized_type == "session.error":
            return {
                "event": "session.error",
                "session_id": session_id,
                "payload": dict(properties),
            }
        if normalized_type == "permission.updated":
            mapped_permission = self._map_permission_asked_properties(properties)
            if mapped_permission is None:
                return None
            request_id = str(mapped_permission.get("request_id") or "").strip()
            if request_id:
                self._remember_request_kind(session_id=session_id, request_id=request_id, kind="permission")
            return {
                "event": "permission.updated",
                "session_id": session_id,
                "payload": mapped_permission,
            }
        if normalized_type == "question.asked":
            mapped_question = self._map_question_asked_properties(properties)
            if mapped_question is None:
                return None
            request_id = str(mapped_question.get("request_id") or "").strip()
            if request_id:
                self._remember_request_kind(session_id=session_id, request_id=request_id, kind="question")
            return {
                "event": "permission.updated",
                "session_id": session_id,
                "payload": mapped_question,
            }
        if normalized_type == "permission.replied":
            mapped_reply = self._map_question_reply_properties(properties)
            request_id = str(mapped_reply.get("request_id") or "").strip()
            if request_id:
                self._pop_request_kind(session_id=session_id, request_id=request_id)
            return {
                "event": "permission.replied",
                "session_id": session_id,
                "payload": mapped_reply,
            }
        if normalized_type in {"question.replied", "question.rejected", "permission.rejected"}:
            mapped_reply = self._map_question_reply_properties(properties)
            request_id = str(mapped_reply.get("request_id") or "").strip()
            if request_id:
                self._pop_request_kind(session_id=session_id, request_id=request_id)
            return {
                "event": "permission.replied",
                "session_id": session_id,
                "payload": mapped_reply,
            }
        return None

    async def submit_turn(
        self,
        *,
        session_id: str,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        recovery_messages: list[dict[str, str]] | None = None,
        selected_agent_contract: dict[str, Any] | None = None,
        defer_until_stream: bool = False,
    ) -> str:
        _opencode_trace(
            "opencode.turn.submit.requested",
            session_id=session_id,
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id or None,
            workspace_path=workspace_path,
            model_id=model_id,
            mode="sandbox" if self._sandbox_runtime_mode_enabled() else "host",
        )
        logger.info(
            "OPENCODE_START mode=%s run_id=%s app_id=%s sandbox_id=%s workspace_path=%s backend_name=%s override=%s base_url=%s",
            "sandbox" if self._sandbox_runtime_mode_enabled() else "host",
            run_id,
            app_id,
            sandbox_id or "",
            workspace_path,
            str(getattr(self._sandbox_runtime_client, "backend_name", "") or ""),
            self._config.sandbox_controller_mode_override,
            str(self._config.base_url or ""),
        )
        await self._seed_custom_tools_and_context(
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            selected_agent_contract=selected_agent_contract,
        )
        if self._sandbox_runtime_mode_enabled():
            sandbox_client, resolved_workspace_path = await self._get_sandbox_official_client(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
            )
            sandbox_submit_kwargs: dict[str, Any] = {
                "session_id": session_id,
                "run_id": run_id,
                "app_id": app_id,
                "sandbox_id": sandbox_id,
                "workspace_path": resolved_workspace_path,
                "model_id": model_id,
                "prompt": prompt,
                "recovery_messages": [item for item in recovery_messages or [] if isinstance(item, dict)],
                "selected_agent_contract": selected_agent_contract,
            }
            if defer_until_stream:
                sandbox_submit_kwargs["defer_until_stream"] = True
            try:
                turn_ref = await sandbox_client.submit_turn(**sandbox_submit_kwargs)
            except Exception as exc:
                _opencode_trace(
                    "opencode.turn.submit.failed",
                    session_id=session_id,
                    run_id=run_id,
                    app_id=app_id,
                    sandbox_id=sandbox_id or None,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                    mode="sandbox",
                )
                raise
            self._sandbox_turn_ref_to_sandbox_id[turn_ref] = sandbox_id
            self._sandbox_turn_ref_to_session_id[turn_ref] = session_id
            _opencode_trace(
                "opencode.turn.submit.confirmed",
                session_id=session_id,
                run_id=run_id,
                app_id=app_id,
                turn_ref=turn_ref,
                sandbox_id=sandbox_id or None,
                mode="sandbox",
            )
            return turn_ref

        self._validate_official_workspace_path(workspace_path)
        await self._ensure_api_mode()
        turn_ref = await self._submit_turn_official(
            session_id=session_id,
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            model_id=model_id,
            prompt=prompt,
            recovery_messages=[item for item in recovery_messages or [] if isinstance(item, dict)],
            defer_until_stream=defer_until_stream,
        )
        _opencode_trace(
            "opencode.turn.submit.confirmed",
            session_id=session_id,
            run_id=run_id,
            app_id=app_id,
            turn_ref=turn_ref,
            sandbox_id=sandbox_id or None,
            mode="host",
        )
        return turn_ref

    async def stream_turn_events(
        self,
        *,
        session_id: str,
        turn_ref: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        resolved_turn_ref = str(turn_ref or "").strip()
        resolved_session_id = str(session_id or "").strip() or self._sandbox_turn_ref_to_session_id.get(resolved_turn_ref) or resolved_turn_ref
        resolved_sandbox_id = self._sandbox_turn_ref_to_sandbox_id.get(resolved_turn_ref) or str(sandbox_id or "").strip() or None
        if resolved_sandbox_id and self._sandbox_runtime_mode_enabled():
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            try:
                async for event in sandbox_client.stream_turn_events(
                    session_id=resolved_session_id,
                    turn_ref=resolved_turn_ref,
                ):
                    if isinstance(event, dict):
                        yield event
            finally:
                self._sandbox_turn_ref_to_sandbox_id.pop(resolved_turn_ref, None)
                self._sandbox_turn_ref_to_session_id.pop(resolved_turn_ref, None)
            return

        if not self._config.base_url:
            raise OpenCodeServerClientError("OpenCode base URL is not configured.")
        await self._ensure_api_mode()
        async for event in self._stream_official_run_events(session_id=session_id, turn_ref=turn_ref):
            yield event
        return

    async def cancel_turn(
        self,
        *,
        session_id: str,
        turn_ref: str,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> bool:
        resolved_turn_ref = str(turn_ref or "").strip()
        resolved_session_id = str(session_id or "").strip() or self._sandbox_turn_ref_to_session_id.get(resolved_turn_ref) or resolved_turn_ref
        resolved_sandbox_id = self._sandbox_turn_ref_to_sandbox_id.get(resolved_turn_ref) or str(sandbox_id or "").strip() or None
        _opencode_trace(
            "opencode.cancel.requested",
            session_id=resolved_session_id,
            turn_ref=resolved_turn_ref,
            sandbox_id=resolved_sandbox_id,
            mode="sandbox" if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id else "host",
        )
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            try:
                sandbox_client, _ = await self._get_sandbox_official_client(
                    sandbox_id=resolved_sandbox_id,
                    workspace_path=str(workspace_path or "").strip(),
                )
                cancelled = await sandbox_client.cancel_turn(
                    session_id=resolved_session_id,
                    turn_ref=resolved_turn_ref,
                )
            finally:
                self._sandbox_turn_ref_to_sandbox_id.pop(resolved_turn_ref, None)
                self._sandbox_turn_ref_to_session_id.pop(resolved_turn_ref, None)
            _opencode_trace(
                "opencode.cancel.result",
                session_id=str(session_id),
                turn_ref=str(turn_ref),
                cancelled=bool(cancelled),
                mode="sandbox",
            )
            return bool(cancelled)

        # Host/API mode: never bounce back through sandbox controller even if a sandbox_id is present.
        self._sandbox_turn_ref_to_sandbox_id.pop(resolved_turn_ref, None)
        self._sandbox_turn_ref_to_session_id.pop(resolved_turn_ref, None)

        await self._ensure_api_mode()
        response = await self._request("POST", f"/session/{resolved_session_id}/abort", json_payload={}, retries=0)
        if isinstance(response.get("cancelled"), bool):
            cancelled = bool(response.get("cancelled"))
            _opencode_trace(
                "opencode.cancel.result",
                session_id=str(session_id),
                turn_ref=str(turn_ref),
                cancelled=cancelled,
                mode="host",
            )
            return cancelled
        if isinstance(response.get("ok"), bool):
            cancelled = bool(response.get("ok"))
            _opencode_trace(
                "opencode.cancel.result",
                session_id=str(session_id),
                turn_ref=str(turn_ref),
                cancelled=cancelled,
                mode="host",
            )
            return cancelled
        if isinstance(response.get("aborted"), bool):
            cancelled = bool(response.get("aborted"))
            _opencode_trace(
                "opencode.cancel.result",
                session_id=str(session_id),
                turn_ref=str(turn_ref),
                cancelled=cancelled,
                mode="host",
            )
            return cancelled
        _opencode_trace(
            "opencode.cancel.result",
            session_id=str(session_id),
            turn_ref=str(turn_ref),
            cancelled=True,
            mode="host",
        )
        return True

    async def answer_question(
        self,
        *,
        question_id: str,
        answers: list[list[str]],
        session_id: str | None = None,
        turn_ref: str | None = None,
        run_ref: str | None = None,
        sandbox_id: str | None = None,
        workspace_path: str | None = None,
    ) -> bool:
        request_id = str(question_id or "").strip()
        if not request_id:
            raise OpenCodeServerClientError("OpenCode question response requires question_id.")

        normalized_answers: list[list[str]] = []
        for row in answers or []:
            if not isinstance(row, list):
                continue
            values = [str(item).strip() for item in row if str(item).strip()]
            normalized_answers.append(values)
        if not normalized_answers:
            raise OpenCodeServerClientError("OpenCode question response requires at least one answer.")

        resolved_turn_ref = str(turn_ref or run_ref or "").strip()
        resolved_session_id = (
            str(session_id or "").strip()
            or self._sandbox_turn_ref_to_session_id.get(resolved_turn_ref)
            or resolved_turn_ref
        )
        resolved_sandbox_id = self._sandbox_turn_ref_to_sandbox_id.get(resolved_turn_ref) or str(sandbox_id or "").strip() or None
        _opencode_trace(
            "opencode.answer.requested",
            session_id=resolved_session_id or None,
            turn_ref=resolved_turn_ref or None,
            question_id=request_id,
            answer_groups=len(normalized_answers),
            sandbox_id=resolved_sandbox_id,
            mode="sandbox" if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id else "host",
        )
        if self._sandbox_runtime_mode_enabled() and resolved_sandbox_id:
            sandbox_client, _ = await self._get_sandbox_official_client(
                sandbox_id=resolved_sandbox_id,
                workspace_path=str(workspace_path or "").strip(),
            )
            ok = await sandbox_client.answer_question(
                question_id=request_id,
                answers=normalized_answers,
                session_id=resolved_session_id,
                turn_ref=resolved_turn_ref,
            )
            _opencode_trace(
                "opencode.answer.result",
                session_id=resolved_session_id or None,
                turn_ref=resolved_turn_ref or None,
                question_id=request_id,
                ok=bool(ok),
                mode="sandbox",
            )
            return bool(ok)

        # Host/API mode: never bounce back through sandbox controller even if a sandbox_id is present.
        self._sandbox_turn_ref_to_sandbox_id.pop(resolved_turn_ref, None)

        await self._ensure_api_mode()
        payload = {"answers": normalized_answers}
        await self._request(
            "POST",
            f"/question/{request_id}/reply",
            json_payload=payload,
            retries=0,
            expect_json=False,
        )
        _opencode_trace(
            "opencode.answer.result",
            session_id=resolved_session_id or None,
            turn_ref=resolved_turn_ref or None,
            question_id=request_id,
            ok=True,
            mode="host",
        )
        return True

    async def start_run(
        self,
        *,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        messages: list[dict[str, str]],
        selected_agent_contract: dict[str, Any] | None = None,
    ) -> str:
        session_id = await self.create_session(
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            model_id=model_id,
            selected_agent_contract=selected_agent_contract,
        )
        turn_ref = await self.submit_turn(
            session_id=session_id,
            run_id=run_id,
            app_id=app_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            model_id=model_id,
            prompt=prompt,
            recovery_messages=messages,
            selected_agent_contract=selected_agent_contract,
        )
        if self._sandbox_runtime_mode_enabled():
            return turn_ref
        self._official_latest_turn_ref_by_session[session_id] = turn_ref
        return session_id

    async def stream_run_events(
        self,
        *,
        run_ref: str,
        sandbox_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        resolved_run_ref = str(run_ref or "").strip()
        if not resolved_run_ref:
            return
        if self._sandbox_runtime_mode_enabled():
            async for event in self.stream_turn_events(
                session_id=self._sandbox_turn_ref_to_session_id.get(resolved_run_ref) or resolved_run_ref,
                turn_ref=resolved_run_ref,
                sandbox_id=sandbox_id,
            ):
                yield event
            return
        turn_ref = self._official_latest_turn_ref_by_session.get(resolved_run_ref) or resolved_run_ref
        async for event in self.stream_turn_events(
            session_id=resolved_run_ref,
            turn_ref=turn_ref,
            sandbox_id=sandbox_id,
        ):
            yield event

    async def cancel_run(self, *, run_ref: str, sandbox_id: str | None = None) -> bool:
        resolved_run_ref = str(run_ref or "").strip()
        if self._sandbox_runtime_mode_enabled():
            return await self.cancel_turn(
                session_id=self._sandbox_turn_ref_to_session_id.get(resolved_run_ref) or resolved_run_ref,
                turn_ref=resolved_run_ref,
                sandbox_id=sandbox_id,
            )
        return await self.cancel_turn(
            session_id=resolved_run_ref,
            turn_ref=self._official_latest_turn_ref_by_session.get(resolved_run_ref) or resolved_run_ref,
            sandbox_id=sandbox_id,
        )

    async def _submit_turn_official(
        self,
        *,
        session_id: str,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        recovery_messages: list[dict[str, str]],
        defer_until_stream: bool = False,
    ) -> str:
        text_prompt = self._build_prompt(
            run_id=run_id,
            app_id=app_id,
            prompt=prompt,
            messages=recovery_messages,
            workspace_path=workspace_path,
            sandbox_id=sandbox_id,
        )
        message_id = f"msg-{run_id}-{uuid4().hex[:10]}"
        parent_message_id = await self._resolve_official_parent_message_id(session_id=session_id)
        message_payload: dict[str, Any] = {
            "messageID": message_id,
            "parts": [{"type": "text", "text": text_prompt}],
        }
        model = self._to_official_model(model_id)
        if model:
            message_payload["model"] = model
            if self._is_official_model_preflight_enabled():
                await self._official_preflight_model(
                    session_id=session_id,
                    message_id=message_id,
                    model=model,
                )

        initial_response: dict[str, Any] = {}
        message_submission_task: Any | None = None
        message_submission_started = False

        async def _submit_message() -> dict[str, Any]:
            response = await self._request("POST", f"/session/{session_id}/message", json_payload=message_payload, retries=0)
            embedded_error = self._extract_assistant_info_error(response)
            if embedded_error:
                safe_error = self._sanitize_error_message(embedded_error)
                raise OpenCodeServerClientError(f"OpenCode assistant error: {safe_error}")
            return response

        if not defer_until_stream:
            try:
                message_submission_task = asyncio.create_task(_submit_message())
                message_submission_started = True

                immediate_window_ms = float(
                    (os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_MESSAGE_IMMEDIATE_WINDOW_MS") or "50").strip()
                )
                immediate_window_seconds = max(0.0, immediate_window_ms) / 1000.0
                if immediate_window_seconds > 0:
                    try:
                        initial_response = await asyncio.wait_for(
                            asyncio.shield(message_submission_task),
                            timeout=immediate_window_seconds,
                        )
                        message_submission_task = None
                    except asyncio.TimeoutError:
                        pass
                else:
                    initial_response = await asyncio.shield(message_submission_task)
                    message_submission_task = None
            except OpenCodeServerClientError:
                raise

        def _consume_message_submission_result(task: Any) -> None:
            try:
                task.result()
            except Exception:
                # Streaming flow handles assistant/session errors from official APIs.
                pass

        if message_submission_task is not None:
            message_submission_task.add_done_callback(_consume_message_submission_result)

        assistant_message_ids: set[str] = set()
        response_info = initial_response.get("info") if isinstance(initial_response.get("info"), dict) else {}
        if str(response_info.get("role") or "").strip().lower() == "assistant":
            response_message_id = str(response_info.get("id") or "").strip()
            if response_message_id:
                assistant_message_ids.add(response_message_id)
                self._remember_latest_assistant_message_id(
                    session_id=session_id,
                    message_id=response_message_id,
                )
        self._official_latest_turn_ref_by_session[session_id] = message_id
        self._official_run_state[self._official_state_key(session_id=session_id, turn_ref=message_id)] = {
            "parent_message_id": message_id,
            "prior_assistant_message_id": parent_message_id,
            "initial_payload": initial_response,
            "initial_emitted": False,
            "complete_on_initial_text": bool(self._extract_text_from_message_payload(initial_response)),
            "text_offsets": {},
            "tool_status": {},
            "message_roles": {message_id: "user"},
            "part_types": {},
            "question_pending_request_ids": set(),
            "emitted_question_request_ids": set(),
            "completed": False,
            "last_progress_at": time.monotonic(),
            "assistant_message_ids": assistant_message_ids,
            "message_payload": message_payload,
            "message_submission_task": message_submission_task,
            "message_submission_started": message_submission_started,
            "workspace_path": workspace_path,
            "sandbox_id": sandbox_id,
        }
        return message_id

    async def _resolve_official_parent_message_id(self, *, session_id: str) -> str:
        resolved_session_id = str(session_id or "").strip()
        if not resolved_session_id:
            return ""
        if resolved_session_id in self._official_latest_assistant_message_id_by_session:
            return str(self._official_latest_assistant_message_id_by_session.get(resolved_session_id) or "").strip()
        try:
            payload = await self._request(
                "GET",
                f"/session/{resolved_session_id}/message",
                json_payload={},
                retries=0,
                expect_dict=False,
            )
        except Exception:
            return ""
        latest_assistant = self._latest_assistant_candidate(
            self._collect_official_assistant_candidates(payload)
        )
        if latest_assistant is None:
            return ""
        info = latest_assistant.get("info") if isinstance(latest_assistant.get("info"), dict) else {}
        message_id = str(info.get("id") or "").strip()
        if not message_id:
            return ""
        self._remember_latest_assistant_message_id(
            session_id=resolved_session_id,
            message_id=message_id,
        )
        return message_id

    async def _stream_official_run_events(self, *, session_id: str, turn_ref: str) -> AsyncGenerator[dict[str, Any], None]:
        async for event in self._stream_official_run_events_via_global_events(
            session_id=session_id,
            turn_ref=turn_ref,
        ):
            yield event

    async def _stream_official_run_events_via_global_events(self, *, session_id: str, turn_ref: str) -> AsyncGenerator[dict[str, Any], None]:
        state = self._official_state_setdefault(
            session_id=session_id,
            turn_ref=turn_ref,
            default={
                "parent_message_id": turn_ref,
                "prior_assistant_message_id": "",
                "initial_payload": {},
                "initial_emitted": False,
                "complete_on_initial_text": False,
                "text_offsets": {},
                "tool_status": {},
                "message_roles": {},
                "part_types": {},
                "question_pending_request_ids": set(),
                "emitted_question_request_ids": set(),
                "completed": False,
                "last_progress_at": time.monotonic(),
                "assistant_message_ids": set(),
                "message_payload": {},
                "message_submission_started": False,
                "workspace_path": "",
                "sandbox_id": "",
                "saw_tool_event": False,
            },
        )
        assistant_message_ids = state.setdefault("assistant_message_ids", set())
        message_roles = state.setdefault("message_roles", {})
        part_types = state.setdefault("part_types", {})
        pending_question_request_ids = state.setdefault("question_pending_request_ids", set())
        parent_message_id = str(state.get("parent_message_id") or "").strip()
        prior_assistant_message_id = str(state.get("prior_assistant_message_id") or "").strip()
        timeout_seconds = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_STREAM_TIMEOUT_SECONDS") or "300").strip())
        deadline = time.monotonic() + max(30.0, timeout_seconds)
        no_match_grace_seconds = float(
            (os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_GLOBAL_NO_MATCH_GRACE_SECONDS") or "3").strip()
        )
        no_match_grace_seconds = max(0.5, no_match_grace_seconds)
        global_read_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_GLOBAL_READ_TIMEOUT_SECONDS") or "30").strip())
        global_read_timeout = max(2.0, global_read_timeout)
        opened_at = time.monotonic()
        saw_assistant_text = False
        terminal_event: dict[str, Any] | None = None
        global_event_seen = 0
        global_event_matched_session = 0
        assistant_delta_emitted = 0
        delta_skipped_field_filter = 0
        delta_skipped_empty = 0
        event_type_counts: dict[str, int] = {}

        _opencode_trace(
            "opencode.global_stream.opened",
            session_id=session_id,
        )

        async def _start_message_submission_if_needed() -> None:
            if bool(state.get("message_submission_started")):
                return
            message_payload = state.get("message_payload")
            if not isinstance(message_payload, dict) or not message_payload:
                return

            async def _submit_message() -> dict[str, Any]:
                response = await self._request(
                    "POST",
                    f"/session/{session_id}/message",
                    json_payload=message_payload,
                    retries=0,
                )
                embedded_error = self._extract_assistant_info_error(response)
                if embedded_error:
                    safe_error = self._sanitize_error_message(embedded_error)
                    raise OpenCodeServerClientError(f"OpenCode assistant error: {safe_error}")
                return response

            state["message_submission_started"] = True
            state["message_submission_task"] = asyncio.create_task(_submit_message())
            await asyncio.sleep(0)

        def _drain_submission_task_error_if_ready() -> dict[str, Any] | None:
            task = state.get("message_submission_task")
            if task is None or not getattr(task, "done", lambda: False)():
                return None
            state["message_submission_task"] = None
            try:
                task.result()
            except OpenCodeServerClientError as exc:
                return {
                    "event": "run.failed",
                    "payload": {"error": str(exc) or "OpenCode assistant error."},
                    "code": "OPENCODE_ASSISTANT_ERROR",
                }
            except Exception as exc:
                return {
                    "event": "run.failed",
                    "payload": {"error": str(exc) or "OpenCode turn submission failed."},
                    "code": "OPENCODE_SUBMIT_FAILED",
                }
            return None

        async def _evaluate_idle_signal(source_event: str) -> tuple[list[dict[str, Any]], bool]:
            nonlocal terminal_event
            nonlocal saw_assistant_text
            nonlocal assistant_delta_emitted
            emitted_events: list[dict[str, Any]] = []
            if any(str(item or "").strip() for item in pending_question_request_ids):
                return emitted_events, False
            messages_payload = await self._request(
                "GET",
                f"/session/{session_id}/message",
                json_payload={},
                retries=0,
                expect_dict=False,
            )
            candidates = self._filter_assistant_candidates_for_turn(
                candidates=self._collect_official_assistant_candidates(messages_payload),
                parent_message_id=parent_message_id,
                prior_assistant_message_id=prior_assistant_message_id,
            )
            last_info_error = ""
            for message in candidates:
                info = message.get("info") if isinstance(message.get("info"), dict) else {}
                message_id = str(info.get("id") or "").strip()
                role = str(info.get("role") or "").strip().lower()
                if message_id and role:
                    message_roles[message_id] = role
                if message_id:
                    assistant_message_ids.add(message_id)
                    self._remember_latest_assistant_message_id(
                        session_id=session_id,
                        message_id=message_id,
                    )
                for event in self._extract_incremental_tool_events(message=message, state=state):
                    state["saw_tool_event"] = True
                    state["last_progress_at"] = time.monotonic()
                    emitted_events.append(event)
                for delta in self._extract_incremental_text_deltas(message=message, state=state):
                    saw_assistant_text = True
                    state["last_progress_at"] = time.monotonic()
                    assistant_delta_emitted += 1
                    emitted_events.append({"event": "assistant.delta", "payload": {"content": delta}})
                embedded_error = self._extract_assistant_info_error(message)
                if embedded_error:
                    last_info_error = self._sanitize_error_message(embedded_error)
            if last_info_error:
                terminal_event = {
                    "event": "run.failed",
                    "payload": {"error": f"OpenCode assistant error: {last_info_error}"},
                    "code": "OPENCODE_ASSISTANT_ERROR",
                }
                return emitted_events, True
            if self._is_session_completion_ready(
                state=state,
                pending_question_request_ids=pending_question_request_ids,
                candidates=candidates,
            ):
                terminal_event = {"event": "run.completed", "payload": {"status": "completed"}}
                return emitted_events, True
            _opencode_trace(
                "opencode.idle_nonterminal",
                session_id=session_id,
                source_event=source_event,
                candidate_count=len(candidates),
                pending_question_count=len([item for item in pending_question_request_ids if str(item or "").strip()]),
            )
            return emitted_events, False

        initial_payload = state.get("initial_payload")
        if isinstance(initial_payload, dict):
            info = initial_payload.get("info")
            if not isinstance(info, dict):
                data_payload = initial_payload.get("data")
                if isinstance(data_payload, dict):
                    info = data_payload.get("info") if isinstance(data_payload.get("info"), dict) else None
            if isinstance(info, dict) and str(info.get("role") or "").strip().lower() == "assistant":
                message_id = str(info.get("id") or "").strip()
                if message_id:
                    assistant_message_ids.add(message_id)
                    message_roles[message_id] = "assistant"

        initial_payload = state.get("initial_payload")
        if isinstance(initial_payload, dict) and initial_payload and not bool(state.get("initial_emitted")):
            state["initial_emitted"] = True
            initial_candidates = self._collect_official_assistant_candidates(initial_payload)
            if not initial_candidates:
                if isinstance(initial_payload.get("parts"), list):
                    initial_candidates = [initial_payload]
                else:
                    data_payload = initial_payload.get("data")
                    if isinstance(data_payload, dict) and isinstance(data_payload.get("parts"), list):
                        initial_candidates = [data_payload]
            if parent_message_id:
                filtered_initial_candidates = [
                    item
                    for item in initial_candidates
                    if self._extract_candidate_parent_id(item) in {"", parent_message_id}
                ]
                if filtered_initial_candidates:
                    initial_candidates = filtered_initial_candidates
            initial_candidates = self._sort_assistant_candidates(initial_candidates)
            emitted_initial_text = False
            for message in initial_candidates:
                message_info = message.get("info") if isinstance(message.get("info"), dict) else {}
                message_id = str(message_info.get("id") or "").strip()
                role = str(message_info.get("role") or "").strip().lower()
                if message_id and role:
                    message_roles[message_id] = role
                if message_id and role == "assistant":
                    assistant_message_ids.add(message_id)
                    self._remember_latest_assistant_message_id(
                        session_id=session_id,
                        message_id=message_id,
                    )
                for event in self._extract_incremental_tool_events(message=message, state=state):
                    state["saw_tool_event"] = True
                    state["last_progress_at"] = time.monotonic()
                    yield event
                for delta in self._extract_incremental_text_deltas(message=message, state=state):
                    emitted_initial_text = True
                    saw_assistant_text = True
                    state["last_progress_at"] = time.monotonic()
                    assistant_delta_emitted += 1
                    yield {"event": "assistant.delta", "payload": {"content": delta}}
            if (
                not initial_candidates
                and not emitted_initial_text
                and not any(str(item or "").strip() for item in pending_question_request_ids)
            ):
                details = self._compact_json_preview(initial_payload)
                yield {
                    "event": "run.failed",
                    "payload": {"error": f"OpenCode response did not include assistant text. response={details}"},
                    "code": "OPENCODE_EMPTY_RESPONSE",
                }
                self._official_state_pop(session_id=session_id, turn_ref=turn_ref)
                return
            if (
                emitted_initial_text
                and bool(state.get("complete_on_initial_text"))
                and state.get("message_submission_task") is None
                and not any(str(item or "").strip() for item in pending_question_request_ids)
            ):
                yield {"event": "run.completed", "payload": {"status": "completed"}}
                self._official_state_pop(session_id=session_id, turn_ref=turn_ref)
                return

        if not self._config.base_url:
            return
        url = f"{self._config.base_url.rstrip('/')}/global/event"
        stream_timeout = httpx.Timeout(
            connect=self._config.connect_timeout_seconds,
            read=global_read_timeout,
            write=self._config.request_timeout_seconds,
            pool=self._config.request_timeout_seconds,
        )
        async with httpx.AsyncClient(timeout=stream_timeout) as client:
            async with client.stream("GET", url, headers=self._headers()) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace").strip()
                    raise OpenCodeServerClientError(
                        f"OpenCode global event stream failed ({response.status_code}): {body or response.reason_phrase}"
                    )
                await _start_message_submission_if_needed()
                async for line in response.aiter_lines():
                    if time.monotonic() >= deadline:
                        break
                    pending_submission_error = _drain_submission_task_error_if_ready()
                    if pending_submission_error is not None:
                        terminal_event = pending_submission_error
                        break
                    raw = (line or "").strip()
                    if not raw or raw.startswith(":"):
                        continue
                    if raw.startswith("data:"):
                        raw = raw[5:].strip()
                    if not raw:
                        continue
                    try:
                        event_wrapper = json.loads(raw)
                    except Exception:
                        continue
                    payload = self._extract_global_event_payload(event_wrapper)
                    if not isinstance(payload, dict):
                        continue
                    global_event_seen += 1
                    event_type = str(payload.get("type") or "").strip()
                    properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
                    if not event_type or not properties:
                        if global_event_matched_session <= 0 and global_event_seen > 0:
                            if event_type.startswith("server.") and global_event_seen >= 2:
                                break
                            if (time.monotonic() - opened_at) >= no_match_grace_seconds:
                                break
                        continue
                    event_session_id = self._extract_session_id_from_global_event_properties(properties)
                    if event_session_id != session_id:
                        if global_event_matched_session <= 0 and global_event_seen > 0:
                            if (time.monotonic() - opened_at) >= no_match_grace_seconds:
                                break
                        continue
                    global_event_matched_session += 1
                    event_type_counts[event_type] = int(event_type_counts.get(event_type) or 0) + 1

                    if event_type == "question.asked":
                        mapped_question = self._map_question_asked_properties(properties)
                        if mapped_question is None:
                            continue
                        request_id = str(mapped_question.get("request_id") or "").strip()
                        if request_id:
                            pending_question_request_ids.add(request_id)
                        state["last_progress_at"] = time.monotonic()
                        yield {"event": "tool.question", "payload": mapped_question}
                        continue

                    if event_type == "permission.asked":
                        mapped_permission = self._map_permission_asked_properties(properties)
                        if mapped_permission is None:
                            continue
                        request_id = str(mapped_permission.get("request_id") or "").strip()
                        if request_id:
                            pending_question_request_ids.add(request_id)
                        if request_id and self._should_auto_approve_permission_request(state=state):
                            approved = await self._approve_permission_request(
                                session_id=session_id,
                                request_id=request_id,
                            )
                            _opencode_trace(
                                "permission.auto_approved",
                                session_id=session_id,
                                request_id=request_id,
                                approved=approved,
                                workspace_path=str(state.get("workspace_path") or ""),
                                sandbox_id=str(state.get("sandbox_id") or ""),
                            )
                            state["last_progress_at"] = time.monotonic()
                            if approved:
                                pending_question_request_ids.discard(request_id)
                                yield {
                                    "event": "tool.question.answered",
                                    "payload": {"request_id": request_id, "answers": [["Allow"]]},
                                }
                                continue
                        state["last_progress_at"] = time.monotonic()
                        yield {"event": "tool.question", "payload": mapped_permission}
                        continue

                    if event_type in {"question.replied", "question.rejected"}:
                        mapped_reply = self._map_question_reply_properties(properties)
                        request_id = str(mapped_reply.get("request_id") or "").strip()
                        if request_id:
                            pending_question_request_ids.discard(request_id)
                        state["last_progress_at"] = time.monotonic()
                        mapped_event = "tool.question.answered" if event_type == "question.replied" else "tool.question.rejected"
                        yield {"event": mapped_event, "payload": mapped_reply}
                        continue

                    if event_type in {"permission.replied", "permission.rejected"}:
                        mapped_reply = self._map_question_reply_properties(properties)
                        request_id = str(mapped_reply.get("request_id") or "").strip()
                        if request_id:
                            pending_question_request_ids.discard(request_id)
                        state["last_progress_at"] = time.monotonic()
                        mapped_event = (
                            "tool.question.answered"
                            if event_type == "permission.replied"
                            else "tool.question.rejected"
                        )
                        yield {"event": mapped_event, "payload": mapped_reply}
                        continue

                    if event_type == "message.updated":
                        info = properties.get("info") if isinstance(properties.get("info"), dict) else {}
                        role = str(info.get("role") or "").strip().lower()
                        message_id = str(info.get("id") or "").strip()
                        if message_id and role:
                            message_roles[message_id] = role
                        if role == "assistant":
                            if message_id:
                                assistant_message_ids.add(message_id)
                                self._remember_latest_assistant_message_id(
                                    session_id=session_id,
                                    message_id=message_id,
                                )
                        embedded_error = self._extract_response_error_message(info)
                        if embedded_error:
                            safe_error = self._sanitize_error_message(embedded_error)
                            terminal_event = {
                                "event": "run.failed",
                                "payload": {"error": f"OpenCode assistant error: {safe_error}"},
                                "code": "OPENCODE_ASSISTANT_ERROR",
                            }
                            break
                        candidates = self._collect_official_assistant_candidates(properties)
                        if not candidates and role == "assistant":
                            candidates = [properties]
                        candidates = self._filter_assistant_candidates_for_turn(
                            candidates=candidates,
                            parent_message_id=parent_message_id,
                            prior_assistant_message_id=prior_assistant_message_id,
                            event_message_id=message_id,
                        )
                        for message in candidates:
                            message_info = message.get("info") if isinstance(message.get("info"), dict) else {}
                            candidate_role = str(message_info.get("role") or role or "").strip().lower()
                            candidate_message_id = str(message_info.get("id") or message_id or "").strip()
                            if candidate_message_id and candidate_role:
                                message_roles[candidate_message_id] = candidate_role
                            if candidate_message_id and candidate_role == "assistant":
                                assistant_message_ids.add(candidate_message_id)
                                self._remember_latest_assistant_message_id(
                                    session_id=session_id,
                                    message_id=candidate_message_id,
                                )
                            if candidate_role == "user":
                                continue
                            if candidate_message_id and parent_message_id and candidate_message_id == parent_message_id:
                                continue
                            emitted_part_delta = False
                            for event in self._extract_incremental_tool_events(message=message, state=state):
                                state["saw_tool_event"] = True
                                state["last_progress_at"] = time.monotonic()
                                yield event
                            for delta in self._extract_incremental_text_deltas(message=message, state=state):
                                emitted_part_delta = True
                                saw_assistant_text = True
                                state["last_progress_at"] = time.monotonic()
                                assistant_delta_emitted += 1
                                yield {"event": "assistant.delta", "payload": {"content": delta}}
                            if emitted_part_delta:
                                continue
                            fallback_text = self._extract_text_from_message_payload(message)
                            if not fallback_text:
                                continue
                            fallback_offsets = state.setdefault("message_text_offsets", {})
                            fallback_key = candidate_message_id
                            if not fallback_key:
                                fallback_hash = sha256(
                                    json.dumps(message, sort_keys=True, default=str).encode("utf-8")
                                ).hexdigest()[:16]
                                fallback_key = f"message.updated:{fallback_hash}"
                            previous = int(fallback_offsets.get(fallback_key) or 0)
                            if len(fallback_text) <= previous:
                                continue
                            delta = fallback_text[previous:]
                            fallback_offsets[fallback_key] = len(fallback_text)
                            saw_assistant_text = True
                            state["last_progress_at"] = time.monotonic()
                            assistant_delta_emitted += 1
                            yield {"event": "assistant.delta", "payload": {"content": delta}}
                        continue

                    if event_type in {"message.part.delta", "message_part.delta", "message.part_delta", "message.delta"} or (
                        "delta" in event_type and ("message" in event_type or "assistant" in event_type)
                    ):
                        message_id = str(
                            properties.get("messageID")
                            or properties.get("messageId")
                            or properties.get("message_id")
                            or ""
                        ).strip()
                        if message_id and parent_message_id and message_id == parent_message_id:
                            continue
                        role = str(message_roles.get(message_id) or "").strip().lower()
                        if role == "user":
                            continue
                        field_name = str(properties.get("field") or "").strip().lower()
                        if field_name:
                            allowed_field_tokens = (
                                "text",
                                "content",
                                "value",
                                "output_text",
                                "markdown",
                                "final",
                                "delta",
                            )
                            if not any(token in field_name for token in allowed_field_tokens):
                                delta_skipped_field_filter += 1
                                continue
                        part_id = str(
                            properties.get("partID")
                            or properties.get("partId")
                            or properties.get("part_id")
                            or ""
                        ).strip()
                        part_type = str(part_types.get(part_id) or "").strip().lower()
                        if self._should_skip_incremental_text_part_type(part_type):
                            continue
                        delta = str(
                            properties.get("delta")
                            or properties.get("textDelta")
                            or properties.get("text_delta")
                            or properties.get("text")
                            or properties.get("value")
                            or properties.get("content")
                            or ""
                        )
                        if not delta:
                            delta_skipped_empty += 1
                            continue
                        offsets = state.setdefault("text_offsets", {})
                        offset_key = part_id or f"{message_id}:delta"
                        previous_offset = int(offsets.get(offset_key) or 0)
                        offsets[offset_key] = previous_offset + len(delta)
                        saw_assistant_text = True
                        state["last_progress_at"] = time.monotonic()
                        assistant_delta_emitted += 1
                        yield {"event": "assistant.delta", "payload": {"content": delta}}
                        continue

                    if event_type in {
                        "message.part.updated",
                        "message_part.updated",
                        "message.part_update",
                        "message.part.created",
                        "message.part.appended",
                    }:
                        part = properties.get("part") if isinstance(properties.get("part"), dict) else {}
                        if not part:
                            continue
                        message_id = str(
                            part.get("messageID")
                            or part.get("messageId")
                            or part.get("message_id")
                            or ""
                        ).strip()
                        if message_id and parent_message_id and message_id == parent_message_id:
                            continue
                        role = str(message_roles.get(message_id) or "").strip().lower()
                        if role == "user":
                            continue
                        part_id = str(part.get("id") or "").strip()
                        part_type = str(part.get("type") or "").strip().lower()
                        if part_id:
                            if part_type:
                                part_types[part_id] = part_type
                        for event in self._extract_incremental_tool_events(message={"parts": [part]}, state=state):
                            state["saw_tool_event"] = True
                            state["last_progress_at"] = time.monotonic()
                            yield event
                        for delta in self._extract_incremental_text_deltas(message={"parts": [part]}, state=state):
                            saw_assistant_text = True
                            state["last_progress_at"] = time.monotonic()
                            yield {"event": "assistant.delta", "payload": {"content": delta}}
                        continue

                    if event_type in {"run.completed", "session.completed", "session.finished"}:
                        if any(str(item or "").strip() for item in pending_question_request_ids):
                            continue
                        terminal_event = {"event": "run.completed", "payload": {"status": "completed"}}
                        break

                    if event_type in {"run.cancelled", "session.cancelled"}:
                        terminal_event = {"event": "run.cancelled", "payload": {"status": "cancelled"}}
                        break

                    if event_type in {"run.paused", "session.paused"}:
                        terminal_event = {"event": "run.paused", "payload": {"status": "paused"}}
                        break

                    if event_type in {"run.failed", "session.failed"}:
                        failure_message = str(
                            properties.get("error")
                            or properties.get("message")
                            or properties.get("reason")
                            or "OpenCode run failed."
                        ).strip()
                        terminal_event = {
                            "event": "run.failed",
                            "payload": {"error": failure_message or "OpenCode run failed."},
                            "code": "OPENCODE_RUN_FAILED_EVENT",
                        }
                        break

                    if event_type == "session.error":
                        details = self._compact_json_preview(properties)
                        terminal_event = {
                            "event": "run.failed",
                            "payload": {"error": f"OpenCode session failed. response={details}"},
                            "code": "OPENCODE_SESSION_ERROR",
                        }
                        break

                    if event_type == "session.status":
                        status_type = self._extract_session_status_type(properties)
                        if status_type == "idle":
                            emitted_events, completed = await _evaluate_idle_signal("session.status")
                            for emitted in emitted_events:
                                yield emitted
                            if completed:
                                break
                        continue

                    if event_type == "session.idle":
                        emitted_events, completed = await _evaluate_idle_signal("session.idle")
                        for emitted in emitted_events:
                            yield emitted
                        if completed:
                            break
                        continue

                pending_submission_error = _drain_submission_task_error_if_ready()
                if pending_submission_error is not None and terminal_event is None:
                    terminal_event = pending_submission_error

        if terminal_event is not None:
            top_event_types = sorted(event_type_counts.items(), key=lambda item: item[1], reverse=True)[:12]
            _opencode_trace(
                "opencode.global_stream.closed",
                session_id=session_id,
                global_event_seen=global_event_seen,
                global_event_matched_session=global_event_matched_session,
                assistant_delta_emitted=assistant_delta_emitted,
                delta_skipped_field_filter=delta_skipped_field_filter,
                delta_skipped_empty=delta_skipped_empty,
                event_type_counts=top_event_types,
                terminal_event=str(terminal_event.get("event") or ""),
            )
            yield terminal_event
            self._official_state_pop(session_id=session_id, turn_ref=turn_ref)
            return

        # No terminal event observed; caller resolves terminal state from the persisted run/session state.
        top_event_types = sorted(event_type_counts.items(), key=lambda item: item[1], reverse=True)[:12]
        _opencode_trace(
            "opencode.global_stream.closed_no_terminal",
            session_id=session_id,
            global_event_seen=global_event_seen,
            global_event_matched_session=global_event_matched_session,
            assistant_delta_emitted=assistant_delta_emitted,
            delta_skipped_field_filter=delta_skipped_field_filter,
            delta_skipped_empty=delta_skipped_empty,
            event_type_counts=top_event_types,
        )

    @staticmethod
    def _extract_global_event_payload(raw_payload: Any) -> dict[str, Any] | None:
        if not isinstance(raw_payload, dict):
            return None
        payload = raw_payload.get("payload")
        if isinstance(payload, dict) and payload.get("type"):
            return payload
        if raw_payload.get("type"):
            return raw_payload
        return None

    @staticmethod
    def _extract_session_status_type(properties: dict[str, Any]) -> str:
        status = properties.get("status")
        if isinstance(status, dict):
            return str(status.get("type") or status.get("status") or "").strip().lower()
        if isinstance(status, str):
            return str(status).strip().lower()
        return str(properties.get("type") or properties.get("state") or "").strip().lower()

    @staticmethod
    def _assistant_finish_value(message: dict[str, Any]) -> str:
        info = message.get("info") if isinstance(message.get("info"), dict) else {}
        return str(info.get("finish") or "").strip().lower()

    @staticmethod
    def _assistant_message_completed_at(message: dict[str, Any]) -> int:
        info = message.get("info") if isinstance(message.get("info"), dict) else {}
        time_data = info.get("time") if isinstance(info.get("time"), dict) else {}
        try:
            return int(time_data.get("completed") or 0)
        except Exception:
            return 0

    @classmethod
    def _assistant_message_is_final(cls, message: dict[str, Any]) -> bool:
        finish = cls._assistant_finish_value(message)
        if finish:
            return finish not in {"tool-calls", "unknown"}
        return cls._assistant_message_completed_at(message) > 0

    @classmethod
    def _latest_assistant_candidate(cls, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        ordered = cls._sort_assistant_candidates(candidates)
        return cls._select_best_assistant_candidate(ordered)

    @classmethod
    def _filter_assistant_candidates_for_turn(
        cls,
        *,
        candidates: list[dict[str, Any]],
        parent_message_id: str,
        prior_assistant_message_id: str,
        event_message_id: str = "",
    ) -> list[dict[str, Any]]:
        ordered = cls._sort_assistant_candidates(candidates)
        if not ordered:
            return []
        event_message_id = str(event_message_id or "").strip()
        if event_message_id:
            event_scoped = [
                item for item in ordered if cls._extract_candidate_message_id(item) == event_message_id
            ]
            if event_scoped:
                ordered = event_scoped
        parent_message_id = str(parent_message_id or "").strip()
        if parent_message_id:
            explicit_parent_matches = [
                item for item in ordered if cls._extract_candidate_parent_id(item) == parent_message_id
            ]
            if explicit_parent_matches:
                return explicit_parent_matches
        prior_assistant_message_id = str(prior_assistant_message_id or "").strip()
        if prior_assistant_message_id:
            newer_candidates = cls._assistant_candidates_after_anchor(
                ordered,
                anchor_message_id=prior_assistant_message_id,
            )
            if newer_candidates:
                return newer_candidates
            if event_message_id:
                return [
                    item
                    for item in ordered
                    if cls._extract_candidate_message_id(item) != prior_assistant_message_id
                ]
            return []
        return ordered

    @classmethod
    def _assistant_candidates_after_anchor(
        cls,
        candidates: list[dict[str, Any]],
        *,
        anchor_message_id: str,
    ) -> list[dict[str, Any]]:
        anchor = str(anchor_message_id or "").strip()
        if not anchor:
            return list(candidates)
        last_anchor_index = -1
        for index, item in enumerate(candidates):
            if cls._extract_candidate_message_id(item) == anchor:
                last_anchor_index = index
        if last_anchor_index < 0:
            return []
        return list(candidates[last_anchor_index + 1 :])

    @staticmethod
    def _has_running_tool_states(*, state: dict[str, Any]) -> bool:
        running_statuses = {"running", "pending", "in_progress", "started"}
        tool_status = state.get("tool_status") if isinstance(state.get("tool_status"), dict) else {}
        return any(str(value or "").strip().lower() in running_statuses for value in tool_status.values())

    @classmethod
    def _is_session_completion_ready(
        cls,
        *,
        state: dict[str, Any],
        pending_question_request_ids: set[Any],
        candidates: list[dict[str, Any]],
        allow_text_fallback: bool = False,
    ) -> bool:
        if any(str(item or "").strip() for item in pending_question_request_ids):
            return False
        if cls._has_running_tool_states(state=state):
            return False
        latest_assistant = cls._latest_assistant_candidate(candidates)
        if latest_assistant is None:
            return False
        if cls._assistant_message_is_final(latest_assistant):
            return True
        if allow_text_fallback:
            return bool(cls._extract_text_from_message_payload(latest_assistant))
        return False

    @staticmethod
    def _extract_session_id_from_global_event_properties(properties: dict[str, Any]) -> str:
        direct = str(properties.get("sessionID") or properties.get("sessionId") or "").strip()
        if direct:
            return direct
        info = properties.get("info")
        if isinstance(info, dict):
            nested = str(info.get("sessionID") or info.get("sessionId") or info.get("id") or "").strip()
            if nested.startswith("ses_"):
                return nested
        part = properties.get("part")
        if isinstance(part, dict):
            nested = str(part.get("sessionID") or part.get("sessionId") or "").strip()
            if nested:
                return nested

        stack: list[Any] = list(properties.values())
        seen: set[int] = set()
        while stack:
            current = stack.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)
            if isinstance(current, list):
                stack.extend(current)
                continue
            if not isinstance(current, dict):
                continue
            nested = str(
                current.get("sessionID")
                or current.get("sessionId")
                or current.get("session_id")
                or ""
            ).strip()
            if nested:
                return nested
            nested_info = current.get("info")
            if isinstance(nested_info, dict):
                nested = str(
                    nested_info.get("sessionID")
                    or nested_info.get("sessionId")
                    or nested_info.get("session_id")
                    or nested_info.get("id")
                    or ""
                ).strip()
                if nested.startswith("ses_"):
                    return nested
            stack.extend(current.values())
        return ""

    @staticmethod
    def _map_question_asked_properties(properties: dict[str, Any]) -> dict[str, Any] | None:
        request_id = str(
            properties.get("id")
            or properties.get("requestID")
            or properties.get("requestId")
            or properties.get("request_id")
            or ""
        ).strip()
        questions_payload = properties.get("questions") if isinstance(properties.get("questions"), list) else []
        questions: list[dict[str, Any]] = []
        for item in questions_payload:
            if not isinstance(item, dict):
                continue
            normalized: dict[str, Any] = {
                "header": str(item.get("header") or "").strip(),
                "question": str(item.get("question") or "").strip(),
                "multiple": bool(item.get("multiple")) if item.get("multiple") is not None else False,
                "options": [],
            }
            options_payload = item.get("options") if isinstance(item.get("options"), list) else []
            for option in options_payload:
                if not isinstance(option, dict):
                    continue
                label = str(option.get("label") or "").strip()
                if not label:
                    continue
                normalized["options"].append(
                    {
                        "label": label,
                        "description": str(option.get("description") or "").strip(),
                    }
                )
            questions.append(normalized)
        if not request_id and not questions:
            return None
        tool_payload = properties.get("tool") if isinstance(properties.get("tool"), dict) else {}
        payload: dict[str, Any] = {
            "request_id": request_id,
            "questions": questions,
            "request_kind": "question",
        }
        if tool_payload:
            payload["tool"] = {
                "call_id": str(tool_payload.get("callID") or tool_payload.get("callId") or "").strip() or None,
                "message_id": str(tool_payload.get("messageID") or tool_payload.get("messageId") or "").strip() or None,
            }
        return payload

    @staticmethod
    def _map_permission_asked_properties(properties: dict[str, Any]) -> dict[str, Any] | None:
        type_hint = str(properties.get("type") or "").strip().lower()
        has_permission_marker = any(
            key in properties for key in ("permission", "pattern", "target", "path", "status", "action")
        )
        if not has_permission_marker and "permission" not in type_hint:
            return None
        request_id = str(
            properties.get("id")
            or properties.get("requestID")
            or properties.get("requestId")
            or properties.get("request_id")
            or ""
        ).strip()
        permission_name = str(
            properties.get("permission")
            or properties.get("kind")
            or properties.get("name")
            or "permission"
        ).strip()
        pattern = str(
            properties.get("pattern")
            or properties.get("path")
            or properties.get("target")
            or ""
        ).strip()
        prompt = str(
            properties.get("question")
            or properties.get("prompt")
            or properties.get("message")
            or ""
        ).strip()
        if not prompt:
            detail = f" ({pattern})" if pattern else ""
            prompt = f"Allow `{permission_name or 'permission'}` request{detail}?"
        if not request_id:
            return None
        return {
            "request_id": request_id,
            "questions": [
                {
                    "header": "Permission",
                    "question": prompt,
                    "multiple": False,
                    "options": [
                        {"label": "Allow", "description": "Allow this request for the current run."},
                        {"label": "Deny", "description": "Reject this request and continue safely."},
                    ],
                }
            ],
            "request_kind": "permission",
            "tool": {
                "call_id": str(properties.get("callID") or properties.get("callId") or "").strip() or None,
                "message_id": str(properties.get("messageID") or properties.get("messageId") or "").strip() or None,
            },
            "permission": permission_name or None,
            "pattern": pattern or None,
        }

    @staticmethod
    def _map_question_reply_properties(properties: dict[str, Any]) -> dict[str, Any]:
        request_id = str(
            properties.get("requestID")
            or properties.get("requestId")
            or properties.get("request_id")
            or properties.get("id")
            or ""
        ).strip()
        answers_payload = properties.get("answers") if isinstance(properties.get("answers"), list) else []
        normalized_answers: list[list[str]] = []
        for row in answers_payload:
            if not isinstance(row, list):
                continue
            normalized_row = [str(item).strip() for item in row if str(item).strip()]
            normalized_answers.append(normalized_row)
        return {
            "request_id": request_id,
            "request_kind": str(properties.get("type") or "").strip().lower() or None,
            "answers": normalized_answers,
        }

    @staticmethod
    def _is_permission_auto_approve_enabled() -> bool:
        raw = (os.getenv("APPS_CODING_AGENT_OPENCODE_AUTO_APPROVE_PERMISSION_ASK") or "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_stage_workspace_path(workspace_path: str) -> bool:
        normalized = str(workspace_path or "").strip().replace("\\", "/")
        if not normalized:
            return False
        return "/.talmudpedia/stage/" in normalized or normalized.endswith("/.talmudpedia/stage/shared/workspace")

    def _should_auto_approve_permission_request(self, *, state: dict[str, Any]) -> bool:
        if not self._is_permission_auto_approve_enabled():
            return False
        workspace_path = str(state.get("workspace_path") or "").strip()
        return self._is_stage_workspace_path(workspace_path)

    async def _approve_permission_request(self, *, session_id: str, request_id: str) -> bool:
        if not request_id:
            return False
        try:
            response = await self._request(
                "POST",
                f"/session/{session_id}/permissions/{request_id}",
                json_payload={"status": "approved", "answers": [["Allow"]]},
                retries=0,
                expect_dict=False,
            )
            if isinstance(response, dict):
                ok = response.get("ok")
                if isinstance(ok, bool):
                    return ok
        except OpenCodeServerClientError:
            return False
        return True

    async def _list_pending_questions_for_session(self, *, session_id: str) -> list[dict[str, Any]]:
        try:
            payload = await self._request(
                "GET",
                "/question",
                json_payload={},
                retries=0,
                expect_dict=False,
            )
        except OpenCodeServerClientError:
            return []
        if not isinstance(payload, list):
            return []
        pending: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            event_session_id = str(item.get("sessionID") or item.get("sessionId") or "").strip()
            if event_session_id != str(session_id):
                continue
            pending.append(item)
        return pending

    async def _official_preflight_model(
        self,
        *,
        session_id: str,
        message_id: str,
        model: dict[str, str],
    ) -> None:
        if not self._config.base_url:
            return
        url = f"{self._config.base_url.rstrip('/')}/session/{session_id}/init"
        payload = {
            "providerID": model.get("providerID"),
            "modelID": model.get("modelID"),
            "messageID": message_id,
        }
        timeout = httpx.Timeout(timeout=2.0, connect=1.5)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
        except Exception:
            return
        if response.status_code < 400:
            return
        raw = response.text.strip()
        if not raw:
            raise OpenCodeServerClientError(
                f"OpenCode model preflight failed for {model.get('providerID')}/{model.get('modelID')} "
                f"with status {response.status_code}."
            )
        try:
            parsed = response.json()
        except Exception:
            parsed = {"message": raw}
        if isinstance(parsed, dict):
            name = str(parsed.get("name") or "").strip()
            data = parsed.get("data")
            if name == "ProviderModelNotFoundError" and isinstance(data, dict):
                provider_id = str(data.get("providerID") or model.get("providerID") or "").strip()
                model_id = str(data.get("modelID") or model.get("modelID") or "").strip()
                suggestions = data.get("suggestions")
                suffix = ""
                if isinstance(suggestions, list):
                    compact = [str(item).strip() for item in suggestions if str(item).strip()]
                    if compact:
                        suffix = f" Suggestions: {', '.join(compact)}."
                raise OpenCodeServerClientError(
                    f"OpenCode model is unavailable: {provider_id}/{model_id}.{suffix}"
                )
            message = self._extract_error_value(parsed, parent_key="error")
            if message:
                raise OpenCodeServerClientError(f"OpenCode model preflight failed: {message}")
        raise OpenCodeServerClientError(f"OpenCode model preflight failed ({response.status_code}): {raw[:260]}")

    @staticmethod
    def _is_official_model_preflight_enabled() -> bool:
        raw = (os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_MODEL_PREFLIGHT_ENABLED") or "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _build_official_session_permission_rules(workspace_path: str) -> list[dict[str, str]]:
        workspace = str(workspace_path or "").strip()
        if not workspace:
            return [{"permission": "question", "pattern": "*", "action": "allow"}]
        normalized = os.path.abspath(workspace)
        real = os.path.realpath(normalized)
        patterns: list[str] = []
        for candidate in (workspace, normalized, real):
            value = str(candidate or "").strip()
            if not value:
                continue
            if value not in patterns:
                patterns.append(value)
            wildcard = value.rstrip("/") + "/*"
            if wildcard not in patterns:
                patterns.append(wildcard)
        rules = [{"permission": "external_directory", "pattern": pattern, "action": "allow"} for pattern in patterns]
        rules.append({"permission": "question", "pattern": "*", "action": "allow"})
        return rules

    @staticmethod
    def _validate_official_workspace_path(workspace_path: str) -> None:
        workspace = str(workspace_path or "").strip()
        if not workspace:
            return
        if not os.path.isabs(workspace):
            raise OpenCodeServerClientError(
                f"OpenCode host-mode workspace_path must be absolute: {workspace}"
            )

    async def _poll_official_assistant_message(
        self,
        *,
        session_id: str,
        parent_message_id: str,
    ) -> str:
        if not self._config.base_url:
            return ""
        timeout_seconds = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_POLL_TIMEOUT_SECONDS") or "90").strip())
        if timeout_seconds <= 0:
            return ""
        deadline = time.monotonic() + timeout_seconds
        path = f"/session/{session_id}/message"
        while time.monotonic() < deadline:
            payload = await self._request("GET", path, json_payload={}, retries=0, expect_dict=False)
            embedded_error = self._extract_assistant_info_error(payload)
            if embedded_error:
                safe_error = self._sanitize_error_message(embedded_error)
                raise OpenCodeServerClientError(f"OpenCode assistant error: {safe_error}")
            assistant_message = self._extract_official_assistant_message(payload, parent_message_id=parent_message_id)
            if assistant_message:
                embedded_error = self._extract_assistant_info_error(assistant_message)
                if embedded_error:
                    safe_error = self._sanitize_error_message(embedded_error)
                    raise OpenCodeServerClientError(f"OpenCode assistant error: {safe_error}")
                text = self._extract_text_from_message_payload(assistant_message)
                if text:
                    return text
            await self._sleep(0.35)
        return ""

    async def _ensure_api_mode(self) -> str:
        if self._api_mode:
            return self._api_mode
        try:
            await self._request("GET", "/global/health", json_payload={}, retries=1, expect_json=True)
            self._api_mode = "official"
            return self._api_mode
        except Exception as exc:
            raise OpenCodeServerClientError(
                f"OpenCode official API health check failed: {exc}"
            ) from exc

    @staticmethod
    def _to_official_model(resolved_model_id: str) -> dict[str, str] | None:
        raw = str(resolved_model_id or "").strip()
        if not raw:
            return None
        if "/" not in raw:
            return None
        provider_id, model_id = raw.split("/", 1)
        provider_id = provider_id.strip()
        model_id = model_id.strip()
        if not provider_id or not model_id:
            return None
        return {
            "providerID": provider_id,
            "modelID": model_id,
        }

    @staticmethod
    def _build_prompt(
        *,
        run_id: str,
        app_id: str,
        prompt: str,
        messages: list[dict[str, str]],
        workspace_path: str,
        sandbox_id: str,
    ) -> str:
        text = str(prompt or "").strip()
        if not text:
            for item in reversed(messages):
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip().lower()
                if role == "user":
                    text = str(item.get("content") or "").strip()
                    if text:
                        break
        if not text:
            text = "Continue."
        return (
            f"{text}\n\n"
            f"[Execution context]\n"
            f"- run_id: {run_id or 'unknown'}\n"
            f"- app_id: {app_id or 'unknown'}\n"
            f"- sandbox_id: {sandbox_id or 'unknown'}\n"
            f"- workspace_path: {workspace_path or 'unknown'}\n"
            f"- editing_rules: use coding-agent tools only for file changes; never claim success if a tool reports error/non-zero exit code.\n"
            f"- contract_tool: use `read_agent_context` for selected app-agent tool schemas/UI hints.\n"
            f"- contract_tool_mode: default output is compact summary; pass `include_full_contract=true` when full contract payload is required.\n"
            f"- contract_tool_input: call contract tools with arguments containing current `run_id`.\n"
            f"- recovery_rules: on apply_patch/context mismatch, read current file range and retry with refreshed patch.\n"
            f"- verification_rules: after edits, run recommended verification/build commands and fix failures before final response.\n"
            f"- output: respond with coding-agent updates and edits."
        )

    @staticmethod
    def _build_selected_agent_contract_context_content(
        *,
        run_id: str,
        app_id: str,
        selected_agent_contract: dict[str, Any] | None,
    ) -> str:
        _ = run_id
        contract_payload = (
            dict(selected_agent_contract)
            if isinstance(selected_agent_contract, dict)
            else {}
        )
        # Keep context deterministic across runs by stripping volatile metadata.
        contract_payload.pop("generated_at", None)
        payload = {
            "app_id": str(app_id or "").strip(),
            "context_version": "1",
            "selected_agent_contract": contract_payload,
        }
        return json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def _content_hash(content: str) -> str:
        return sha256(str(content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _files_hash(files: dict[str, str]) -> str:
        digest = sha256()
        for path, content in sorted((files or {}).items()):
            digest.update(str(path).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(content).encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    async def _seed_custom_tools_and_context(
        self,
        *,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        selected_agent_contract: dict[str, Any] | None,
    ) -> None:
        if self._config.skip_workspace_bootstrap:
            logger.info(
                "OPENCODE_BOOTSTRAP_SKIPPED run_id=%s app_id=%s sandbox_id=%s workspace_path=%s reason=skip_workspace_bootstrap",
                run_id,
                app_id,
                sandbox_id or "",
                workspace_path,
            )
            return
        try:
            bootstrap_files = build_opencode_bootstrap_files()
        except Exception as exc:
            raise OpenCodeServerClientError(
                f"Failed to load OpenCode custom-tool bootstrap files: {exc}"
            ) from exc

        context_content = self._build_selected_agent_contract_context_content(
            run_id=run_id,
            app_id=app_id,
            selected_agent_contract=selected_agent_contract,
        )
        bootstrap_hash = self._files_hash(bootstrap_files)
        context_hash = self._content_hash(context_content)
        seed_bootstrap_files = self._seed_bootstrap_files_on_run_start()
        logger.info(
            "OPENCODE_BOOTSTRAP mode=%s run_id=%s app_id=%s sandbox_id=%s workspace_path=%s seed_bootstrap=%s backend_name=%s override=%s",
            "sandbox" if self._sandbox_runtime_mode_enabled() else "host",
            run_id,
            app_id,
            sandbox_id or "",
            workspace_path,
            seed_bootstrap_files,
            str(getattr(self._sandbox_runtime_client, "backend_name", "") or ""),
            self._config.sandbox_controller_mode_override,
        )

        if self._sandbox_runtime_mode_enabled():
            if not sandbox_id:
                raise OpenCodeServerClientError(
                    "OpenCode sandbox mode requires sandbox_id for custom-tool bootstrap."
                )
            sandbox_key = str(sandbox_id).strip()

            async def _sandbox_write_if_changed(path: str, content: str) -> None:
                read_file = getattr(self._sandbox_runtime_client, "read_file", None)
                if callable(read_file):
                    try:
                        current_payload = await read_file(sandbox_id=sandbox_id, path=path)
                        current_content = current_payload.get("content") if isinstance(current_payload, dict) else None
                        if isinstance(current_content, str) and current_content == content:
                            return
                    except PublishedAppDraftDevRuntimeClientError:
                        # Missing/unreadable file should be overwritten below.
                        pass
                try:
                    await self._sandbox_runtime_client.write_file(
                        sandbox_id=sandbox_id,
                        path=path,
                        content=content,
                    )
                except PublishedAppDraftDevRuntimeClientError as exc:
                    raise OpenCodeServerClientError(
                        f"Failed to seed OpenCode custom tools in sandbox `{sandbox_id}` at `{path}`: {exc}"
                    ) from exc

            if (
                seed_bootstrap_files
                and hasattr(self._sandbox_runtime_client, "delete_file")
                and sandbox_key not in self._bootstrap_cleanup_done_targets
            ):
                for path in OPENCODE_DEPRECATED_TOOL_PATHS:
                    try:
                        await self._sandbox_runtime_client.delete_file(
                            sandbox_id=sandbox_id,
                            path=path,
                        )
                    except PublishedAppDraftDevRuntimeClientError:
                        # Best-effort cleanup for older workspaces that still have superseded tool files.
                        pass
                self._bootstrap_cleanup_done_targets.add(sandbox_key)

            should_seed_bootstrap = (
                seed_bootstrap_files
                and self._sandbox_bootstrap_hash.get(sandbox_key) != bootstrap_hash
            )
            should_seed_context = self._sandbox_context_hash.get(sandbox_key) != context_hash

            if should_seed_bootstrap:
                for path, content in sorted(bootstrap_files.items()):
                    await _sandbox_write_if_changed(path, content)
                self._sandbox_bootstrap_hash[sandbox_key] = bootstrap_hash
            elif sandbox_key not in self._sandbox_bootstrap_hash:
                # Bootstrap files are expected to be preinstalled with workspace templates.
                self._sandbox_bootstrap_hash[sandbox_key] = bootstrap_hash

            if should_seed_context:
                await _sandbox_write_if_changed(OPENCODE_BOOTSTRAP_CONTEXT_PATH, context_content)
                self._sandbox_context_hash[sandbox_key] = context_hash
            logger.info(
                "OPENCODE_BOOTSTRAP_SANDBOX seeded_bootstrap=%s seeded_context=%s run_id=%s sandbox_id=%s workspace_path=%s",
                should_seed_bootstrap,
                should_seed_context,
                run_id,
                sandbox_id,
                workspace_path,
            )
            return

        workspace_root_raw = str(workspace_path or "").strip()
        if not workspace_root_raw:
            raise OpenCodeServerClientError(
                "OpenCode host mode requires a local workspace_path for custom-tool bootstrap."
            )
        workspace_root_path = Path(workspace_root_raw).expanduser()
        if not workspace_root_path.is_absolute():
            raise OpenCodeServerClientError(
                f"OpenCode host-mode workspace_path must be absolute: {workspace_root_raw}"
            )
        try:
            workspace_root_path.mkdir(parents=True, exist_ok=True)
            workspace_root = workspace_root_path.resolve()
        except Exception as exc:
            logger.exception(
                "OPENCODE_BOOTSTRAP_HOST_INIT_FAILED run_id=%s app_id=%s sandbox_id=%s workspace_path=%s",
                run_id,
                app_id,
                sandbox_id or "",
                workspace_root_raw,
            )
            raise OpenCodeServerClientError(
                f"Failed to initialize OpenCode workspace path `{workspace_root_raw}`: {exc}"
            ) from exc

        workspace_key = str(workspace_root)
        should_seed_bootstrap = (
            seed_bootstrap_files
            and self._host_bootstrap_hash.get(workspace_key) != bootstrap_hash
        )
        should_seed_context = self._host_context_hash.get(workspace_key) != context_hash

        def write_workspace_file(path: str, content: str) -> None:
            normalized = str(path or "").replace("\\", "/").lstrip("/")
            if not normalized or ".." in normalized.split("/"):
                raise OpenCodeServerClientError(f"Invalid OpenCode bootstrap path: {path}")
            target = (workspace_root / normalized).resolve()
            try:
                target.relative_to(workspace_root)
            except Exception as exc:
                raise OpenCodeServerClientError(
                    f"OpenCode bootstrap path escapes workspace root: {normalized}"
                ) from exc
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except Exception as exc:
                raise OpenCodeServerClientError(
                    f"Failed to write OpenCode bootstrap file `{normalized}`: {exc}"
                ) from exc

        if should_seed_bootstrap:
            for path, content in sorted(bootstrap_files.items()):
                write_workspace_file(path, content)
            self._host_bootstrap_hash[workspace_key] = bootstrap_hash
        elif workspace_key not in self._host_bootstrap_hash:
            self._host_bootstrap_hash[workspace_key] = bootstrap_hash

        if should_seed_context:
            write_workspace_file(OPENCODE_BOOTSTRAP_CONTEXT_PATH, context_content)
            self._host_context_hash[workspace_key] = context_hash

        if seed_bootstrap_files and workspace_key not in self._bootstrap_cleanup_done_targets:
            for path in OPENCODE_DEPRECATED_TOOL_PATHS:
                normalized = str(path or "").replace("\\", "/").lstrip("/")
                if not normalized or ".." in normalized.split("/"):
                    continue
                target = (workspace_root / normalized).resolve()
                try:
                    target.relative_to(workspace_root)
                except Exception:
                    continue
                try:
                    if target.is_file():
                        target.unlink()
                except Exception:
                    # Best-effort cleanup for older local workspaces.
                    pass
            self._bootstrap_cleanup_done_targets.add(workspace_key)

    @staticmethod
    def _extract_text_from_message_payload(payload: dict[str, Any]) -> str:
        parts = payload.get("parts")
        if not isinstance(parts, list):
            message = payload.get("message")
            if isinstance(message, dict):
                parts = message.get("parts")
        if not isinstance(parts, list):
            data = payload.get("data")
            if isinstance(data, dict):
                parts = data.get("parts")
        if not isinstance(parts, list):
            result = payload.get("result")
            if isinstance(result, dict):
                parts = result.get("parts")
        if isinstance(parts, list):
            snippets: list[str] = []
            for part in parts:
                text = OpenCodeServerClient._extract_text_from_part(part)
                if text:
                    snippets.append(text)
            text = "\n".join(snippets).strip()
            if text:
                return text
        for key in ("text", "content", "value", "message", "result", "data", "payload"):
            text = OpenCodeServerClient._extract_text_from_part(payload.get(key))
            if text:
                return text
        return ""

    @staticmethod
    def _extract_official_assistant_message(payload: Any, *, parent_message_id: str) -> dict[str, Any] | None:
        candidates = OpenCodeServerClient._collect_official_assistant_candidates(payload)
        if not candidates:
            return None
        if parent_message_id:
            matching_parent: list[dict[str, Any]] = []
            for item in candidates:
                parent_id = OpenCodeServerClient._extract_candidate_parent_id(item)
                if parent_id and parent_id == parent_message_id:
                    matching_parent.append(item)
            selected = OpenCodeServerClient._select_best_assistant_candidate(matching_parent)
            if selected is not None:
                return selected
            # Some OpenCode versions omit parentID on assistant messages.
            without_parent: list[dict[str, Any]] = []
            for item in candidates:
                if not OpenCodeServerClient._extract_candidate_parent_id(item):
                    without_parent.append(item)
            selected = OpenCodeServerClient._select_best_assistant_candidate(without_parent)
            if selected is not None:
                return selected
        return OpenCodeServerClient._select_best_assistant_candidate(candidates)

    @staticmethod
    def _collect_official_assistant_candidates(payload: Any) -> list[dict[str, Any]]:
        stack: list[Any] = [payload]
        seen: set[int] = set()
        candidates: list[dict[str, Any]] = []
        while stack:
            current = stack.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)
            if isinstance(current, list):
                for item in reversed(current):
                    stack.append(item)
                continue
            if not isinstance(current, dict):
                continue
            info = current.get("info")
            if isinstance(info, dict):
                role = str(info.get("role") or "").strip().lower()
                if role == "assistant":
                    candidates.append(current)
            for key in ("messages", "items", "results", "data", "payload", "message", "result"):
                nested = current.get(key)
                if isinstance(nested, (dict, list)):
                    stack.append(nested)
        return candidates

    @staticmethod
    def _extract_candidate_parent_id(payload: dict[str, Any]) -> str:
        info = payload.get("info")
        if not isinstance(info, dict):
            return ""
        return str(info.get("parentID") or info.get("parentId") or "").strip()

    @staticmethod
    def _extract_candidate_message_id(payload: dict[str, Any]) -> str:
        info = payload.get("info")
        if not isinstance(info, dict):
            return ""
        return str(info.get("id") or "").strip()

    @staticmethod
    def _select_best_assistant_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        for item in reversed(candidates):
            if OpenCodeServerClient._extract_assistant_info_error(item):
                return item
        for item in reversed(candidates):
            if OpenCodeServerClient._extract_text_from_message_payload(item):
                return item
        for item in reversed(candidates):
            info = item.get("info")
            if not isinstance(info, dict):
                continue
            time_data = info.get("time")
            if isinstance(time_data, dict) and time_data.get("completed") is not None:
                return item
        return candidates[-1]

    @staticmethod
    def _sort_assistant_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def _key(item: dict[str, Any]) -> tuple[int, int]:
            info = item.get("info") if isinstance(item.get("info"), dict) else {}
            time_data = info.get("time") if isinstance(info.get("time"), dict) else {}
            created = int(time_data.get("created") or 0)
            completed = int(time_data.get("completed") or 0)
            return (created, completed)

        return sorted(candidates, key=_key)

    @staticmethod
    def _extract_incremental_text_deltas(*, message: dict[str, Any], state: dict[str, Any]) -> list[str]:
        parts = message.get("parts") if isinstance(message.get("parts"), list) else []
        offsets = state.setdefault("text_offsets", {})
        deltas: list[str] = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").strip().lower()
            if OpenCodeServerClient._should_skip_incremental_text_part_type(part_type):
                continue
            text = OpenCodeServerClient._extract_text_from_part(part)
            if not text:
                continue
            part_id = str(part.get("id") or f"part-{index}").strip()
            prev = int(offsets.get(part_id) or 0)
            if len(text) <= prev:
                continue
            deltas.append(text[prev:])
            offsets[part_id] = len(text)
        return deltas

    @staticmethod
    def _should_skip_incremental_text_part_type(part_type: str) -> bool:
        normalized = str(part_type or "").strip().lower()
        return normalized in {
            "tool",
            "step-start",
            "step-finish",
            "snapshot",
            "patch",
            "reasoning",
            "analysis",
            "thought",
        }

    @staticmethod
    def _extract_incremental_tool_events(*, message: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
        parts = message.get("parts") if isinstance(message.get("parts"), list) else []
        tool_status = state.setdefault("tool_status", {})
        tool_input_snapshot = state.setdefault("tool_input_snapshot", {})
        events: list[dict[str, Any]] = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict) or str(part.get("type") or "").strip().lower() != "tool":
                continue
            call_id = str(part.get("callID") or part.get("callId") or part.get("id") or f"tool-{index}").strip()
            tool_name = str(part.get("tool") or "").strip()
            state_payload = part.get("state") if isinstance(part.get("state"), dict) else {}
            status = str(state_payload.get("status") or "").strip().lower()
            previous = str(tool_status.get(call_id) or "").strip().lower()
            input_payload = state_payload.get("input")
            output_payload = state_payload.get("output")
            error_payload = str(state_payload.get("error") or state_payload.get("message") or "Tool failed").strip()
            input_signature = repr(input_payload) if input_payload is not None else ""
            previous_input_signature = str(tool_input_snapshot.get(call_id) or "")
            should_refresh_started = (
                previous in {"pending"}
                and status in {"running", "in_progress", "started"}
                and bool(input_signature)
                and input_signature != previous_input_signature
            )

            if status in {"running", "pending", "in_progress", "started"}:
                if previous not in {"running", "pending", "in_progress", "started"} or should_refresh_started:
                    events.append({"event": "tool.started", "payload": {"tool": tool_name, "span_id": call_id, "input": input_payload}})
            elif status in {"completed", "success", "done", "finished"}:
                if previous not in {"running", "pending", "in_progress", "started", "completed", "success", "done", "finished"}:
                    events.append({"event": "tool.started", "payload": {"tool": tool_name, "span_id": call_id, "input": input_payload}})
                if previous not in {"completed", "success", "done", "finished"}:
                    events.append(
                        {
                            "event": "tool.completed",
                            "payload": {
                                "tool": tool_name,
                                "span_id": call_id,
                                "input": input_payload,
                                "output": output_payload,
                            },
                        }
                    )
            elif status in {"failed", "error", "cancelled"}:
                if previous not in {"running", "pending", "in_progress", "started", "failed", "error", "cancelled"}:
                    events.append({"event": "tool.started", "payload": {"tool": tool_name, "span_id": call_id, "input": input_payload}})
                if previous not in {"failed", "error", "cancelled"}:
                    events.append(
                        {
                            "event": "tool.failed",
                            "payload": {
                                "tool": tool_name,
                                "span_id": call_id,
                                "error": error_payload,
                                "input": input_payload,
                                "output": output_payload,
                            },
                            "code": str(state_payload.get("code") or "").strip() or None,
                        }
                    )
            tool_status[call_id] = status
            tool_input_snapshot[call_id] = input_signature
        return events

    @staticmethod
    def _extract_text_from_part(part: Any) -> str:
        if isinstance(part, str):
            return part.strip()
        if isinstance(part, list):
            nested_text = [OpenCodeServerClient._extract_text_from_part(item) for item in part]
            return "\n".join(item for item in nested_text if item).strip()
        if not isinstance(part, dict):
            return ""
        for key in ("text", "content", "value"):
            value = part.get(key)
            nested_text = OpenCodeServerClient._extract_text_from_part(value)
            if nested_text:
                return nested_text
        for key in ("part", "parts", "payload", "data", "delta", "result", "message"):
            nested_text = OpenCodeServerClient._extract_text_from_part(part.get(key))
            if nested_text:
                return nested_text
        return ""

    @staticmethod
    def _extract_tool_events_from_message_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        parts = payload.get("parts")
        if not isinstance(parts, list):
            data = payload.get("data")
            if isinstance(data, dict):
                parts = data.get("parts")
        if not isinstance(parts, list):
            return []

        events: list[dict[str, Any]] = []
        for part in parts:
            if not isinstance(part, dict) or str(part.get("type") or "").strip().lower() != "tool":
                continue
            tool_name = str(part.get("tool") or "").strip()
            call_id = str(part.get("callID") or part.get("callId") or "").strip()
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            status = str(state.get("status") or "").strip().lower()
            input_payload = state.get("input")
            output_payload = state.get("output")

            started_payload = {"tool": tool_name, "span_id": call_id, "input": input_payload}
            if status in {"running", "pending", "in_progress", "started"}:
                events.append({"event": "tool.started", "payload": started_payload})
                continue

            if status in {"completed", "success", "done", "finished"}:
                events.append({"event": "tool.started", "payload": started_payload})
                events.append(
                    {
                        "event": "tool.completed",
                        "payload": {
                            "tool": tool_name,
                            "span_id": call_id,
                            "input": input_payload,
                            "output": output_payload,
                        },
                    }
                )
                continue

            if status in {"failed", "error", "cancelled"}:
                message = str(state.get("error") or state.get("message") or "Tool failed").strip()
                events.append({"event": "tool.started", "payload": started_payload})
                events.append(
                    {
                        "event": "tool.failed",
                        "payload": {
                            "tool": tool_name,
                            "span_id": call_id,
                            "input": input_payload,
                            "output": output_payload,
                        },
                        "code": str(state.get("code") or "").strip() or None,
                        "diagnostics": [{"message": message}],
                    }
                )
        return events

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any],
        retries: int,
        expect_json: bool = True,
        expect_dict: bool = True,
    ) -> Any:
        if not self._config.base_url:
            raise OpenCodeServerClientError("OpenCode base URL is not configured.")

        url = f"{self._config.base_url.rstrip('/')}{path}"
        headers = self._headers()
        attempts = max(0, retries) + 1
        last_error: Exception | None = None

        for _ in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self._timeout()) as client:
                    request_kwargs: dict[str, Any] = {"headers": headers}
                    if method.upper() != "GET":
                        request_kwargs["json"] = json_payload
                    response = await client.request(method, url, **request_kwargs)
                if response.status_code >= 400:
                    body = response.text.strip()
                    raise OpenCodeServerClientError(
                        f"OpenCode request failed ({response.status_code}): {body or response.reason_phrase}"
                    )
                if not expect_json:
                    return {"ok": True}
                raw = response.text.strip()
                if not raw:
                    return {}
                try:
                    payload = response.json()
                except Exception as exc:
                    content_type = response.headers.get("content-type", "")
                    preview = raw[:220]
                    raise OpenCodeServerClientError(
                        f"OpenCode server returned non-JSON response for {path} "
                        f"(status {response.status_code}, content-type `{content_type}`): {preview}"
                    ) from exc
                if expect_dict and not isinstance(payload, dict):
                    raise OpenCodeServerClientError("OpenCode server returned invalid JSON payload.")
                if isinstance(payload, dict):
                    return self._unwrap_payload(path=path, payload=payload)
                return payload
            except OpenCodeServerClientError as exc:
                last_error = exc
                break
            except Exception as exc:
                if (
                    isinstance(exc, httpx.ReadTimeout)
                    and method.upper() == "POST"
                    and "/session/" in path
                    and path.endswith("/message")
                ):
                    # Official API can keep POST /session/{id}/message open while generation continues.
                    # Treat read timeout as accepted and recover output via polling.
                    return {}
                last_error = exc

        if isinstance(last_error, OpenCodeServerClientError):
            raise last_error
        detail = str(last_error or "").strip()
        if not detail and last_error is not None:
            detail = last_error.__class__.__name__
        raise OpenCodeServerClientError(f"OpenCode request failed: {detail or 'unknown error'}")

    def _unwrap_payload(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        success = payload.get("success")
        if isinstance(success, bool):
            if not success:
                message = self._extract_error_message(payload)
                raise OpenCodeServerClientError(
                    f"OpenCode request failed for {path}: {message or 'success=false with no error details'}"
                )
            data = payload.get("data")
            if isinstance(data, dict):
                return data
        return payload

    @staticmethod
    def _extract_error_message(payload: dict[str, Any]) -> str:
        errors = payload.get("error")
        if isinstance(errors, list):
            parts: list[str] = []
            for item in errors:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    message = str(item.get("message") or item.get("code") or "").strip()
                    if message:
                        parts.append(message)
            if parts:
                return OpenCodeServerClient._sanitize_error_message("; ".join(parts))
        if isinstance(errors, dict):
            message = str(errors.get("message") or errors.get("code") or "").strip()
            if message:
                return OpenCodeServerClient._sanitize_error_message(message)
        if isinstance(errors, str) and errors.strip():
            return OpenCodeServerClient._sanitize_error_message(errors.strip())
        data = payload.get("data")
        if isinstance(data, dict):
            return OpenCodeServerClient._extract_error_message(data)
        return ""

    @staticmethod
    def _extract_response_error_message(payload: Any) -> str:
        # OpenCode can return assistant-shaped payloads that include structured errors
        # under `info.error`, `error`, or nested `data.error` fields.
        seen: set[int] = set()
        stack: list[Any] = [payload]
        while stack:
            current = stack.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)
            if isinstance(current, dict):
                for key in ("error", "errors", "message"):
                    value = current.get(key)
                    text = OpenCodeServerClient._extract_error_value(value, parent_key=key)
                    if text:
                        return text
                for nested in current.values():
                    if isinstance(nested, (dict, list)):
                        stack.append(nested)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
        return ""

    @staticmethod
    def _extract_assistant_info_error(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        info = payload.get("info")
        if not isinstance(info, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                nested_info = data.get("info")
                if isinstance(nested_info, dict):
                    info = nested_info
        if not isinstance(info, dict):
            return ""
        return OpenCodeServerClient._extract_error_value(info.get("error"), parent_key="error")

    @staticmethod
    def _extract_error_value(value: Any, *, parent_key: str) -> str:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ""
            lowered = stripped.lower()
            if parent_key in {"error", "errors"}:
                return OpenCodeServerClient._sanitize_error_message(stripped)
            if any(token in lowered for token in ("error", "exception", "failed", "invalid", "traceback")):
                return OpenCodeServerClient._sanitize_error_message(stripped)
            return ""
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str) and message.strip():
                return OpenCodeServerClient._sanitize_error_message(message.strip())
            for nested in value.values():
                if not isinstance(nested, (dict, list)):
                    continue
                nested_text = OpenCodeServerClient._extract_error_value(nested, parent_key=parent_key)
                if nested_text:
                    return nested_text
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    continue
                nested_text = OpenCodeServerClient._extract_error_value(nested, parent_key=parent_key)
                if nested_text:
                    return nested_text
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                detail = value.get("detail")
                if isinstance(detail, str) and detail.strip():
                    return OpenCodeServerClient._sanitize_error_message(f"{name.strip()}: {detail.strip()}")
                return OpenCodeServerClient._sanitize_error_message(name.strip())
            code = value.get("code")
            if isinstance(code, str) and code.strip():
                return OpenCodeServerClient._sanitize_error_message(code.strip())
        if isinstance(value, list):
            for item in value:
                nested_text = OpenCodeServerClient._extract_error_value(item, parent_key=parent_key)
                if nested_text:
                    return nested_text
        return ""

    @staticmethod
    def _compact_json_preview(payload: dict[str, Any], *, max_chars: int = 260) -> str:
        try:
            serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        except Exception:
            serialized = str(payload)
        return OpenCodeServerClient._sanitize_error_message(serialized[:max_chars])

    @staticmethod
    def _sanitize_error_message(message: str) -> str:
        text = str(message or "")
        text = re.sub(
            r"-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY]",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r'("private_key"\s*:\s*")(.+?)(")',
            r'\1[REDACTED]\3',
            text,
            flags=re.DOTALL,
        )
        return text

    async def _sleep(self, seconds: float) -> None:
        # Isolated for testability in polling paths.
        import asyncio

        await asyncio.sleep(seconds)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        if isinstance(self._config.extra_headers, dict):
            headers.update({str(key): str(value) for key, value in self._config.extra_headers.items() if str(value).strip()})
        return headers

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            timeout=self._config.request_timeout_seconds,
            connect=self._config.connect_timeout_seconds,
        )
