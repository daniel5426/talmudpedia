from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, AsyncGenerator
from uuid import UUID

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_agent_engines.base import EngineRunContext
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE

logger = logging.getLogger(__name__)


class PublishedAppCodingAgentRuntimeStreamingMixin:
    def _envelope(
        self,
        *,
        seq: int,
        event: str,
        run_id: UUID,
        app_id: UUID,
        stage: str,
        payload: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": event,
            "run_id": str(run_id),
            "app_id": str(app_id),
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "payload": payload or {},
            "diagnostics": diagnostics or [],
        }
        return data

    @staticmethod
    def _coerce_assistant_text(value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        parts.append(text)
                    continue
                if isinstance(item, dict):
                    nested = PublishedAppCodingAgentRuntimeStreamingMixin._coerce_assistant_text(item)
                    if nested:
                        parts.append(nested)
            joined = " ".join(parts).strip()
            return joined or None
        if isinstance(value, dict):
            for key in ("content", "message", "text", "summary"):
                candidate = value.get(key)
                text = PublishedAppCodingAgentRuntimeStreamingMixin._coerce_assistant_text(candidate)
                if text:
                    return text
        return None

    def _extract_assistant_text_from_output(self, output_result: Any) -> str | None:
        if not isinstance(output_result, dict):
            return None

        state = output_result.get("state")
        if isinstance(state, dict):
            text = self._coerce_assistant_text(state.get("last_agent_output"))
            if text:
                return text

        text = self._coerce_assistant_text(output_result.get("last_agent_output"))
        if text:
            return text

        messages = output_result.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or message.get("type") or "").strip().lower()
                if role not in {"assistant", "ai"}:
                    continue
                text = self._coerce_assistant_text(message.get("content"))
                if text:
                    return text

        return None

    def _fallback_assistant_text(self, run: AgentRun) -> str:
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        prompt = str(input_params.get("input") or "").strip().lower()
        if prompt in {"hi", "hello", "hey", "yo", "shalom"}:
            return "Hi. I can edit app code, run checks, and explain changes. What would you like to change?"
        if "what can you do" in prompt or prompt == "help" or "how can you help" in prompt:
            return (
                "I can inspect and edit files, run targeted checks/tests, and create or restore checkpoints. "
                "Tell me what you want to build or fix."
            )
        return "I can help with code changes, debugging, and verification in this app workspace. Tell me your goal."

    @staticmethod
    def _stream_guardrail_seconds() -> tuple[float, float]:
        inactivity_raw = (os.getenv("APPS_CODING_AGENT_STREAM_INACTIVITY_TIMEOUT_SECONDS") or "75").strip()
        max_duration_raw = (os.getenv("APPS_CODING_AGENT_STREAM_MAX_DURATION_SECONDS") or "300").strip()
        try:
            inactivity_timeout = float(inactivity_raw)
        except Exception:
            inactivity_timeout = 75.0
        try:
            max_duration = float(max_duration_raw)
        except Exception:
            max_duration = 300.0
        inactivity_timeout = max(10.0, inactivity_timeout)
        max_duration = max(inactivity_timeout + 5.0, max_duration)
        return inactivity_timeout, max_duration

    @staticmethod
    def _extract_chat_session_id(run: AgentRun) -> UUID | None:
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        raw = str(context.get("chat_session_id") or "").strip()
        if not raw:
            return None
        try:
            return UUID(raw)
        except Exception:
            return None

    async def _persist_assistant_chat_message_if_needed(
        self,
        *,
        run: AgentRun,
        assistant_text: str,
    ) -> None:
        session_id = self._extract_chat_session_id(run)
        if session_id is None:
            return
        text = str(assistant_text or "").strip()
        if not text:
            return
        history_service = PublishedAppCodingChatHistoryService(self.db)
        await history_service.persist_assistant_message(
            session_id=session_id,
            run_id=run.id,
            content=text,
        )

    async def stream_run_events(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
        resume_payload: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = run.id
        persistent_run = await self.db.get(AgentRun, run_id)
        if persistent_run is not None:
            run = persistent_run

        seq = 1
        assistant_delta_emitted = False
        assistant_chunks: list[str] = []
        assistant_message_persisted = False
        first_token_recorded = False
        stream_started_at = time.monotonic()
        saw_write_tool_event = False
        assistant_delta_events = 0

        def emit(
            event: str,
            stage: str,
            payload: dict[str, Any] | None = None,
            diagnostics: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            nonlocal seq
            envelope = self._envelope(
                seq=seq,
                event=event,
                run_id=run.id,
                app_id=app.id,
                stage=stage,
                payload=payload,
                diagnostics=diagnostics,
            )
            seq += 1
            return envelope

        async def persist_assistant_message_for_terminal(default_text: str | None = None) -> None:
            nonlocal assistant_message_persisted
            if assistant_message_persisted:
                return
            text = "".join(assistant_chunks).strip()
            if not text:
                text = str(default_text or "").strip()
            if not text:
                text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
            if not text:
                return
            await self._persist_assistant_chat_message_if_needed(run=run, assistant_text=text)
            assistant_message_persisted = True

        async def finalize_sandbox(reason: str) -> None:
            _ = reason
            context = self._run_context(run)
            context["preview_sandbox_status"] = "running"

        async def release_run_lock() -> None:
            await self._clear_preview_run_lock(
                app_id=run.published_app_id,
                actor_id=run.initiator_user_id or run.user_id,
                run_id=run.id,
            )
            await self.db.commit()

        yield emit(
            "run.accepted",
            "run",
            {
                "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                "surface": CODING_AGENT_SURFACE,
            },
        )
        yield emit("plan.updated", "plan", {"summary": "Coding-agent run started"})

        def terminal_event_for_status(status_value: str) -> str:
            normalized = str(status_value or "").strip().lower()
            if normalized == RunStatus.completed.value:
                return "run.completed"
            if normalized == RunStatus.cancelled.value:
                return "run.cancelled"
            if normalized == RunStatus.paused.value:
                return "run.paused"
            return "run.failed"

        terminal_status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if terminal_status in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
            RunStatus.paused.value,
        }:
            if terminal_status == RunStatus.completed.value:
                await finalize_sandbox("stopped")
                assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                assistant_chunks.append(assistant_text)
                yield emit("assistant.delta", "assistant", {"content": assistant_text})
                await persist_assistant_message_for_terminal(assistant_text)
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.completed",
                    assistant_delta_events=1 if assistant_text else 0,
                    saw_write_tool_event=False,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.completed", "run", self.serialize_run(run))
            elif terminal_status == RunStatus.cancelled.value:
                await finalize_sandbox("stopped")
                await persist_assistant_message_for_terminal("Run cancelled.")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.cancelled",
                    assistant_delta_events=0,
                    saw_write_tool_event=False,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.cancelled", "run", self.serialize_run(run))
            elif terminal_status == RunStatus.paused.value:
                await finalize_sandbox("stopped")
                await persist_assistant_message_for_terminal("Run paused.")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.paused",
                    assistant_delta_events=0,
                    saw_write_tool_event=False,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.paused", "run", self.serialize_run(run))
            else:
                await finalize_sandbox("error")
                await persist_assistant_message_for_terminal(run.error_message or f"run {terminal_status}")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.failed",
                    assistant_delta_events=0,
                    saw_write_tool_event=False,
                    revision_created=bool(run.result_revision_id),
                )
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": run.error_message or f"run {terminal_status}"}],
                )
                await release_run_lock()
            return

        run_context = self._run_context(run)
        sandbox_id = str(run_context.get("preview_sandbox_id") or "").strip()
        if not sandbox_id:
            sandbox_id, sandbox_error = await self._recover_or_bootstrap_run_sandbox_context(run=run, app=app)
        else:
            sandbox_error = None
        if not sandbox_id:
            run.status = RunStatus.failed
            run.error_message = sandbox_error or "Preview sandbox session is required before execution."
            run.completed_at = datetime.now(timezone.utc)
            await release_run_lock()
            await self.db.commit()
            await persist_assistant_message_for_terminal(run.error_message)
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"code": "CODING_AGENT_SANDBOX_REQUIRED", "message": run.error_message}],
            )
            return

        try:
            engine = self._resolve_engine_for_run(run)
            inactivity_timeout_s, max_stream_duration_s = self._stream_guardrail_seconds()
            stream_deadline = time.monotonic() + max_stream_duration_s
            engine_iter = engine.stream(
                EngineRunContext(
                    app=app,
                    run=run,
                    resume_payload=resume_payload,
                )
            ).__aiter__()
            terminal_engine_event: str | None = None
            terminal_engine_payload: dict[str, Any] = {}
            terminal_engine_diagnostics: list[dict[str, Any]] | None = None
            status_poll_timeout_s = min(2.0, max(0.5, inactivity_timeout_s / 5.0))
            last_provider_progress_at = time.monotonic()
            try:
                while True:
                    remaining = stream_deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Coding-agent stream exceeded max duration ({int(max_stream_duration_s)}s) without terminal event."
                        )
                    if time.monotonic() - last_provider_progress_at > inactivity_timeout_s:
                        latest_run = await self.db.get(AgentRun, run_id)
                        latest_status = (
                            latest_run.status.value if hasattr(latest_run.status, "value") else str(latest_run.status)
                        ) if latest_run is not None else ""
                        if latest_run is not None and latest_status in {
                            RunStatus.completed.value,
                            RunStatus.failed.value,
                            RunStatus.cancelled.value,
                            RunStatus.paused.value,
                        }:
                            run = latest_run
                            terminal_engine_event = terminal_event_for_status(latest_status)
                            break
                        raise TimeoutError(
                            f"Coding-agent stream stalled for {int(inactivity_timeout_s)}s without provider progress."
                        )
                    next_timeout = min(status_poll_timeout_s, remaining)
                    try:
                        raw_event = await asyncio.wait_for(engine_iter.__anext__(), timeout=next_timeout)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        latest_run = await self.db.get(AgentRun, run_id)
                        latest_status = (
                            latest_run.status.value if hasattr(latest_run.status, "value") else str(latest_run.status)
                        ) if latest_run is not None else ""
                        if latest_run is not None and latest_status in {
                            RunStatus.completed.value,
                            RunStatus.failed.value,
                            RunStatus.cancelled.value,
                            RunStatus.paused.value,
                        }:
                            run = latest_run
                            terminal_engine_event = terminal_event_for_status(latest_status)
                            break
                        continue
                    last_provider_progress_at = time.monotonic()
                    mapped_event = raw_event.event
                    stage = raw_event.stage
                    payload = raw_event.payload
                    diagnostics = raw_event.diagnostics
                    if mapped_event in {"run.completed", "run.failed", "run.cancelled", "run.paused"}:
                        terminal_engine_event = mapped_event
                        terminal_engine_payload = payload if isinstance(payload, dict) else {}
                        terminal_engine_diagnostics = diagnostics
                        break
                    latest_run = await self.db.get(AgentRun, run_id)
                    latest_status = (
                        latest_run.status.value if hasattr(latest_run.status, "value") else str(latest_run.status)
                    ) if latest_run is not None else ""
                    if latest_run is not None and latest_status in {
                        RunStatus.completed.value,
                        RunStatus.failed.value,
                        RunStatus.cancelled.value,
                        RunStatus.paused.value,
                    }:
                        run = latest_run
                        terminal_engine_event = terminal_event_for_status(latest_status)
                        break
                    if self._is_workspace_write_tool_event(event=mapped_event, payload=payload):
                        saw_write_tool_event = True
                    if mapped_event == "assistant.delta":
                        raw_content = str((payload or {}).get("content") or "")
                        if raw_content.strip():
                            assistant_delta_events += 1
                            assistant_delta_emitted = True
                            assistant_chunks.append(raw_content)
                            if not first_token_recorded:
                                first_token_recorded = True
                                first_token_ms = self._record_timing_metric(
                                    run,
                                    phase="first_token",
                                    started_at=stream_started_at,
                                )
                                logger.info(
                                    "CODING_AGENT_TIMING run_id=%s app_id=%s phase=first_token duration_ms=%s",
                                    run.id,
                                    app.id,
                                    first_token_ms,
                                )
                                await self.db.commit()
                    yield emit(mapped_event, stage, payload, diagnostics)
            finally:
                aclose = getattr(engine_iter, "aclose", None)
                if callable(aclose):
                    try:
                        await aclose()
                    except Exception:
                        pass

            run = await self.db.get(AgentRun, run_id) or run
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if terminal_engine_event in {"run.completed", "run.failed", "run.cancelled", "run.paused"} and status not in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
                RunStatus.paused.value,
            }:
                if terminal_engine_event == "run.completed":
                    run.status = RunStatus.completed
                    run.error_message = None
                elif terminal_engine_event == "run.cancelled":
                    run.status = RunStatus.cancelled
                    run.error_message = None
                elif terminal_engine_event == "run.paused":
                    run.status = RunStatus.paused
                    run.error_message = None
                else:
                    failure_message = str(
                        (terminal_engine_diagnostics or [{}])[0].get("message")
                        or terminal_engine_payload.get("error")
                        or "run failed"
                    )
                    run.status = RunStatus.failed
                    run.error_message = failure_message
                run.completed_at = run.completed_at or datetime.now(timezone.utc)
                await self.db.commit()
                status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status == RunStatus.completed.value:
                terminal_event_ms = self._record_timing_metric(
                    run,
                    phase="terminal_event",
                    started_at=stream_started_at,
                )
                logger.info(
                    "CODING_AGENT_TIMING run_id=%s app_id=%s phase=terminal_event duration_ms=%s",
                    run.id,
                    app.id,
                    terminal_event_ms,
                )
                checkpoint_started_at = time.monotonic()
                if saw_write_tool_event:
                    revision = await self.auto_apply_and_checkpoint(run)
                    self._set_timing_metric_value(run, metric="checkpoint_skipped_no_edit_tool", value=False)
                else:
                    revision = None
                    self._set_timing_metric_value(run, metric="checkpoint_skipped_no_edit_tool", value=True)
                checkpoint_done_ms = self._record_timing_metric(
                    run,
                    phase="revision_persist",
                    started_at=checkpoint_started_at,
                )
                self._set_timing_metric_value(
                    run,
                    metric="opencode_delta_events",
                    value=assistant_delta_events,
                )
                logger.info(
                    "CODING_AGENT_TIMING run_id=%s app_id=%s phase=revision_persist duration_ms=%s",
                    run.id,
                    app.id,
                    checkpoint_done_ms,
                )
                await finalize_sandbox("stopped")
                await self.db.commit()
                if revision is not None:
                    yield emit(
                        "revision.created",
                        "revision",
                        {
                            "revision_id": str(revision.id),
                            "entry_file": revision.entry_file,
                            "file_count": len(revision.files or {}),
                        },
                    )
                    yield emit(
                        "checkpoint.created",
                        "checkpoint",
                        {
                            "checkpoint_id": str(run.checkpoint_revision_id or revision.id),
                            "revision_id": str(revision.id),
                        },
                    )
                if not assistant_delta_emitted:
                    assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                    assistant_chunks.append(assistant_text)
                    yield emit("assistant.delta", "assistant", {"content": assistant_text})
                await persist_assistant_message_for_terminal()
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.completed",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=revision is not None,
                )
                await release_run_lock()
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            if status == RunStatus.cancelled.value:
                await finalize_sandbox("stopped")
                await persist_assistant_message_for_terminal("Run cancelled.")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.cancelled",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.cancelled", "run", self.serialize_run(run))
                return

            if status == RunStatus.paused.value:
                await finalize_sandbox("stopped")
                await persist_assistant_message_for_terminal("Run paused.")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.paused",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.paused", "run", self.serialize_run(run))
                return

            failure_message = str(
                (terminal_engine_diagnostics or [{}])[0].get("message")
                or terminal_engine_payload.get("error")
                or run.error_message
                or "run failed"
            )
            if status != RunStatus.failed.value:
                run.status = RunStatus.failed
            run.error_message = failure_message
            run.completed_at = run.completed_at or datetime.now(timezone.utc)
            await self.db.commit()

            await finalize_sandbox("error")
            await persist_assistant_message_for_terminal(failure_message)
            self._append_local_telemetry_snapshot(
                app=app,
                run=run,
                terminal_event="run.failed",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
                revision_created=bool(run.result_revision_id),
            )
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": failure_message}],
            )
            await release_run_lock()
        except Exception as exc:
            failed_run = await self.db.get(AgentRun, run_id)
            if failed_run is not None:
                failed_run.status = RunStatus.failed
                failed_run.error_message = str(exc)
                failed_run.completed_at = datetime.now(timezone.utc)
                context = self._run_context(failed_run)
                context["preview_sandbox_status"] = "running"
                await release_run_lock()
                await self.db.commit()
                run = failed_run
            await persist_assistant_message_for_terminal(str(exc))
            self._append_local_telemetry_snapshot(
                app=app,
                run=run,
                terminal_event="run.failed",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
                revision_created=bool(run.result_revision_id),
            )
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": str(exc)}],
            )
        finally:
            # Guard against lock leaks on cancellation/disconnect paths where terminal
            # status has already been persisted but event streaming is interrupted.
            try:
                latest_run = await self.db.get(AgentRun, run_id)
                if latest_run is not None:
                    latest_status = latest_run.status.value if hasattr(latest_run.status, "value") else str(latest_run.status)
                    if latest_status in {
                        RunStatus.completed.value,
                        RunStatus.failed.value,
                        RunStatus.cancelled.value,
                        RunStatus.paused.value,
                    }:
                        await self._clear_preview_run_lock(
                            app_id=latest_run.published_app_id,
                            actor_id=latest_run.initiator_user_id or latest_run.user_id,
                            run_id=latest_run.id,
                        )
                        await self.db.commit()
            except Exception:
                pass
