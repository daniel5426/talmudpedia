from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, RunStatus
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

    async def stream(self, ctx: EngineRunContext) -> AsyncGenerator[EngineStreamEvent, None]:
        run = ctx.run
        input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
        raw_context = input_params.get("context")
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        input_params["context"] = context
        run.input_params = input_params
        messages = input_params.get("messages") if isinstance(input_params.get("messages"), list) else []
        prompt = str(input_params.get("input") or "").strip()
        prompt_history_budget_chars = int(os.getenv("APPS_CODING_AGENT_OPENCODE_PROMPT_HISTORY_BUDGET_CHARS", "14000"))
        effective_prompt = build_opencode_effective_prompt(
            current_user_prompt=prompt,
            messages=[item for item in messages if isinstance(item, dict)],
            max_chars=prompt_history_budget_chars,
        )
        resolved_model_id = str(context.get("resolved_model_id") or "").strip()
        opencode_model_id = str(context.get("opencode_model_id") or "").strip()
        workspace_path = str(
            context.get("opencode_workspace_path")
            or context.get("coding_run_sandbox_workspace_path")
            or ""
        ).strip()
        sandbox_id = str(
            context.get("opencode_sandbox_id")
            or context.get("coding_run_sandbox_id")
            or ""
        ).strip()
        workspace_root = os.path.realpath(os.path.abspath(workspace_path)) if workspace_path else ""

        if not run.engine_run_ref:
            opencode_start_started_at = time.monotonic()
            run.engine_run_ref = await self._client.start_run(
                run_id=str(run.id),
                app_id=str(ctx.app.id),
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                model_id=opencode_model_id or resolved_model_id,
                prompt=effective_prompt,
                messages=[item for item in messages if isinstance(item, dict)],
                selected_agent_contract=(
                    dict(context.get("selected_agent_contract"))
                    if isinstance(context.get("selected_agent_contract"), dict)
                    else None
                ),
            )
            opencode_start_ms = max(0, int((time.monotonic() - opencode_start_started_at) * 1000))
            timings = context.get("timing_metrics_ms")
            if not isinstance(timings, dict):
                timings = {}
                context["timing_metrics_ms"] = timings
            timings["opencode_start"] = opencode_start_ms
            logger.info(
                "CODING_AGENT_TIMING run_id=%s app_id=%s phase=opencode_start duration_ms=%s",
                run.id,
                ctx.app.id,
                opencode_start_ms,
            )

        run.status = RunStatus.running
        if not run.started_at:
            run.started_at = datetime.now(timezone.utc)
        run.error_message = None
        await self._db.commit()

        saw_terminal = False
        saw_failure = False
        failure_message = "OpenCode run failed"
        saw_apply_patch_failure = False
        saw_apply_patch_success = False
        saw_recovery_edit_success = False
        fail_on_unrecovered_apply_patch = str(
            os.getenv("APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH", "1")
        ).strip().lower() in {"1", "true", "yes", "on"}

        async for raw in self._client.stream_run_events(run_ref=str(run.engine_run_ref)):
            mapped = self._translate_event(raw)
            if mapped is None:
                continue
            if mapped.event == "tool.failed" and self._is_apply_patch_tool(mapped.payload):
                saw_apply_patch_failure = True
            elif mapped.event == "tool.completed":
                if self._is_successful_apply_patch(mapped.payload):
                    saw_apply_patch_success = True
                    saw_recovery_edit_success = True
                elif self._is_recovery_edit_tool(mapped.payload):
                    saw_recovery_edit_success = True
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
                    "AUDIT_SANDBOX_PATH_VIOLATION tenant_id=%s run_id=%s app_id=%s sandbox_id=%s workspace_root=%s violations=%s",
                    run.tenant_id,
                    run.id,
                    ctx.app.id,
                    sandbox_id,
                    workspace_root,
                    workspace_violations,
                )
                try:
                    if run.engine_run_ref:
                        await self._client.cancel_run(run_ref=str(run.engine_run_ref))
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
                continue
            if mapped.event == "run.failed":
                saw_terminal = True
                saw_failure = True
                if mapped.diagnostics:
                    failure_message = str(mapped.diagnostics[0].get("message") or failure_message)
                else:
                    failure_message = str((mapped.payload or {}).get("error") or failure_message)
                continue
            yield mapped

        persisted = await self._db.get(AgentRun, run.id) or run
        if (
            fail_on_unrecovered_apply_patch
            and saw_terminal
            and not saw_failure
            and saw_apply_patch_failure
            and not saw_apply_patch_success
            and not saw_recovery_edit_success
        ):
            saw_failure = True
            failure_message = (
                "OpenCode run completed after apply_patch failures without a successful follow-up edit."
            )
        if saw_terminal and not saw_failure:
            persisted.status = RunStatus.completed
            persisted.error_message = None
        else:
            persisted.status = RunStatus.failed
            if saw_terminal and saw_failure:
                persisted.error_message = failure_message
            else:
                persisted.error_message = "OpenCode stream ended without terminal completion event"
        persisted.completed_at = datetime.now(timezone.utc)
        await self._db.commit()

    async def cancel(self, run: AgentRun) -> EngineCancelResult:
        if not run.engine_run_ref:
            return EngineCancelResult(
                confirmed=False,
                diagnostics=[{"code": "OPENCODE_CANCEL_UNCONFIRMED", "message": "Missing OpenCode run reference"}],
            )
        try:
            confirmed = await self._client.cancel_run(run_ref=str(run.engine_run_ref))
        except Exception as exc:
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
            return EngineCancelResult(confirmed=True, diagnostics=[])
        return EngineCancelResult(
            confirmed=False,
            diagnostics=[{"code": "OPENCODE_CANCEL_UNCONFIRMED", "message": "OpenCode cancellation not confirmed"}],
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
    def _translate_event(raw: dict[str, Any]) -> EngineStreamEvent | None:
        event_type = str(raw.get("event") or raw.get("type") or "").strip().lower()
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}

        if event_type in {"assistant.delta", "assistant_delta", "token"}:
            content = payload.get("content") if isinstance(payload, dict) else None
            if content is None:
                content = raw.get("content")
            return EngineStreamEvent(
                event="assistant.delta",
                stage="assistant",
                payload={"content": str(content or "")},
                diagnostics=None,
            )

        if event_type in {"tool.started", "tool_start", "on_tool_start"}:
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

        if event_type in {"tool.completed", "tool_end", "on_tool_end"}:
            tool_name = raw.get("tool") or payload.get("tool") or raw.get("name")
            output = payload.get("output") if isinstance(payload, dict) else raw.get("output")
            if isinstance(output, dict) and output.get("error"):
                diagnostics: list[dict[str, Any]] = [{"message": str(output.get("error"))}]
                if output.get("code"):
                    diagnostics[0]["code"] = str(output.get("code"))
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
                diagnostics=None,
            )

        if event_type in {"tool.failed", "tool_error"}:
            tool_name = raw.get("tool") or payload.get("tool") or raw.get("name")
            message = payload.get("error") or raw.get("error") or "Tool failed"
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

        if event_type in {"plan.updated", "plan_update", "node_start"}:
            if not payload and isinstance(raw.get("state"), dict):
                payload = {"state": raw.get("state")}
            return EngineStreamEvent(
                event="plan.updated",
                stage="plan",
                payload=payload,
                diagnostics=None,
            )

        if event_type in {"run.completed", "completed"}:
            return EngineStreamEvent(
                event="run.completed",
                stage="run",
                payload=payload or {"status": "completed"},
                diagnostics=None,
            )

        if event_type in {"run.failed", "error", "failed"}:
            message = payload.get("error") or raw.get("error") or "OpenCode run failed"
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
