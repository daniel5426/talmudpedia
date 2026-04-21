from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, AsyncGenerator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedAppCodingChatSession
from app.services.published_app_coding_pipeline_trace import pipeline_trace
from app.services.opencode_server_client import OpenCodeServerClient

from .base import EngineCancelResult, EngineRunContext, EngineStreamEvent
from .prompt_history import build_opencode_effective_prompt


logger = logging.getLogger(__name__)

RECOVERY_EDIT_TOOL_HINTS = (
    "write",
    "edit",
    "replace",
    "insert",
    "append",
    "prepend",
    "rename",
    "move",
    "delete",
    "remove",
    "mkdir",
    "touch",
    "create",
    "mv",
    "rm",
    "cp",
)


class OpenCodePublishedAppCodingAgentEngine:
    def __init__(
        self,
        *,
        db: AsyncSession,
        client: OpenCodeServerClient,
    ):
        self._db = db
        self._client = client

    @staticmethod
    def _recovery_messages(context: dict[str, Any]) -> list[dict[str, str]]:
        raw = context.get("opencode_recovery_messages")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    @staticmethod
    def _chat_session_uuid(context: dict[str, Any]) -> UUID | None:
        raw = str(context.get("chat_session_id") or "").strip()
        if not raw:
            return None
        try:
            return UUID(raw)
        except Exception:
            return None

    @staticmethod
    def _is_invalid_session_error(exc: Exception) -> bool:
        message = str(exc or "").strip().lower()
        return any(
            token in message
            for token in (
                "session not found",
                "invalid session",
                "unknown session",
                "missing session",
                "session does not exist",
            )
        )

    async def _recreate_persistent_session(
        self,
        *,
        run: AgentRun,
        app_id: str,
        context: dict[str, Any],
        sandbox_id: str,
        workspace_path: str,
        model_id: str,
    ) -> str:
        session_id = await self._client.create_session(
            run_id=str(run.id),
            app_id=app_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            model_id=model_id,
            selected_agent_contract=(
                dict(context.get("selected_agent_contract"))
                if isinstance(context.get("selected_agent_contract"), dict)
                else None
            ),
        )
        chat_session_id = self._chat_session_uuid(context)
        if chat_session_id is not None:
            chat_session = await self._db.get(PublishedAppCodingChatSession, chat_session_id)
            if chat_session is not None:
                chat_session.opencode_session_id = session_id
                chat_session.opencode_sandbox_id = sandbox_id or None
                chat_session.opencode_workspace_path = workspace_path or None
                chat_session.opencode_session_opened_at = datetime.now(timezone.utc)
                chat_session.opencode_session_closed_at = None
        context["opencode_session_id"] = session_id
        context["opencode_sandbox_id"] = sandbox_id or None
        context["opencode_workspace_path"] = workspace_path or None
        await self._db.commit()
        return session_id

    async def stream(self, ctx: EngineRunContext) -> AsyncGenerator[EngineStreamEvent, None]:
        run = ctx.run
        trace_base = {
            "run_id": str(run.id),
            "app_id": str(ctx.app.id),
        }

        def trace_engine(event: str, **fields: Any) -> None:
            pipeline_trace(event, pipeline="opencode_engine", **trace_base, **fields)

        input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
        raw_context = input_params.get("context")
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        input_params["context"] = context
        run.input_params = input_params
        prompt = str(input_params.get("input") or "").strip()
        resolved_model_id = str(context.get("resolved_model_id") or "").strip()
        opencode_model_id = str(context.get("opencode_model_id") or "").strip()
        opencode_session_id = str(context.get("opencode_session_id") or "").strip()
        workspace_path = str(
            context.get("opencode_workspace_path")
            or context.get("preview_workspace_live_path")
            or ""
        ).strip()
        live_workspace_path = str(context.get("preview_workspace_live_path") or "").strip()
        if not workspace_path:
            trace_engine("engine.stream.invalid_workspace", reason="missing_workspace_path")
            raise RuntimeError("OpenCode run requires a workspace path.")
        sandbox_id = str(
            context.get("opencode_sandbox_id")
            or context.get("preview_sandbox_id")
            or ""
        ).strip()
        workspace_root = os.path.realpath(os.path.abspath(workspace_path)) if workspace_path else ""
        recovery_messages = self._recovery_messages(context)
        if recovery_messages:
            prompt_history_budget_chars = int(
                os.getenv("APPS_CODING_AGENT_OPENCODE_PROMPT_HISTORY_BUDGET_CHARS", "14000")
            )
            recovery_messages = [
                {
                    "role": str(item.get("role") or "").strip(),
                    "content": str(item.get("content") or "").strip(),
                }
                for item in recovery_messages
                if isinstance(item, dict) and str(item.get("content") or "").strip()
            ]
            effective_prompt = build_opencode_effective_prompt(
                current_user_prompt=prompt,
                messages=recovery_messages,
                max_chars=prompt_history_budget_chars,
            )
        else:
            effective_prompt = prompt

        if not run.engine_run_ref:
            opencode_submit_started_at = time.monotonic()
            trace_engine(
                "engine.stream.turn_submit_requested",
                session_id=opencode_session_id or None,
                sandbox_id=sandbox_id or None,
                workspace_path=workspace_path,
                model_id=opencode_model_id or resolved_model_id,
            )
            if not opencode_session_id:
                opencode_session_id = await self._recreate_persistent_session(
                    run=run,
                    app_id=str(ctx.app.id),
                    context=context,
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=opencode_model_id or resolved_model_id,
                )
            try:
                run.engine_run_ref = await self._client.submit_turn(
                    session_id=opencode_session_id,
                    run_id=str(run.id),
                    app_id=str(ctx.app.id),
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=opencode_model_id or resolved_model_id,
                    prompt=effective_prompt,
                    recovery_messages=recovery_messages if recovery_messages else None,
                    selected_agent_contract=(
                        dict(context.get("selected_agent_contract"))
                        if isinstance(context.get("selected_agent_contract"), dict)
                        else None
                    ),
                    defer_until_stream=True,
                )
            except Exception as exc:
                if not self._is_invalid_session_error(exc):
                    raise
                trace_engine(
                    "engine.stream.session_recreate_after_submit_error",
                    session_id=opencode_session_id or None,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                opencode_session_id = await self._recreate_persistent_session(
                    run=run,
                    app_id=str(ctx.app.id),
                    context=context,
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=opencode_model_id or resolved_model_id,
                )
                run.engine_run_ref = await self._client.submit_turn(
                    session_id=opencode_session_id,
                    run_id=str(run.id),
                    app_id=str(ctx.app.id),
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=opencode_model_id or resolved_model_id,
                    prompt=effective_prompt,
                    recovery_messages=recovery_messages if recovery_messages else None,
                    selected_agent_contract=(
                        dict(context.get("selected_agent_contract"))
                        if isinstance(context.get("selected_agent_contract"), dict)
                        else None
                    ),
                    defer_until_stream=True,
                )
            opencode_turn_submit_ms = max(0, int((time.monotonic() - opencode_submit_started_at) * 1000))
            timings = context.get("timing_metrics_ms")
            if not isinstance(timings, dict):
                timings = {}
                context["timing_metrics_ms"] = timings
            timings["opencode_turn_submit"] = opencode_turn_submit_ms
            logger.info(
                "CODING_AGENT_TIMING run_id=%s app_id=%s phase=opencode_turn_submit duration_ms=%s",
                run.id,
                ctx.app.id,
                opencode_turn_submit_ms,
            )
            trace_engine(
                "engine.stream.turn_submit_confirmed",
                session_id=opencode_session_id or None,
                engine_run_ref=str(run.engine_run_ref or ""),
                opencode_turn_submit_ms=opencode_turn_submit_ms,
            )

        run.status = RunStatus.running
        if not run.started_at:
            run.started_at = datetime.now(timezone.utc)
        run.error_message = None
        await self._db.commit()

        saw_terminal = False
        saw_failure = False
        saw_cancelled = False
        saw_paused = False
        failure_message = "OpenCode run failed"
        saw_apply_patch_failure = False
        saw_apply_patch_success = False
        saw_recovery_edit_success = False
        fail_on_unrecovered_apply_patch = str(
            os.getenv("APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        tool_event_mode = str(
            os.getenv("APPS_CODING_AGENT_OPENCODE_TOOL_EVENT_MODE", "raw")
        ).strip().lower()
        if tool_event_mode not in {"raw", "normalized"}:
            tool_event_mode = "raw"

        emitted_raw_events = False

        async def _raw_event_stream():
            nonlocal emitted_raw_events, opencode_session_id
            try:
                async for item in self._client.stream_turn_events(
                    session_id=opencode_session_id,
                    turn_ref=str(run.engine_run_ref),
                    sandbox_id=sandbox_id or None,
                    workspace_path=workspace_path,
                ):
                    emitted_raw_events = True
                    yield item
            except Exception as exc:
                if emitted_raw_events or not self._is_invalid_session_error(exc):
                    raise
                trace_engine(
                    "engine.stream.session_recreate_after_stream_error",
                    session_id=opencode_session_id or None,
                    turn_ref=str(run.engine_run_ref or "") or None,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                recreated_session_id = await self._recreate_persistent_session(
                    run=run,
                    app_id=str(ctx.app.id),
                    context=context,
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=opencode_model_id or resolved_model_id,
                )
                opencode_session_id = recreated_session_id
                context["opencode_recovery_messages"] = recovery_messages
                run.engine_run_ref = await self._client.submit_turn(
                    session_id=recreated_session_id,
                    run_id=str(run.id),
                    app_id=str(ctx.app.id),
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=opencode_model_id or resolved_model_id,
                    prompt=effective_prompt,
                    recovery_messages=recovery_messages if recovery_messages else None,
                    selected_agent_contract=(
                        dict(context.get("selected_agent_contract"))
                        if isinstance(context.get("selected_agent_contract"), dict)
                        else None
                    ),
                    defer_until_stream=True,
                )
                async for item in self._client.stream_turn_events(
                    session_id=recreated_session_id,
                    turn_ref=str(run.engine_run_ref),
                    sandbox_id=sandbox_id or None,
                    workspace_path=workspace_path,
                ):
                    yield item

        async for raw in _raw_event_stream():
            mapped = self._translate_event(raw, tool_event_mode=tool_event_mode)
            if mapped is None:
                continue
            if mapped.event != "assistant.delta":
                payload = mapped.payload if isinstance(mapped.payload, dict) else {}
                trace_engine(
                    "engine.stream.event",
                    mapped_event=mapped.event,
                    stage=mapped.stage,
                    tool=str(payload.get("tool") or "").strip() or None,
                    span_id=str(payload.get("span_id") or "").strip() or None,
                    diagnostics_count=len(mapped.diagnostics or []),
                )
            if mapped.event == "tool.failed" and self._is_apply_patch_tool(mapped.payload):
                saw_apply_patch_failure = True
                trace_engine("engine.stream.apply_patch_failed")
            elif mapped.event == "tool.completed":
                if self._is_apply_patch_tool(mapped.payload) and self._tool_output_has_error(mapped.payload):
                    saw_apply_patch_failure = True
                    trace_engine("engine.stream.apply_patch_failed")
                if self._is_successful_apply_patch(mapped.payload):
                    saw_apply_patch_success = True
                    saw_recovery_edit_success = True
                    trace_engine("engine.stream.apply_patch_succeeded")
                elif self._is_recovery_edit_tool(mapped.payload):
                    saw_recovery_edit_success = True
                    trace_engine("engine.stream.recovery_edit_succeeded")
            workspace_violations = self._extract_workspace_violations(
                payload=mapped.payload or {},
                workspace_root=workspace_root,
            )
            if workspace_violations:
                saw_terminal = True
                saw_failure = True
                failure_message = (
                    "Security violation: tool emitted path outside run workspace root "
                    f"({', '.join(workspace_violations[:3])})"
                )
                logger.error(
                    "AUDIT_SANDBOX_PATH_VIOLATION organization_id=%s run_id=%s app_id=%s sandbox_id=%s workspace_root=%s violations=%s",
                    run.organization_id,
                    run.id,
                    ctx.app.id,
                    sandbox_id,
                    workspace_root,
                    workspace_violations,
                )
                trace_engine(
                    "engine.stream.workspace_violation",
                    sandbox_id=sandbox_id or None,
                    workspace_root=workspace_root,
                    violation_count=len(workspace_violations),
                    violations=workspace_violations[:10],
                )
                try:
                    if run.engine_run_ref:
                        await self._client.cancel_turn(
                            session_id=opencode_session_id,
                            turn_ref=str(run.engine_run_ref),
                            sandbox_id=sandbox_id or None,
                            workspace_path=workspace_path,
                        )
                except Exception:
                    pass
                yield EngineStreamEvent(
                    event="run.failed",
                    stage="run",
                    payload={"error": failure_message},
                    diagnostics=[
                        {
                            "code": "CODING_AGENT_SANDBOX_PATH_VIOLATION",
                            "message": failure_message,
                            "paths": workspace_violations[:10],
                        }
                    ],
                )
                break
            if mapped.event == "run.completed":
                saw_terminal = True
                break
            if mapped.event == "run.cancelled":
                saw_terminal = True
                saw_cancelled = True
                break
            if mapped.event == "run.paused":
                saw_terminal = True
                saw_paused = True
                break
            if mapped.event == "run.failed":
                saw_terminal = True
                saw_failure = True
                if mapped.diagnostics:
                    failure_message = str(mapped.diagnostics[0].get("message") or failure_message)
                else:
                    failure_message = str((mapped.payload or {}).get("error") or failure_message)
                break
            yield mapped

        persisted = await self._db.get(AgentRun, run.id) or run
        if (
            fail_on_unrecovered_apply_patch
            and saw_terminal
            and not saw_failure
            and not saw_cancelled
            and not saw_paused
            and saw_apply_patch_failure
            and not saw_apply_patch_success
            and not saw_recovery_edit_success
        ):
            saw_failure = True
            failure_message = (
                "OpenCode run completed after apply_patch failures without a successful follow-up edit."
            )
            trace_engine("engine.stream.force_failed_unrecovered_apply_patch")
        if saw_terminal:
            if not saw_failure:
                if saw_cancelled:
                    persisted.status = RunStatus.cancelled
                elif saw_paused:
                    persisted.status = RunStatus.paused
                else:
                    persisted.status = RunStatus.completed
                persisted.error_message = None
            else:
                persisted.error_message = failure_message
                persisted.status = RunStatus.failed
            persisted.completed_at = datetime.now(timezone.utc)
            await self._db.commit()
            trace_engine(
                "engine.stream.closed",
                status=(
                    persisted.status.value
                    if hasattr(persisted.status, "value")
                    else str(persisted.status)
                ),
                saw_terminal=saw_terminal,
                saw_failure=saw_failure,
                saw_cancelled=saw_cancelled,
                saw_paused=saw_paused,
                saw_apply_patch_failure=saw_apply_patch_failure,
                saw_apply_patch_success=saw_apply_patch_success,
                saw_recovery_edit_success=saw_recovery_edit_success,
                error=str(persisted.error_message or "") or None,
            )
            return

        trace_engine(
            "engine.stream.closed_nonterminal",
            status=(
                persisted.status.value
                if hasattr(persisted.status, "value")
                else str(persisted.status)
            ),
            saw_terminal=saw_terminal,
            saw_failure=saw_failure,
            saw_apply_patch_failure=saw_apply_patch_failure,
            saw_apply_patch_success=saw_apply_patch_success,
            saw_recovery_edit_success=saw_recovery_edit_success,
        )
        return

    async def cancel(self, run: AgentRun) -> EngineCancelResult:
        if not run.engine_run_ref:
            pipeline_trace(
                "engine.cancel.unconfirmed_missing_run_ref",
                pipeline="opencode_engine",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
            )
            return EngineCancelResult(
                confirmed=False,
                diagnostics=[{"code": "OPENCODE_CANCEL_UNCONFIRMED", "message": "Missing OpenCode run reference"}],
            )
        input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
        raw_context = input_params.get("context")
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        session_id = str(context.get("opencode_session_id") or "").strip() or None
        sandbox_id = str(context.get("opencode_sandbox_id") or context.get("preview_sandbox_id") or "").strip() or None
        if not session_id:
            return EngineCancelResult(
                confirmed=False,
                diagnostics=[{"code": "OPENCODE_CANCEL_UNCONFIRMED", "message": "Missing OpenCode session id"}],
            )
        try:
            confirmed = await self._client.cancel_turn(
                session_id=session_id,
                turn_ref=str(run.engine_run_ref),
                sandbox_id=sandbox_id,
                workspace_path=str(context.get("opencode_workspace_path") or context.get("preview_workspace_live_path") or "") or None,
            )
        except Exception as exc:
            pipeline_trace(
                "engine.cancel.failed",
                pipeline="opencode_engine",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            return EngineCancelResult(
                confirmed=False,
                diagnostics=[
                    {
                        "code": "OPENCODE_CANCEL_UNCONFIRMED",
                        "message": f"OpenCode cancellation request failed: {exc}",
                    }
                ],
            )
        if confirmed:
            pipeline_trace(
                "engine.cancel.confirmed",
                pipeline="opencode_engine",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
            )
            return EngineCancelResult(confirmed=True, diagnostics=[])
        pipeline_trace(
            "engine.cancel.unconfirmed",
            pipeline="opencode_engine",
            run_id=str(run.id),
            app_id=str(run.published_app_id) if run.published_app_id else None,
        )
        return EngineCancelResult(
            confirmed=False,
            diagnostics=[{"code": "OPENCODE_CANCEL_UNCONFIRMED", "message": "OpenCode cancellation not confirmed"}],
        )

    async def answer_question(self, *, run: AgentRun, question_id: str, answers: list[list[str]]) -> None:
        if not run.engine_run_ref:
            pipeline_trace(
                "engine.answer_question.missing_run_ref",
                pipeline="opencode_engine",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
                question_id=str(question_id or "") or None,
            )
            raise RuntimeError("Missing OpenCode run reference for question response")
        input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
        raw_context = input_params.get("context")
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        session_id = str(context.get("opencode_session_id") or "").strip()
        if not session_id:
            raise RuntimeError("Missing OpenCode session id for question response")
        sandbox_id = str(context.get("opencode_sandbox_id") or context.get("preview_sandbox_id") or "").strip() or None
        await self._client.answer_question(
            session_id=session_id,
            turn_ref=str(run.engine_run_ref),
            question_id=str(question_id or "").strip(),
            answers=answers,
            sandbox_id=sandbox_id,
            workspace_path=str(context.get("opencode_workspace_path") or context.get("preview_workspace_live_path") or "") or None,
        )
        pipeline_trace(
            "engine.answer_question.sent",
            pipeline="opencode_engine",
            run_id=str(run.id),
            app_id=str(run.published_app_id) if run.published_app_id else None,
            question_id=str(question_id or "") or None,
            answer_groups=len(answers or []),
        )

    @classmethod
    def _extract_workspace_violations(cls, *, payload: dict[str, Any], workspace_root: str) -> list[str]:
        if not workspace_root:
            return []
        candidates = cls._collect_path_candidates(payload)
        violations: list[str] = []
        for candidate in candidates:
            if not cls._path_within_workspace(candidate, workspace_root):
                violations.append(candidate)
        return violations

    @classmethod
    def _collect_path_candidates(cls, value: Any, *, key_hint: str = "") -> list[str]:
        candidates: list[str] = []
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key or "").strip().lower()
                if isinstance(nested, str) and cls._looks_like_path_key(key_text):
                    token = nested.strip()
                    if token:
                        candidates.append(token)
                candidates.extend(cls._collect_path_candidates(nested, key_hint=key_text))
            return candidates
        if isinstance(value, list):
            for item in value:
                candidates.extend(cls._collect_path_candidates(item, key_hint=key_hint))
            return candidates
        if isinstance(value, str) and cls._looks_like_path_key(key_hint):
            token = value.strip()
            if token:
                candidates.append(token)
        return candidates

    @staticmethod
    def _looks_like_path_key(key: str) -> bool:
        return key in {
            "path",
            "file",
            "filepath",
            "file_path",
            "from_path",
            "to_path",
            "target_path",
            "workspace_path",
        }

    @staticmethod
    def _path_within_workspace(path_value: str, workspace_root: str) -> bool:
        candidate = str(path_value or "").strip()
        if not candidate:
            return True
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return True
        if not os.path.isabs(candidate):
            resolved = os.path.realpath(os.path.abspath(os.path.join(workspace_root, candidate)))
        else:
            resolved = os.path.realpath(os.path.abspath(candidate))
        root = os.path.realpath(os.path.abspath(workspace_root))
        try:
            common = os.path.commonpath([root, resolved])
        except Exception:
            return False
        return common == root

    @staticmethod
    def _is_apply_patch_tool(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        tool_name = str(payload.get("tool") or "").strip().lower()
        return "apply_patch" in tool_name

    @classmethod
    def _is_successful_apply_patch(cls, payload: dict[str, Any] | None) -> bool:
        if not cls._is_apply_patch_tool(payload):
            return False
        output = payload.get("output") if isinstance(payload, dict) else None
        if output is None:
            return True
        if not isinstance(output, dict):
            return True
        if output.get("error"):
            return False
        if output.get("ok") is False:
            return False
        result_payload = output.get("result") if isinstance(output.get("result"), dict) else {}
        if result_payload.get("ok") is False:
            return False
        return True

    @staticmethod
    def _tool_output_has_error(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        output = payload.get("output")
        if not isinstance(output, dict):
            return False
        if output.get("error"):
            return True
        if output.get("ok") is False:
            return True
        result_payload = output.get("result")
        if isinstance(result_payload, dict) and result_payload.get("ok") is False:
            return True
        return False

    @classmethod
    def _is_recovery_edit_tool(cls, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        tool_name = str(payload.get("tool") or "").strip().lower()
        if not tool_name:
            return False
        if cls._is_apply_patch_tool(payload):
            return False
        return any(hint in tool_name for hint in RECOVERY_EDIT_TOOL_HINTS)

    @staticmethod
    def _translate_event(raw: dict[str, Any], *, tool_event_mode: str = "raw") -> EngineStreamEvent | None:
        event_type = str(raw.get("event") or raw.get("type") or "").strip().lower()
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}

        if event_type == "assistant.delta":
            content = payload.get("content") if isinstance(payload, dict) else None
            if content is None:
                content = raw.get("content")
            return EngineStreamEvent(
                event="assistant.delta",
                stage="assistant",
                payload={"content": str(content or "")},
                diagnostics=None,
            )

        if event_type == "tool.started":
            tool_name = raw.get("tool") or payload.get("tool") or raw.get("name")
            return EngineStreamEvent(
                event="tool.started",
                stage="tool",
                payload={
                    "tool": str(tool_name or ""),
                    "span_id": raw.get("span_id") or payload.get("span_id"),
                    "input": payload.get("input") or raw.get("input"),
                },
                diagnostics=None,
            )

        if event_type == "tool.completed":
            tool_name = raw.get("tool") or payload.get("tool") or raw.get("name")
            output = payload.get("output") if isinstance(payload, dict) else raw.get("output")
            if isinstance(output, dict) and output.get("error"):
                diagnostics: list[dict[str, Any]] = [{"message": str(output.get("error"))}]
                if output.get("code"):
                    diagnostics[0]["code"] = str(output.get("code"))
                if tool_event_mode == "normalized":
                    return EngineStreamEvent(
                        event="tool.failed",
                        stage="tool",
                        payload={
                            "tool": str(tool_name or ""),
                            "span_id": raw.get("span_id") or payload.get("span_id"),
                            "output": output,
                        },
                        diagnostics=diagnostics,
                    )
                return EngineStreamEvent(
                    event="tool.completed",
                    stage="tool",
                    payload={
                        "tool": str(tool_name or ""),
                        "span_id": raw.get("span_id") or payload.get("span_id"),
                        "output": output,
                    },
                    diagnostics=diagnostics,
                )
            return EngineStreamEvent(
                event="tool.completed",
                stage="tool",
                payload={
                    "tool": str(tool_name or ""),
                    "span_id": raw.get("span_id") or payload.get("span_id"),
                    "output": output,
                },
                diagnostics=None,
            )

        if event_type == "tool.failed":
            tool_name = raw.get("tool") or payload.get("tool") or raw.get("name")
            message = (
                payload.get("error")
                or payload.get("message")
                or payload.get("reason")
                or raw.get("error")
                or raw.get("message")
                or "Tool failed"
            )
            diagnostics = [{"message": str(message)}]
            code = payload.get("code") or raw.get("code")
            if code:
                diagnostics[0]["code"] = str(code)
            return EngineStreamEvent(
                event="tool.failed",
                stage="tool",
                payload={
                    "tool": str(tool_name or ""),
                    "span_id": raw.get("span_id") or payload.get("span_id"),
                    "output": payload.get("output") or raw.get("output"),
                },
                diagnostics=diagnostics,
            )

        if event_type == "tool.question":
            request_id = str(payload.get("request_id") or raw.get("request_id") or "").strip()
            questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
            tool_payload = payload.get("tool") if isinstance(payload.get("tool"), dict) else {}
            if not request_id:
                return None
            return EngineStreamEvent(
                event="tool.question",
                stage="tool",
                payload={
                    "request_id": request_id,
                    "questions": [item for item in questions if isinstance(item, dict)],
                    "tool": dict(tool_payload),
                },
                diagnostics=None,
            )

        if event_type in {"tool.question.answered", "tool.question.rejected"}:
            request_id = str(payload.get("request_id") or raw.get("request_id") or "").strip()
            answers = payload.get("answers") if isinstance(payload.get("answers"), list) else []
            return EngineStreamEvent(
                event=event_type,
                stage="tool",
                payload={
                    "request_id": request_id,
                    "answers": answers,
                },
                diagnostics=None,
            )

        if event_type == "plan.updated":
            if not payload and isinstance(raw.get("state"), dict):
                payload = {"state": raw.get("state")}
            return EngineStreamEvent(
                event="plan.updated",
                stage="plan",
                payload=payload,
                diagnostics=None,
            )

        if event_type == "run.completed":
            return EngineStreamEvent(
                event="run.completed",
                stage="run",
                payload=payload or {"status": "completed"},
                diagnostics=None,
            )

        if event_type == "run.cancelled":
            return EngineStreamEvent(
                event="run.cancelled",
                stage="run",
                payload=payload or {"status": "cancelled"},
                diagnostics=None,
            )

        if event_type == "run.paused":
            return EngineStreamEvent(
                event="run.paused",
                stage="run",
                payload=payload or {"status": "paused"},
                diagnostics=None,
            )

        if event_type == "run.failed":
            message = (
                payload.get("error")
                or payload.get("message")
                or payload.get("reason")
                or raw.get("error")
                or raw.get("message")
                or "OpenCode run failed"
            )
            diagnostics = [{"message": str(message)}]
            code = payload.get("code") or raw.get("code")
            if code:
                diagnostics[0]["code"] = str(code)
            return EngineStreamEvent(
                event="run.failed",
                stage="run",
                payload={"error": str(message)},
                diagnostics=diagnostics,
            )

        return None
