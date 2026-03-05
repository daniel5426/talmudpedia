from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID

from sqlalchemy import select

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_agent_engines.base import EngineRunContext
from app.services.published_app_coding_pipeline_trace import pipeline_trace
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE

_TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.paused"}
_TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
    RunStatus.paused.value,
}


class PublishedAppCodingAgentRuntimeStreamingMixin:
    _HISTORY_TOOL_EVENTS_MAX = 300

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
        return {
            "event": event,
            "run_id": str(run_id),
            "app_id": str(app_id),
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "payload": payload or {},
            "diagnostics": diagnostics or [],
        }

    @staticmethod
    def _coerce_assistant_text(value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                nested = PublishedAppCodingAgentRuntimeStreamingMixin._coerce_assistant_text(item)
                if nested:
                    parts.append(nested)
            joined = " ".join(parts).strip()
            return joined or None
        if isinstance(value, dict):
            for key in ("content", "message", "text", "summary"):
                nested = PublishedAppCodingAgentRuntimeStreamingMixin._coerce_assistant_text(value.get(key))
                if nested:
                    return nested
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

    @staticmethod
    def _is_generic_failure_message(message: str | None) -> bool:
        normalized = str(message or "").strip().lower()
        return normalized in {"", "run failed", "runtime error", "error", "failed"}

    def _compose_failure_message(
        self,
        *,
        run: AgentRun,
        diagnostics: list[dict[str, Any]] | None = None,
        payload: dict[str, Any] | None = None,
        fallback: str | None = None,
    ) -> str:
        diagnostic_message = ""
        if isinstance(diagnostics, list) and diagnostics:
            first = diagnostics[0] if isinstance(diagnostics[0], dict) else {}
            diagnostic_message = str(first.get("message") or "").strip()
        payload_message = str((payload or {}).get("error") or "").strip()
        run_message = str(run.error_message or "").strip()
        fallback_message = str(fallback or "").strip()

        for candidate in (diagnostic_message, payload_message, run_message, fallback_message):
            if candidate and not self._is_generic_failure_message(candidate):
                return candidate
        for candidate in (diagnostic_message, payload_message, run_message, fallback_message):
            if candidate:
                return candidate
        return "Coding-agent OpenCode engine ended without a terminal status."

    @staticmethod
    def _exception_message(exc: Exception) -> str:
        rendered = str(exc or "").strip()
        if rendered and rendered.lower() not in {"run failed", "error", "failed"}:
            return rendered
        class_name = exc.__class__.__name__ if exc is not None else "RuntimeError"
        if rendered:
            return f"{class_name}: {rendered}"
        return class_name

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

    async def _persist_tool_event_for_history(
        self,
        *,
        run: AgentRun,
        event: str,
        stage: str,
        payload: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> None:
        if event not in {"tool.started", "tool.completed", "tool.failed"}:
            return
        # Refresh with row lock to prevent lost updates when multiple run monitors/sessions
        # append tool history concurrently for the same run.
        persisted_row = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.id == run.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        persisted = persisted_row.scalar_one_or_none() or run
        output_result = dict(persisted.output_result) if isinstance(persisted.output_result, dict) else {}
        raw_events = output_result.get("tool_events")
        events = list(raw_events) if isinstance(raw_events, list) else []
        events.append(
            {
                "event": event,
                "stage": str(stage or "tool"),
                "payload": dict(payload or {}),
                "diagnostics": list(diagnostics or []),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        if len(events) > self._HISTORY_TOOL_EVENTS_MAX:
            events = events[-self._HISTORY_TOOL_EVENTS_MAX :]
        output_result["tool_events"] = events
        persisted.output_result = output_result
        await self.db.commit()

    async def stream_run_events(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = run.id
        trace_base = {
            "run_id": str(run_id),
            "app_id": str(app.id),
        }

        def trace_stream(event: str, **fields: Any) -> None:
            pipeline_trace(event, pipeline="runtime_stream", **trace_base, **fields)

        def summarize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
            if not isinstance(payload, dict):
                return {}
            summary: dict[str, Any] = {"payload_keys": sorted(payload.keys())[:24]}
            tool = str(payload.get("tool") or "").strip()
            span_id = str(payload.get("span_id") or "").strip()
            status = str(payload.get("status") or "").strip()
            error = str(payload.get("error") or "").strip()
            if tool:
                summary["tool"] = tool
            if span_id:
                summary["span_id"] = span_id
            if status:
                summary["status"] = status
            if error:
                summary["error"] = error[:400]
            return summary

        trace_stream(
            "runtime_stream.opened",
            status=(run.status.value if hasattr(run.status, "value") else str(run.status)),
            chat_session_id=str(self._extract_chat_session_id(run) or "") or None,
        )
        persistent_run = await self.db.get(AgentRun, run_id)
        if persistent_run is not None:
            run = persistent_run

        seq = 1
        assistant_chunks: list[str] = []
        assistant_delta_events = 0
        assistant_message_persisted = False
        saw_write_tool_event = False
        write_flag_persisted = False

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

        async def persist_workspace_write_flag() -> None:
            nonlocal write_flag_persisted, run
            if write_flag_persisted:
                return
            persisted = await self.db.get(AgentRun, run_id) or run
            if not bool(getattr(persisted, "has_workspace_writes", False)):
                persisted.has_workspace_writes = True
                await self.db.commit()
            run = persisted
            write_flag_persisted = True

        yield emit(
            "run.accepted",
            "run",
            {
                "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                "surface": CODING_AGENT_SURFACE,
            },
        )
        yield emit("plan.updated", "plan", {"summary": "Coding-agent run started"})

        terminal_status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if terminal_status in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
            RunStatus.paused.value,
        }:
            trace_stream(
                "runtime_stream.already_terminal",
                terminal_status=terminal_status,
            )
            if terminal_status == RunStatus.completed.value:
                assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                if assistant_text:
                    assistant_chunks.append(assistant_text)
                    yield emit("assistant.delta", "assistant", {"content": assistant_text})
                    assistant_delta_events += 1
                await persist_assistant_message_for_terminal(assistant_text)
                await release_run_lock()
                trace_stream("runtime_stream.closed", terminal_event="run.completed")
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            if terminal_status == RunStatus.cancelled.value:
                await persist_assistant_message_for_terminal("Run cancelled.")
                await release_run_lock()
                trace_stream("runtime_stream.closed", terminal_event="run.cancelled")
                yield emit("run.cancelled", "run", self.serialize_run(run))
                return

            if terminal_status == RunStatus.paused.value:
                await persist_assistant_message_for_terminal("Run paused.")
                await release_run_lock()
                trace_stream("runtime_stream.closed", terminal_event="run.paused")
                yield emit("run.paused", "run", self.serialize_run(run))
                return

            failure_message = self._compose_failure_message(run=run, fallback="run failed")
            await persist_assistant_message_for_terminal(failure_message)
            await release_run_lock()
            trace_stream("runtime_stream.closed", terminal_event="run.failed", error=failure_message)
            yield emit("run.failed", "run", self.serialize_run(run), [{"message": failure_message}])
            return

        sandbox_id, sandbox_error = await self._recover_or_bootstrap_run_sandbox_context(run=run, app=app)
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
            trace_stream(
                "runtime_stream.closed",
                terminal_event="run.failed",
                error=run.error_message,
                error_code="CODING_AGENT_SANDBOX_REQUIRED",
            )
            return

        terminal_engine_event: str | None = None
        terminal_engine_payload: dict[str, Any] = {}
        terminal_engine_diagnostics: list[dict[str, Any]] | None = None

        try:
            engine = self._resolve_engine_for_run(run)
            async for raw_event in engine.stream(
                EngineRunContext(
                    app=app,
                    run=run,
                )
            ):
                mapped_event = str(raw_event.event or "")
                stage = str(raw_event.stage or "run")
                payload = dict(raw_event.payload or {})
                diagnostics = list(raw_event.diagnostics or [])

                if mapped_event == "assistant.delta":
                    content = str(payload.get("content") or "")
                    if content:
                        assistant_chunks.append(content)
                        assistant_delta_events += 1
                        yield emit("assistant.delta", "assistant", {"content": content})
                    continue

                trace_stream(
                    "runtime_stream.engine_event",
                    mapped_event=mapped_event,
                    stage=stage,
                    **summarize_payload(payload),
                )

                if mapped_event in _TERMINAL_EVENTS:
                    terminal_engine_event = mapped_event
                    terminal_engine_payload = payload
                    terminal_engine_diagnostics = diagnostics
                    trace_stream(
                        "runtime_stream.engine_terminal_observed",
                        mapped_event=mapped_event,
                        diagnostics_count=len(diagnostics),
                        **summarize_payload(payload),
                    )
                    break

                if self._is_workspace_write_tool_event(event=mapped_event, payload=payload):
                    saw_write_tool_event = True
                    await persist_workspace_write_flag()
                if mapped_event in {"tool.started", "tool.completed", "tool.failed"}:
                    await self._persist_tool_event_for_history(
                        run=run,
                        event=mapped_event,
                        stage=stage,
                        payload=payload,
                        diagnostics=diagnostics,
                    )
                yield emit(mapped_event, stage, payload, diagnostics)

            run = await self.db.get(AgentRun, run_id) or run
            status = run.status.value if hasattr(run.status, "value") else str(run.status)

            if terminal_engine_event in _TERMINAL_EVENTS and status not in _TERMINAL_RUN_STATUSES:
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
                    run.status = RunStatus.failed
                    run.error_message = self._compose_failure_message(
                        run=run,
                        diagnostics=terminal_engine_diagnostics,
                        payload=terminal_engine_payload,
                        fallback="run failed",
                    )
                run.completed_at = run.completed_at or datetime.now(timezone.utc)
                await self.db.commit()
                status = run.status.value if hasattr(run.status, "value") else str(run.status)
                trace_stream(
                    "runtime_stream.terminal_status_persisted",
                    status=status,
                    mapped_terminal_event=terminal_engine_event,
                )

            if status not in _TERMINAL_RUN_STATUSES:
                trace_stream(
                    "runtime_stream.missing_terminal_nonfatal",
                    status=status,
                    mapped_terminal_event=terminal_engine_event,
                )
                return

            if status == RunStatus.completed.value:
                await finalize_sandbox("stopped")
                await self.db.commit()

                if assistant_delta_events == 0:
                    assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                    if assistant_text:
                        assistant_chunks.append(assistant_text)
                        yield emit("assistant.delta", "assistant", {"content": assistant_text})
                        assistant_delta_events += 1

                await persist_assistant_message_for_terminal()
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.completed",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                trace_stream(
                    "runtime_stream.closed",
                    terminal_event="run.completed",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                )
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
                trace_stream(
                    "runtime_stream.closed",
                    terminal_event="run.cancelled",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                )
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
                trace_stream(
                    "runtime_stream.closed",
                    terminal_event="run.paused",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                )
                yield emit("run.paused", "run", self.serialize_run(run))
                return

            failure_message = self._compose_failure_message(
                run=run,
                diagnostics=terminal_engine_diagnostics,
                payload=terminal_engine_payload,
                fallback="run failed",
            )
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
            await release_run_lock()
            trace_stream(
                "runtime_stream.closed",
                terminal_event="run.failed",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
                error=failure_message,
            )
            yield emit("run.failed", "run", self.serialize_run(run), [{"message": failure_message}])
        except Exception as exc:
            error_message = self._exception_message(exc)
            failed_run = await self.db.get(AgentRun, run_id)
            if failed_run is not None:
                failed_run.status = RunStatus.failed
                failed_run.error_message = error_message
                failed_run.completed_at = datetime.now(timezone.utc)
                context = self._run_context(failed_run)
                context["preview_sandbox_status"] = "running"
                await release_run_lock()
                await self.db.commit()
                run = failed_run

            await persist_assistant_message_for_terminal(error_message)
            self._append_local_telemetry_snapshot(
                app=app,
                run=run,
                terminal_event="run.failed",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
                revision_created=bool(run.result_revision_id),
            )
            trace_stream(
                "runtime_stream.exception",
                error=error_message,
                error_type=exc.__class__.__name__ if exc is not None else "Exception",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
            )
            yield emit("run.failed", "run", self.serialize_run(run), [{"message": error_message}])
        finally:
            # Guard against lock leaks on disconnect paths.
            try:
                latest_run = await self.db.get(AgentRun, run_id)
                if latest_run is not None:
                    latest_status = latest_run.status.value if hasattr(latest_run.status, "value") else str(latest_run.status)
                    if latest_status in _TERMINAL_RUN_STATUSES:
                        await self._clear_preview_run_lock(
                            app_id=latest_run.published_app_id,
                            actor_id=latest_run.initiator_user_id or latest_run.user_id,
                            run_id=latest_run.id,
                        )
                        await self.db.commit()
            except Exception:
                pass
            trace_stream("runtime_stream.finally")
