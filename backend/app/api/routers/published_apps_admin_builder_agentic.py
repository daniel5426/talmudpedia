from typing import Any, Dict, List, Optional

from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService

from .published_apps_admin_builder_core import (
    _builder_chat_commands_enabled,
    _builder_chat_worker_precheck_enabled,
    _builder_compile_error,
    _extract_prompt_focus_paths,
    _stream_event_payload,
)
from .published_apps_admin_builder_model import _generate_builder_patch_with_model
from .published_apps_admin_builder_patch import _apply_patch_operations
from .published_apps_admin_builder_tools import (
    _apply_patch_operations_to_sandbox,
    _builder_tool_apply_patch_dry_run,
    _builder_tool_build_project_worker,
    _builder_tool_compile_project,
    _builder_tool_list_files,
    _builder_tool_read_file,
    _builder_tool_run_targeted_tests,
    _builder_tool_search_code,
    _collect_changed_paths,
    _run_allowlisted_sandbox_command,
)
from .published_apps_admin_shared import BUILDER_AGENT_MAX_ITERATIONS, BuilderPatchGenerationResult, BuilderPatchOp

async def _run_builder_agentic_loop(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    request_id: str,
    runtime_service: Optional[PublishedAppDraftDevRuntimeService] = None,
    sandbox_id: Optional[str] = None,
) -> tuple[BuilderPatchGenerationResult, List[Dict[str, Any]], Dict[str, str], str]:
    def tool_started(stage: str, tool: str, iteration: int, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload_data: Dict[str, Any] = {"tool": tool, "iteration": iteration}
        if isinstance(data, dict):
            payload_data.update(data)
        return _stream_event_payload(
            event="tool_started",
            stage=stage,
            request_id=request_id,
            data=payload_data,
        )

    def tool_finished(
        *,
        stage: str,
        tool: str,
        iteration: int,
        ok: bool,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return _stream_event_payload(
            event="tool_completed" if ok else "tool_failed",
            stage=stage,
            request_id=request_id,
            data={
                "tool": tool,
                "iteration": iteration,
                "status": "ok" if ok else "failed",
                "result": result,
            },
            diagnostics=result.get("diagnostics") if not ok else None,
        )

    trace_events: List[Dict[str, Any]] = []
    repair_feedback: List[str] = []
    recent_paths: List[str] = []
    aggregate_ops: List[BuilderPatchOp] = []
    working_files = dict(files)
    working_entry = entry_file
    focus_paths = _extract_prompt_focus_paths(working_files, user_prompt, max_paths=4)

    for iteration in range(1, BUILDER_AGENT_MAX_ITERATIONS + 1):
        trace_events.append(tool_started("inspect", "list_files", iteration))
        list_result = _builder_tool_list_files(working_files)
        trace_events.append(tool_finished(stage="inspect", tool="list_files", iteration=iteration, ok=True, result=list_result))
        inspect_paths: List[str] = []
        for path in focus_paths:
            if path in working_files and path not in inspect_paths:
                inspect_paths.append(path)
        if recent_paths:
            recent_candidate = recent_paths[-1]
            if recent_candidate in working_files and recent_candidate not in inspect_paths:
                inspect_paths.append(recent_candidate)
        for inspect_path in inspect_paths[:3]:
            trace_events.append(tool_started("inspect", "read_file", iteration, {"path": inspect_path}))
            read_result = _builder_tool_read_file(working_files, inspect_path)
            trace_events.append(tool_finished(stage="inspect", tool="read_file", iteration=iteration, ok=True, result=read_result))
        trace_events.append(tool_started("inspect", "search_code", iteration))
        search_result = _builder_tool_search_code(working_files, user_prompt)
        trace_events.append(tool_finished(stage="inspect", tool="search_code", iteration=iteration, ok=True, result=search_result))

        model_recent_paths: List[str] = []
        for path in focus_paths + recent_paths:
            if path and path not in model_recent_paths:
                model_recent_paths.append(path)
        model_recent_paths = model_recent_paths[:8]

        result = await _generate_builder_patch_with_model(
            user_prompt=user_prompt,
            files=working_files,
            entry_file=working_entry,
            repair_feedback=repair_feedback,
            recent_paths=model_recent_paths,
        )

        dry_run_result = _builder_tool_apply_patch_dry_run(
            working_files,
            working_entry,
            result.operations,
        )
        trace_events.append(tool_started("patch_dry_run", "apply_patch_dry_run", iteration))
        trace_events.append(
            tool_finished(
                stage="patch_dry_run",
                tool="apply_patch_dry_run",
                iteration=iteration,
                ok=bool(dry_run_result.get("ok")),
                result=dry_run_result,
            )
        )
        if not dry_run_result.get("ok"):
            failure_message = str(dry_run_result.get("message") or "patch dry run failed")
            repair_feedback.append(failure_message)
            continue

        working_files, working_entry = _apply_patch_operations(
            working_files,
            working_entry,
            result.operations,
        )
        aggregate_ops.extend(result.operations)
        recent_paths = [
            op.path
            for op in result.operations
            if op.path
        ] + [
            op.to_path
            for op in result.operations
            if op.to_path
        ]
        recent_paths = [path for path in recent_paths if path][:8]
        focus_paths = _extract_prompt_focus_paths(working_files, user_prompt, max_paths=4)
        if runtime_service is not None and sandbox_id:
            try:
                trace_events.append(tool_started("edit", "apply_sandbox_patch", iteration))
                await _apply_patch_operations_to_sandbox(
                    runtime_service,
                    sandbox_id=sandbox_id,
                    operations=result.operations,
                )
                trace_events.append(
                    tool_finished(
                        stage="edit",
                        tool="apply_sandbox_patch",
                        iteration=iteration,
                        ok=True,
                        result={
                            "status": "applied",
                            "changed_paths": _collect_changed_paths(result.operations),
                        },
                    )
                )
            except Exception as exc:
                failed = {
                    "status": "failed",
                    "message": str(exc),
                    "diagnostics": [{"message": str(exc)}],
                }
                trace_events.append(
                    tool_finished(
                        stage="edit",
                        tool="apply_sandbox_patch",
                        iteration=iteration,
                        ok=False,
                        result=failed,
                    )
                )
                repair_feedback.append(str(exc))
                continue

        compile_result = _builder_tool_compile_project(working_files, working_entry)
        trace_events.append(tool_started("compile", "compile_project", iteration))
        trace_events.append(
            tool_finished(
                stage="compile",
                tool="compile_project",
                iteration=iteration,
                ok=bool(compile_result.get("ok")),
                result=compile_result,
            )
        )
        if not compile_result.get("ok"):
            repair_feedback.append(str(compile_result.get("message") or "compile failed"))
            continue

        test_result = await _builder_tool_run_targeted_tests(working_files, recent_paths)
        trace_events.append(tool_started("test", "run_targeted_tests", iteration))
        trace_events.append(
            tool_finished(
                stage="test",
                tool="run_targeted_tests",
                iteration=iteration,
                ok=bool(test_result.get("ok")),
                result=test_result,
            )
        )
        if not test_result.get("ok"):
            repair_feedback.append(str(test_result.get("message") or "targeted tests failed"))
            continue

        if _builder_chat_commands_enabled() and runtime_service is not None and sandbox_id:
            trace_events.append(tool_started("command", "run_command", iteration, {"command": "npm run build"}))
            build_command_result = await _run_allowlisted_sandbox_command(
                runtime_service,
                sandbox_id=sandbox_id,
                command=["npm", "run", "build"],
            )
            trace_events.append(
                tool_finished(
                    stage="command",
                    tool="run_command",
                    iteration=iteration,
                    ok=bool(build_command_result.get("ok")),
                    result=build_command_result,
                )
            )
            if not build_command_result.get("ok"):
                repair_feedback.append(str(build_command_result.get("message") or "sandbox build failed"))
                continue
        elif _builder_chat_worker_precheck_enabled():
            worker_build_result = await _builder_tool_build_project_worker(working_files)
            trace_events.append(tool_started("worker_build", "build_project_worker", iteration))
            trace_events.append(
                tool_finished(
                    stage="worker_build",
                    tool="build_project_worker",
                    iteration=iteration,
                    ok=bool(worker_build_result.get("ok")),
                    result=worker_build_result,
                )
            )
            if not worker_build_result.get("ok"):
                repair_feedback.append(str(worker_build_result.get("message") or "worker build failed"))
                continue

        return (
            BuilderPatchGenerationResult(
                operations=aggregate_ops,
                summary=result.summary,
                rationale=result.rationale,
                assumptions=result.assumptions,
            ),
            trace_events,
            working_files,
            working_entry,
        )

    exc = _builder_compile_error(
        "Agentic loop could not produce a valid patch",
        diagnostics=[{"message": item} for item in repair_feedback[-6:]] or [{"message": "No valid patch generated"}],
    )
    setattr(exc, "builder_trace_events", list(trace_events))
    raise exc
