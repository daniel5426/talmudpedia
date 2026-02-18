from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

import httpx


class OpenCodeServerClientError(Exception):
    pass


@dataclass(frozen=True)
class OpenCodeServerClientConfig:
    enabled: bool
    base_url: str | None
    api_key: str | None
    request_timeout_seconds: float
    connect_timeout_seconds: float
    health_cache_seconds: int


class OpenCodeServerClient:
    def __init__(self, config: OpenCodeServerClientConfig):
        self._config = config
        self._health_checked_at: datetime | None = None
        self._health_ok = False
        self._api_mode: str | None = None
        self._official_run_state: dict[str, dict[str, Any]] = {}

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
        return bool(self._config.enabled and self._config.base_url)

    async def ensure_healthy(self, *, force: bool = False) -> None:
        if not self.is_enabled:
            raise OpenCodeServerClientError(
                "OpenCode engine is disabled or missing APPS_CODING_AGENT_OPENCODE_BASE_URL."
            )

        now = datetime.now(timezone.utc)
        if not force and self._health_checked_at is not None:
            if now - self._health_checked_at <= timedelta(seconds=self._config.health_cache_seconds):
                if self._health_ok:
                    return
                raise OpenCodeServerClientError("OpenCode engine health check is currently failing.")

        if force:
            self._api_mode = None
        await self._ensure_api_mode()
        if self._api_mode == "official":
            await self._request("GET", "/global/health", json_payload={}, retries=1, expect_json=True)
        else:
            await self._request("GET", "/health", json_payload={}, retries=1, expect_json=False)
        self._health_checked_at = now
        self._health_ok = True

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
    ) -> str:
        mode = await self._ensure_api_mode()
        if mode == "official":
            return await self._start_run_official(
                run_id=run_id,
                app_id=app_id,
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                model_id=model_id,
                prompt=prompt,
                messages=messages,
            )

        payload = {
            "run_id": run_id,
            "app_id": app_id,
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "model_id": model_id,
            "prompt": prompt,
            "messages": messages,
            "ephemeral": True,
        }
        response = await self._request("POST", "/v1/runs", json_payload=payload, retries=0)
        run_ref = response.get("run_ref") or response.get("id")
        if not run_ref:
            raise OpenCodeServerClientError("OpenCode run start response is missing run_ref.")
        return str(run_ref)

    async def stream_run_events(self, *, run_ref: str) -> AsyncGenerator[dict[str, Any], None]:
        if not self._config.base_url:
            raise OpenCodeServerClientError("OpenCode base URL is not configured.")
        mode = await self._ensure_api_mode()
        if mode == "official":
            async for event in self._stream_official_run_events(session_id=run_ref):
                yield event
            return

        url = f"{self._config.base_url.rstrip('/')}/v1/runs/{run_ref}/events"
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace").strip()
                        raise OpenCodeServerClientError(
                            f"OpenCode stream request failed ({response.status_code}): {body or response.reason_phrase}"
                        )
                    async for line in response.aiter_lines():
                        raw = (line or "").strip()
                        if not raw or raw.startswith(":"):
                            continue
                        if raw.startswith("data:"):
                            raw = raw[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            parsed = json.loads(raw)
                        except Exception as exc:
                            raise OpenCodeServerClientError(f"OpenCode event stream returned invalid JSON: {raw}") from exc
                        if isinstance(parsed, dict):
                            yield parsed
        except OpenCodeServerClientError:
            raise
        except Exception as exc:
            raise OpenCodeServerClientError(f"OpenCode stream request failed: {exc}") from exc

    async def cancel_run(self, *, run_ref: str) -> bool:
        mode = await self._ensure_api_mode()
        if mode == "official":
            response = await self._request("POST", f"/session/{run_ref}/abort", json_payload={}, retries=0)
            if isinstance(response.get("cancelled"), bool):
                return bool(response.get("cancelled"))
            if isinstance(response.get("ok"), bool):
                return bool(response.get("ok"))
            if isinstance(response.get("aborted"), bool):
                return bool(response.get("aborted"))
            return True

        response = await self._request("POST", f"/v1/runs/{run_ref}/cancel", json_payload={}, retries=0)
        cancelled = response.get("cancelled")
        if isinstance(cancelled, bool):
            return cancelled
        return True

    async def _start_run_official(
        self,
        *,
        run_id: str,
        app_id: str,
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        session_payload: dict[str, Any] = {"title": f"App {app_id} run {run_id}"}
        permission_rules = self._build_official_session_permission_rules(workspace_path)
        if permission_rules:
            session_payload["permission"] = permission_rules
        session = await self._request("POST", "/session", json_payload=session_payload, retries=0)
        session_id = str(session.get("id") or session.get("sessionID") or session.get("sessionId") or "").strip()
        if not session_id:
            raise OpenCodeServerClientError("OpenCode server returned invalid session response (missing id).")

        text_prompt = self._build_prompt(prompt=prompt, messages=messages, workspace_path=workspace_path, sandbox_id=sandbox_id)
        message_id = f"msg-{run_id}-{uuid4().hex[:10]}"
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
        prompt_async_payload: dict[str, Any] = {
            "messageID": message_id,
            "parts": [{"type": "text", "text": text_prompt}],
        }
        if model:
            prompt_async_payload["model"] = model

        try:
            await self._request(
                "POST",
                f"/session/{session_id}/prompt_async",
                json_payload=prompt_async_payload,
                retries=0,
                expect_json=False,
            )
        except OpenCodeServerClientError:
            # Fallback for servers/modes where prompt_async is unavailable.
            response = await self._request("POST", f"/session/{session_id}/message", json_payload=message_payload, retries=0)
            embedded_error = self._extract_assistant_info_error(response)
            if embedded_error:
                safe_error = self._sanitize_error_message(embedded_error)
                raise OpenCodeServerClientError(f"OpenCode assistant error: {safe_error}")
            initial_response = response

        assistant_message_ids: set[str] = set()
        response_info = initial_response.get("info") if isinstance(initial_response.get("info"), dict) else {}
        if str(response_info.get("role") or "").strip().lower() == "assistant":
            response_message_id = str(response_info.get("id") or "").strip()
            if response_message_id:
                assistant_message_ids.add(response_message_id)
        self._official_run_state[session_id] = {
            "parent_message_id": message_id,
            "initial_payload": initial_response,
            "initial_emitted": False,
            "complete_on_initial_text": bool(self._extract_text_from_message_payload(initial_response)),
            "text_offsets": {},
            "tool_status": {},
            "message_roles": {message_id: "user"},
            "part_types": {},
            "completed": False,
            "last_progress_at": time.monotonic(),
            "assistant_message_ids": assistant_message_ids,
        }
        return session_id

    async def _stream_official_run_events(self, *, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        use_global_event_stream = (os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_USE_GLOBAL_EVENT_STREAM") or "1").strip().lower()
        should_use_global = use_global_event_stream in {"1", "true", "yes", "on"}
        terminal_emitted = False
        if should_use_global:
            try:
                async for event in self._stream_official_run_events_via_global_events(session_id=session_id):
                    if str(event.get("event") or "").strip() in {"run.completed", "run.failed"}:
                        terminal_emitted = True
                    yield event
                if terminal_emitted:
                    return
            except OpenCodeServerClientError:
                raise
            except Exception:
                # Fall back to snapshot polling if global stream is unavailable.
                pass

        async for event in self._stream_official_run_events_snapshot(session_id=session_id):
            yield event

    async def _stream_official_run_events_via_global_events(self, *, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        state = self._official_run_state.setdefault(
            session_id,
            {
                "parent_message_id": "",
                "initial_payload": {},
                "initial_emitted": False,
                "complete_on_initial_text": False,
                "text_offsets": {},
                "tool_status": {},
                "message_roles": {},
                "part_types": {},
                "completed": False,
                "last_progress_at": time.monotonic(),
                "assistant_message_ids": set(),
            },
        )
        assistant_message_ids = state.setdefault("assistant_message_ids", set())
        message_roles = state.setdefault("message_roles", {})
        part_types = state.setdefault("part_types", {})
        parent_message_id = str(state.get("parent_message_id") or "").strip()
        timeout_seconds = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_STREAM_TIMEOUT_SECONDS") or "300").strip())
        deadline = time.monotonic() + max(30.0, timeout_seconds)
        global_read_timeout = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_GLOBAL_READ_TIMEOUT_SECONDS") or "30").strip())
        global_read_timeout = max(2.0, global_read_timeout)
        saw_assistant_text = False
        terminal_event: dict[str, Any] | None = None

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
                async for line in response.aiter_lines():
                    if time.monotonic() >= deadline:
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
                    event_type = str(payload.get("type") or "").strip()
                    properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
                    if not event_type or not properties:
                        continue
                    event_session_id = self._extract_session_id_from_global_event_properties(properties)
                    if event_session_id != session_id:
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
                        embedded_error = self._extract_response_error_message(info)
                        if embedded_error:
                            safe_error = self._sanitize_error_message(embedded_error)
                            terminal_event = {
                                "event": "run.failed",
                                "payload": {"error": f"OpenCode assistant error: {safe_error}"},
                                "code": "OPENCODE_ASSISTANT_ERROR",
                            }
                            break
                        continue

                    if event_type == "message.part.delta":
                        message_id = str(properties.get("messageID") or "").strip()
                        role = str(message_roles.get(message_id) or "").strip().lower()
                        if role and role != "assistant":
                            continue
                        if message_id and not role and message_id not in assistant_message_ids:
                            continue
                        if str(properties.get("field") or "").strip() != "text":
                            continue
                        part_id = str(properties.get("partID") or "").strip()
                        part_type = str(part_types.get(part_id) or "").strip().lower()
                        if self._should_skip_incremental_text_part_type(part_type):
                            continue
                        delta = str(properties.get("delta") or "")
                        if not delta:
                            continue
                        offsets = state.setdefault("text_offsets", {})
                        offset_key = part_id or f"{message_id}:delta"
                        previous_offset = int(offsets.get(offset_key) or 0)
                        offsets[offset_key] = previous_offset + len(delta)
                        saw_assistant_text = True
                        state["last_progress_at"] = time.monotonic()
                        yield {"event": "assistant.delta", "payload": {"content": delta}}
                        continue

                    if event_type == "message.part.updated":
                        part = properties.get("part") if isinstance(properties.get("part"), dict) else {}
                        if not part:
                            continue
                        message_id = str(part.get("messageID") or "").strip()
                        role = str(message_roles.get(message_id) or "").strip().lower()
                        if role and role != "assistant":
                            continue
                        part_id = str(part.get("id") or "").strip()
                        part_type = str(part.get("type") or "").strip().lower()
                        if part_id:
                            if part_type:
                                part_types[part_id] = part_type
                        if message_id and not role and message_id not in assistant_message_ids and part_type == "text":
                            # Avoid echoing user prompt text before role metadata lands.
                            continue
                        for event in self._extract_incremental_tool_events(message={"parts": [part]}, state=state):
                            state["last_progress_at"] = time.monotonic()
                            yield event
                        for delta in self._extract_incremental_text_deltas(message={"parts": [part]}, state=state):
                            saw_assistant_text = True
                            state["last_progress_at"] = time.monotonic()
                            yield {"event": "assistant.delta", "payload": {"content": delta}}
                        continue

                    if event_type == "session.error":
                        details = self._compact_json_preview(properties)
                        terminal_event = {
                            "event": "run.failed",
                            "payload": {"error": f"OpenCode session failed. response={details}"},
                            "code": "OPENCODE_SESSION_ERROR",
                        }
                        break

                    if event_type == "session.idle":
                        messages_payload = await self._request(
                            "GET",
                            f"/session/{session_id}/message",
                            json_payload={},
                            retries=0,
                            expect_dict=False,
                        )
                        candidates = self._collect_official_assistant_candidates(messages_payload)
                        if parent_message_id:
                            filtered = [
                                item
                                for item in candidates
                                if self._extract_candidate_parent_id(item) in {"", parent_message_id}
                            ]
                            if filtered:
                                candidates = filtered
                        candidates = self._sort_assistant_candidates(candidates)
                        last_info_error = ""
                        for message in candidates:
                            info = message.get("info") if isinstance(message.get("info"), dict) else {}
                            message_id = str(info.get("id") or "").strip()
                            role = str(info.get("role") or "").strip().lower()
                            if message_id and role:
                                message_roles[message_id] = role
                            if message_id:
                                assistant_message_ids.add(message_id)
                            for event in self._extract_incremental_tool_events(message=message, state=state):
                                state["last_progress_at"] = time.monotonic()
                                yield event
                            for delta in self._extract_incremental_text_deltas(message=message, state=state):
                                saw_assistant_text = True
                                state["last_progress_at"] = time.monotonic()
                                yield {"event": "assistant.delta", "payload": {"content": delta}}
                            embedded_error = self._extract_assistant_info_error(message)
                            if embedded_error:
                                last_info_error = self._sanitize_error_message(embedded_error)
                        if saw_assistant_text:
                            terminal_event = {"event": "run.completed", "payload": {"status": "completed"}}
                        elif last_info_error:
                            terminal_event = {
                                "event": "run.failed",
                                "payload": {"error": f"OpenCode assistant error: {last_info_error}"},
                                "code": "OPENCODE_ASSISTANT_ERROR",
                            }
                        else:
                            detail_payload = messages_payload if isinstance(messages_payload, dict) else {"messages": messages_payload}
                            details = self._compact_json_preview(detail_payload)
                            terminal_event = {
                                "event": "run.failed",
                                "payload": {"error": f"OpenCode response did not include assistant text. response={details}"},
                                "code": "OPENCODE_EMPTY_RESPONSE",
                            }
                        break

        if terminal_event is not None:
            yield terminal_event
            self._official_run_state.pop(session_id, None)
            return

        # No terminal event observed; let snapshot polling handle completion/failure.

    async def _stream_official_run_events_snapshot(self, *, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        state = self._official_run_state.setdefault(
            session_id,
            {
                "parent_message_id": "",
                "initial_payload": {},
                "initial_emitted": False,
                "complete_on_initial_text": False,
                "text_offsets": {},
                "tool_status": {},
                "message_roles": {},
                "part_types": {},
                "completed": False,
                "last_progress_at": time.monotonic(),
            },
        )
        parent_message_id = str(state.get("parent_message_id") or "").strip()
        timeout_seconds = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_STREAM_TIMEOUT_SECONDS") or "300").strip())
        deadline = time.monotonic() + max(30.0, timeout_seconds)
        poll_interval_seconds = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_POLL_INTERVAL_SECONDS") or "0.35").strip())
        poll_interval_seconds = max(0.1, poll_interval_seconds)
        saw_assistant_text = False
        last_assistant_info_error = ""

        while time.monotonic() < deadline:
            used_initial_payload = not bool(state.get("initial_emitted"))
            payload: Any
            if used_initial_payload:
                payload = state.get("initial_payload") or {}
                state["initial_emitted"] = True
            else:
                payload = await self._request("GET", f"/session/{session_id}/message", json_payload={}, retries=0, expect_dict=False)

            candidates = self._collect_official_assistant_candidates(payload)
            if not candidates and isinstance(payload, dict):
                if isinstance(payload.get("parts"), list):
                    candidates = [payload]
                else:
                    data_payload = payload.get("data")
                    if isinstance(data_payload, dict) and isinstance(data_payload.get("parts"), list):
                        candidates = [data_payload]
            if parent_message_id:
                filtered = [
                    item
                    for item in candidates
                    if self._extract_candidate_parent_id(item) in {"", parent_message_id}
                ]
                if filtered:
                    candidates = filtered
            candidates = self._sort_assistant_candidates(candidates)

            if used_initial_payload and isinstance(payload, dict) and payload and not candidates and not saw_assistant_text:
                details = self._compact_json_preview(payload)
                yield {
                    "event": "run.failed",
                    "payload": {"error": f"OpenCode response did not include assistant text. response={details}"},
                    "code": "OPENCODE_EMPTY_RESPONSE",
                }
                self._official_run_state.pop(session_id, None)
                return

            for message in candidates:
                embedded_error = self._extract_assistant_info_error(message)
                if embedded_error:
                    last_assistant_info_error = self._sanitize_error_message(embedded_error)

                for event in self._extract_incremental_tool_events(message=message, state=state):
                    state["last_progress_at"] = time.monotonic()
                    yield event
                for delta in self._extract_incremental_text_deltas(message=message, state=state):
                    saw_assistant_text = True
                    state["last_progress_at"] = time.monotonic()
                    yield {"event": "assistant.delta", "payload": {"content": delta}}

            if bool(state.get("complete_on_initial_text")) and saw_assistant_text:
                yield {"event": "run.completed", "payload": {"status": "completed"}}
                self._official_run_state.pop(session_id, None)
                return

            running_statuses = {"running", "pending", "in_progress", "started"}
            tool_status = state.get("tool_status") if isinstance(state.get("tool_status"), dict) else {}
            has_running_tools = any(str(value or "").strip().lower() in running_statuses for value in tool_status.values())
            settle_seconds = float((os.getenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_STREAM_SETTLE_SECONDS") or "1.0").strip())
            last_progress_at = float(state.get("last_progress_at") or 0.0)
            if saw_assistant_text and not has_running_tools and (time.monotonic() - last_progress_at) >= max(0.2, settle_seconds):
                yield {"event": "run.completed", "payload": {"status": "completed"}}
                self._official_run_state.pop(session_id, None)
                return
            if (not saw_assistant_text) and last_assistant_info_error and not has_running_tools and (
                (time.monotonic() - last_progress_at) >= max(0.2, settle_seconds)
            ):
                yield {
                    "event": "run.failed",
                    "payload": {"error": f"OpenCode assistant error: {last_assistant_info_error}"},
                    "code": "OPENCODE_ASSISTANT_ERROR",
                }
                self._official_run_state.pop(session_id, None)
                return

            await self._sleep(poll_interval_seconds)

        if (not saw_assistant_text) and last_assistant_info_error:
            yield {
                "event": "run.failed",
                "payload": {"error": f"OpenCode assistant error: {last_assistant_info_error}"},
                "code": "OPENCODE_ASSISTANT_ERROR",
            }
            self._official_run_state.pop(session_id, None)
            return

        yield {
            "event": "run.failed",
            "payload": {"error": "OpenCode stream timed out before completion."},
            "code": "OPENCODE_STREAM_TIMEOUT",
        }
        self._official_run_state.pop(session_id, None)

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
        for value in properties.values():
            if not isinstance(value, dict):
                continue
            nested = str(value.get("sessionID") or value.get("sessionId") or "").strip()
            if nested:
                return nested
        return ""

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
            return []
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
        return [{"permission": "external_directory", "pattern": pattern, "action": "allow"} for pattern in patterns]

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
        official_error: Exception | None = None
        try:
            await self._request("GET", "/global/health", json_payload={}, retries=1, expect_json=True)
            self._api_mode = "official"
            return self._api_mode
        except Exception as exc:
            official_error = exc
        try:
            await self._request("GET", "/health", json_payload={}, retries=1, expect_json=False)
            self._api_mode = "legacy"
            return self._api_mode
        except Exception as legacy_error:
            raise OpenCodeServerClientError(
                f"OpenCode health check failed for both official and legacy APIs "
                f"(official: {official_error}; legacy: {legacy_error})"
            ) from legacy_error

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
            f"- sandbox_id: {sandbox_id or 'unknown'}\n"
            f"- workspace_path: {workspace_path or 'unknown'}\n"
            f"- output: respond with coding-agent updates and edits."
        )

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

            if status in {"running", "pending", "in_progress", "started"}:
                if previous not in {"running", "pending", "in_progress", "started"}:
                    events.append({"event": "tool.started", "payload": {"tool": tool_name, "span_id": call_id, "input": input_payload}})
            elif status in {"completed", "success", "done", "finished"}:
                if previous not in {"running", "pending", "in_progress", "started", "completed", "success", "done", "finished"}:
                    events.append({"event": "tool.started", "payload": {"tool": tool_name, "span_id": call_id, "input": input_payload}})
                if previous not in {"completed", "success", "done", "finished"}:
                    events.append(
                        {
                            "event": "tool.completed",
                            "payload": {"tool": tool_name, "span_id": call_id, "output": output_payload},
                        }
                    )
            elif status in {"failed", "error", "cancelled"}:
                if previous not in {"running", "pending", "in_progress", "started", "failed", "error", "cancelled"}:
                    events.append({"event": "tool.started", "payload": {"tool": tool_name, "span_id": call_id, "input": input_payload}})
                if previous not in {"failed", "error", "cancelled"}:
                    events.append(
                        {
                            "event": "tool.failed",
                            "payload": {"tool": tool_name, "span_id": call_id, "error": error_payload, "output": output_payload},
                            "code": str(state_payload.get("code") or "").strip() or None,
                        }
                    )
            tool_status[call_id] = status
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
                        "payload": {"tool": tool_name, "span_id": call_id, "output": output_payload},
                    }
                )
                continue

            if status in {"failed", "error", "cancelled"}:
                message = str(state.get("error") or state.get("message") or "Tool failed").strip()
                events.append({"event": "tool.started", "payload": started_payload})
                events.append(
                    {
                        "event": "tool.failed",
                        "payload": {"tool": tool_name, "span_id": call_id, "output": output_payload},
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
        return headers

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            timeout=self._config.request_timeout_seconds,
            connect=self._config.connect_timeout_seconds,
        )
