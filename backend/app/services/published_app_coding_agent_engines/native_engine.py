from __future__ import annotations

from typing import Any, AsyncGenerator

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionEvent, ExecutionMode
from app.db.postgres.models.agents import AgentRun, RunStatus

from .base import EngineCancelResult, EngineRunContext, EngineStreamEvent


MappedEvent = tuple[str, str, dict[str, Any], list[dict[str, Any]] | None]


class NativePublishedAppCodingAgentEngine:
    def __init__(self, *, executor: AgentExecutorService):
        self._executor = executor

    async def stream(self, ctx: EngineRunContext) -> AsyncGenerator[EngineStreamEvent, None]:
        run = ctx.run
        if run.status == RunStatus.paused and ctx.resume_payload is not None:
            await self._executor.resume_run(run.id, ctx.resume_payload, background=False)

        async for raw in self._executor.run_and_stream(
            run.id,
            self._executor.db,
            ctx.resume_payload,
            mode=ExecutionMode.DEBUG,
        ):
            mapped = self._map_execution_event(raw)
            if mapped is None:
                continue
            mapped_event, stage, payload, diagnostics = mapped
            yield EngineStreamEvent(
                event=mapped_event,
                stage=stage,
                payload=payload,
                diagnostics=diagnostics,
            )

    async def cancel(self, run: AgentRun) -> EngineCancelResult:
        return EngineCancelResult(confirmed=True, diagnostics=[])

    @staticmethod
    def _map_execution_event(event: ExecutionEvent) -> MappedEvent | None:
        if event.event == "token":
            return (
                "assistant.delta",
                "assistant",
                {"content": (event.data or {}).get("content", "")},
                None,
            )

        if event.event == "on_tool_start":
            data = event.data if isinstance(event.data, dict) else {}
            return (
                "tool.started",
                "tool",
                {
                    "tool": event.name,
                    "span_id": event.span_id,
                    "input": data.get("input"),
                },
                None,
            )

        if event.event == "on_tool_end":
            data = event.data if isinstance(event.data, dict) else {}
            output = data.get("output")
            if isinstance(output, dict) and output.get("error"):
                diagnostics: list[dict[str, Any]] = [{"message": str(output.get("error"))}]
                code = output.get("code")
                field = output.get("field")
                if code:
                    diagnostics[0]["code"] = str(code)
                if field:
                    diagnostics[0]["field"] = str(field)
                failures = output.get("failures")
                if isinstance(failures, list) and failures:
                    diagnostics[0]["patch_failure_count"] = len(failures)
                    first_failure = failures[0] if isinstance(failures[0], dict) else {}
                    if isinstance(first_failure, dict):
                        refresh = first_failure.get("recommended_refresh")
                        if isinstance(refresh, dict):
                            diagnostics[0]["recommended_refresh"] = {
                                "path": first_failure.get("path"),
                                "start_line": refresh.get("start_line"),
                                "end_line": refresh.get("end_line"),
                            }
                result_payload = output.get("result")
                if isinstance(result_payload, dict):
                    patch_code = result_payload.get("code")
                    if patch_code:
                        diagnostics[0]["patch_code"] = str(patch_code)
                return (
                    "tool.failed",
                    "tool",
                    {
                        "tool": event.name,
                        "span_id": event.span_id,
                        "output": output,
                    },
                    diagnostics,
                )
            return (
                "tool.completed",
                "tool",
                {
                    "tool": event.name,
                    "span_id": event.span_id,
                    "output": output,
                },
                None,
            )

        if event.event == "node_start":
            return (
                "plan.updated",
                "plan",
                {
                    "node": event.name,
                    "span_id": event.span_id,
                    "state": event.data,
                },
                None,
            )

        if event.event == "error":
            message = str((event.data or {}).get("error") or "runtime error")
            return (
                "run.failed",
                "run",
                {
                    "error": message,
                },
                [{"message": message}],
            )

        return None
