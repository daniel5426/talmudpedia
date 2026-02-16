from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    BuilderCheckpointType,
    BuilderConversationTurnStatus,
    PublishedApp,
    PublishedAppBuilderConversationTurn,
    PublishedAppPublishJob,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
)
from app.services.published_app_bundle_storage import PublishedAppBundleStorage

from .published_apps_admin_shared import (
    BUILDER_AGENT_MAX_ITERATIONS,
    BUILDER_CHAT_MAX_COMMAND_OUTPUT_BYTES,
    BUILDER_CHAT_COMMAND_TIMEOUT_SECONDS,
    BUILDER_CONTEXT_MAX_FILE_BYTES,
    BUILDER_CONTEXT_MAX_FILES,
    BUILDER_FILE_MENTION_RE,
    BuilderCheckpointResponse,
    BuilderConversationTurnResponse,
    BuilderPatchGenerationResult,
    BuilderPatchOp,
    IMPORT_RE,
)

logger = logging.getLogger(__name__)

def _builder_policy_error(message: str, *, field: Optional[str] = None) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "BUILDER_PATCH_POLICY_VIOLATION",
            "message": message,
            "field": field,
        },
    )


def _builder_compile_error(message: str, diagnostics: Optional[List[Dict[str, str]]] = None) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "BUILDER_COMPILE_FAILED",
            "message": message,
            "diagnostics": diagnostics or [],
        },
    )


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _builder_model_patch_generation_enabled() -> bool:
    return _env_flag("BUILDER_MODEL_PATCH_GENERATION_ENABLED", False)


def _builder_agentic_loop_enabled() -> bool:
    return _env_flag("BUILDER_AGENTIC_LOOP_ENABLED", False)


def _builder_targeted_tests_enabled() -> bool:
    return _env_flag("APPS_BUILDER_TARGETED_TESTS_ENABLED", False)


def _builder_chat_sandbox_tools_enabled() -> bool:
    return _env_flag("APPS_BUILDER_CHAT_SANDBOX_TOOLS_ENABLED", False)


def _builder_chat_commands_enabled() -> bool:
    return _env_flag("APPS_BUILDER_CHAT_COMMANDS_ENABLED", False)


def _builder_chat_worker_precheck_enabled() -> bool:
    return _env_flag("APPS_BUILDER_CHAT_WORKER_PRECHECK_ENABLED", False)


def _builder_chat_command_allowlist() -> List[List[str]]:
    raw = (os.getenv("APPS_BUILDER_CHAT_COMMAND_ALLOWLIST") or "").strip()
    defaults = [
        ["npm", "run", "build"],
        ["npm", "run", "lint"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "test", "--", "--run", "--passWithNoTests"],
    ]
    if not raw:
        return defaults
    commands: List[List[str]] = []
    for item in raw.split(";"):
        tokens = [token for token in item.strip().split(" ") if token]
        if tokens:
            commands.append(tokens)
    return commands or defaults


def _is_allowed_sandbox_command(command: List[str], *, allowlist: List[List[str]]) -> bool:
    if not command:
        return False
    # Reject obvious shell metacharacter payloads. Command is tokenized and executed without shell.
    forbidden = {"|", "&&", "||", ";", "$(", "`", ">", "<"}
    for token in command:
        if any(mark in token for mark in forbidden):
            return False
    return any(command == allowed for allowed in allowlist)


def _new_builder_request_id() -> str:
    return uuid4().hex


def _stream_event_payload(
    *,
    event: str,
    stage: str,
    request_id: str,
    data: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[List[Dict[str, str]]] = None,
    include_done_type: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "event": event,
        "stage": stage,
        "request_id": request_id,
    }
    if data is not None:
        payload["data"] = data
    if diagnostics:
        payload["diagnostics"] = diagnostics
    if include_done_type:
        payload["type"] = "done"
    return payload


def _stream_event_sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _extract_http_error_details(exc: HTTPException) -> tuple[str, List[Dict[str, str]]]:
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("code") or "builder operation failed")
        raw_diagnostics = detail.get("diagnostics")
        diagnostics: List[Dict[str, str]] = []
        if isinstance(raw_diagnostics, list):
            diagnostics = [item for item in raw_diagnostics if isinstance(item, dict)]
        if not diagnostics and message:
            diagnostics = [{"message": message}]
        return message, diagnostics
    return str(detail), [{"message": str(detail)}]


def _extract_http_error_code(exc: HTTPException) -> Optional[str]:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        if code:
            return str(code)
    return None


def _next_build_seq(previous: Optional[PublishedAppRevision]) -> int:
    if previous is None:
        return 1
    return int(previous.build_seq or 0) + 1


def _builder_auto_enqueue_enabled() -> bool:
    return _env_flag("APPS_BUILDER_BUILD_AUTOMATION_ENABLED", False)


def _builder_worker_build_gate_enabled() -> bool:
    return _env_flag("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", False)


def _publish_full_build_enabled() -> bool:
    return _env_flag("APPS_PUBLISH_FULL_BUILD_ENABLED", True)


def _publish_job_eager_enabled() -> bool:
    return _env_flag("APPS_PUBLISH_JOB_EAGER", False)


def _normalize_registered_task_name(raw: Any) -> str:
    token = str(raw or "").strip()
    if not token:
        return ""
    return token.split(" ", 1)[0]


def _verify_publish_worker_ready() -> Optional[str]:
    from app.workers.celery_app import celery_app

    inspect_timeout = float(os.getenv("APPS_PUBLISH_WORKER_INSPECT_TIMEOUT_SECONDS", "1.5"))
    inspect = celery_app.control.inspect(timeout=inspect_timeout)
    try:
        registered = inspect.registered() or {}
    except Exception as exc:
        logger.warning("Failed to inspect Celery registered tasks", extra={"error": str(exc)})
        return f"Failed to inspect Celery workers for publish capability: {exc}"

    if not isinstance(registered, dict) or not registered:
        return "No Celery worker responded to publish capability check. Ensure workers are running."

    task_name = "app.workers.tasks.publish_published_app_task"
    has_publish_task = False
    for tasks in registered.values():
        task_list = tasks if isinstance(tasks, list) else []
        if any(_normalize_registered_task_name(item) == task_name for item in task_list):
            has_publish_task = True
            break
    if not has_publish_task:
        return (
            f"Celery workers are running but `{task_name}` is not registered. "
            "Restart workers with the latest backend code."
        )

    try:
        active_queues = inspect.active_queues() or {}
    except Exception as exc:
        logger.warning("Failed to inspect Celery active queues", extra={"error": str(exc)})
        return f"Failed to inspect Celery worker queues for publish capability: {exc}"

    has_apps_build_queue = False
    if isinstance(active_queues, dict):
        for queue_items in active_queues.values():
            queue_list = queue_items if isinstance(queue_items, list) else []
            if any(isinstance(item, dict) and item.get("name") == "apps_build" for item in queue_list):
                has_apps_build_queue = True
                break
    if not has_apps_build_queue:
        return "Celery workers are running but none are subscribed to `apps_build` queue."
    return None


def _mark_revision_build_enqueue_failed(
    *,
    revision: PublishedAppRevision,
    reason: str,
) -> None:
    normalized_reason = (reason or "").strip()
    if len(normalized_reason) > 4000:
        normalized_reason = f"{normalized_reason[:4000]}... [truncated]"
    revision.build_status = PublishedAppRevisionBuildStatus.failed
    revision.build_error = normalized_reason or "Build enqueue failed"
    revision.build_started_at = None
    revision.build_finished_at = datetime.now(timezone.utc)
    revision.dist_storage_prefix = None
    revision.dist_manifest = None


def _enqueue_revision_build(
    *,
    revision: PublishedAppRevision,
    app: PublishedApp,
    build_kind: str,
) -> Optional[str]:
    if not _builder_auto_enqueue_enabled():
        return (
            "Build automation is disabled (`APPS_BUILDER_BUILD_AUTOMATION_ENABLED=0`). "
            "Enable it and retry build."
        )
    try:
        from app.workers.tasks import build_published_app_revision_task
    except Exception as exc:
        return f"Build worker task import failed: {exc}"

    try:
        build_published_app_revision_task.delay(
            revision_id=str(revision.id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            slug=app.slug,
            build_kind=build_kind,
        )
    except Exception as exc:
        logger.warning(
            "Failed to enqueue published app build task",
            extra={
                "revision_id": str(revision.id),
                "app_id": str(app.id),
                "build_kind": build_kind,
                "error": str(exc),
            },
        )
        return f"Failed to enqueue build task: {exc}"
    return None


def _enqueue_publish_job(
    *,
    job: PublishedAppPublishJob,
) -> Optional[str]:
    try:
        from app.workers.tasks import publish_published_app_task
    except Exception as exc:
        return f"Publish worker task import failed: {exc}"

    if _publish_job_eager_enabled():
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    publish_published_app_task.run,
                    str(job.id),
                )
                future.result()
        except Exception as exc:
            logger.warning(
                "Failed to run published app publish task eagerly",
                extra={
                    "publish_job_id": str(job.id),
                    "app_id": str(job.published_app_id),
                    "error": str(exc),
                },
            )
            return f"Failed to run publish task eagerly: {exc}"
        return None

    worker_ready_error = _verify_publish_worker_ready()
    if worker_ready_error:
        return worker_ready_error

    try:
        publish_published_app_task.delay(
            job_id=str(job.id),
        )
    except Exception as exc:
        logger.warning(
            "Failed to enqueue published app publish task",
            extra={
                "publish_job_id": str(job.id),
                "app_id": str(job.published_app_id),
                "error": str(exc),
            },
        )
        return f"Failed to enqueue publish task: {exc}"
    return None


def _summarize_dist_manifest(dist_manifest: Dict[str, Any]) -> Dict[str, Any]:
    assets = dist_manifest.get("assets")
    normalized_assets = assets if isinstance(assets, list) else []
    total_bytes = 0
    asset_paths: List[str] = []
    for item in normalized_assets:
        if not isinstance(item, dict):
            continue
        total_bytes += int(item.get("size") or 0)
        path = item.get("path")
        if isinstance(path, str) and path:
            asset_paths.append(path)
    return {
        "entry_html": str(dist_manifest.get("entry_html") or "index.html"),
        "asset_count": len(normalized_assets),
        "total_bytes": total_bytes,
        "asset_paths_preview": asset_paths[:12],
    }


async def _run_worker_build_preflight(
    files: Dict[str, str],
    *,
    include_dist_manifest: bool = False,
) -> Optional[Dict[str, Any]]:
    from app.workers.tasks import _build_dist_manifest, _materialize_project_files, _run_subprocess

    npm_ci_timeout = int(os.getenv("APPS_BUILD_NPM_CI_TIMEOUT_SECONDS", "300"))
    npm_build_timeout = int(os.getenv("APPS_BUILD_NPM_BUILD_TIMEOUT_SECONDS", "300"))

    with tempfile.TemporaryDirectory(prefix="apps-builder-preflight-") as temp_dir:
        project_dir = Path(temp_dir)
        _materialize_project_files(project_dir, files)

        has_lockfile = (project_dir / "package-lock.json").exists()
        install_command = ["npm", "ci"] if has_lockfile else ["npm", "install", "--no-audit", "--no-fund"]
        install_code, install_stdout, install_stderr = await _run_subprocess(
            install_command,
            cwd=project_dir,
            timeout_seconds=npm_ci_timeout,
        )
        if install_code != 0:
            install_name = "npm ci" if has_lockfile else "npm install"
            raise RuntimeError(
                f"`{install_name}` failed with exit code {install_code}\n{install_stderr or install_stdout}"
            )

        build_code, build_stdout, build_stderr = await _run_subprocess(
            ["npm", "run", "build"],
            cwd=project_dir,
            timeout_seconds=npm_build_timeout,
        )
        if build_code != 0:
            raise RuntimeError(
                f"`npm run build` failed with exit code {build_code}\n{build_stderr or build_stdout}"
            )

        dist_dir = project_dir / "dist"
        if not dist_dir.exists() or not dist_dir.is_dir():
            raise RuntimeError("Build succeeded but dist directory was not produced")
        if include_dist_manifest:
            return _build_dist_manifest(dist_dir)
    return None


async def _validate_worker_build_gate_or_raise(files: Dict[str, str]) -> None:
    if not _builder_worker_build_gate_enabled():
        return
    try:
        await _run_worker_build_preflight(files)
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).strip() or "Worker build validation failed"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        raise _builder_compile_error(
            "Worker build validation failed",
            diagnostics=[{"message": message}],
        )


def _promote_revision_dist_artifacts(
    *,
    app: PublishedApp,
    source_revision: PublishedAppRevision,
    destination_revision: PublishedAppRevision,
) -> Optional[str]:
    source_prefix = (source_revision.dist_storage_prefix or "").strip()
    if not source_prefix:
        return None

    storage = PublishedAppBundleStorage.from_env()
    destination_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
        tenant_id=str(app.tenant_id),
        app_id=str(app.id),
        revision_id=str(destination_revision.id),
    )
    storage.copy_prefix(
        source_prefix=source_prefix,
        destination_prefix=destination_prefix,
    )
    return destination_prefix


def _truncate_for_context(content: str, *, max_bytes: int = BUILDER_CONTEXT_MAX_FILE_BYTES) -> str:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content
    clipped = encoded[:max_bytes]
    while clipped:
        try:
            decoded = clipped.decode("utf-8")
            return decoded + "\n/* ...truncated for prompt budget... */"
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "/* ...truncated for prompt budget... */"


def _collect_local_imports(path: str, files: Dict[str, str]) -> List[str]:
    from .published_apps_admin_builder_patch import _resolve_local_project_import

    source = files.get(path, "")
    neighbors: List[str] = []
    for spec in IMPORT_RE.findall(source):
        import_path = (spec or "").strip()
        if not import_path.startswith("."):
            continue
        resolved = _resolve_local_project_import(import_path, path, files)
        if resolved:
            neighbors.append(resolved)
    return neighbors


def _select_builder_context_paths(
    files: Dict[str, str],
    entry_file: str,
    user_prompt: str,
    *,
    recent_paths: Optional[List[str]] = None,
) -> List[str]:
    selected: List[str] = []

    def add(path: str) -> None:
        if path in files and path not in selected:
            selected.append(path)

    add(entry_file)
    add("src/main.tsx")
    add("src/App.tsx")
    add("src/theme.ts")
    for focus_path in _extract_prompt_focus_paths(files, user_prompt):
        add(focus_path)

    queue = list(selected)
    visited: set[str] = set()
    while queue and len(selected) < BUILDER_CONTEXT_MAX_FILES:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for neighbor in _collect_local_imports(current, files):
            if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
                break
            if neighbor not in selected:
                selected.append(neighbor)
                queue.append(neighbor)

    for path in recent_paths or []:
        if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
            break
        add(path)

    prompt_terms = [
        term
        for term in re.findall(r"[a-zA-Z_]{4,}", user_prompt.lower())
        if term not in {"that", "with", "from", "this", "make", "into", "change"}
    ][:8]
    if prompt_terms and len(selected) < BUILDER_CONTEXT_MAX_FILES:
        for path in sorted(files.keys()):
            if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
                break
            lowered_path = path.lower()
            source = files.get(path, "").lower()
            if any(term in lowered_path or term in source for term in prompt_terms):
                add(path)

    if len(selected) < BUILDER_CONTEXT_MAX_FILES:
        for path in sorted(files.keys()):
            if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
                break
            add(path)
    return selected


def _extract_prompt_focus_paths(files: Dict[str, str], user_prompt: str, *, max_paths: int = 6) -> List[str]:
    from .published_apps_admin_builder_patch import _normalize_builder_path

    focus_paths: List[str] = []
    candidates: List[str] = []

    for raw_match in BUILDER_FILE_MENTION_RE.findall(user_prompt or ""):
        cleaned = raw_match.strip().strip(".,:;!?)]}>")
        if cleaned:
            candidates.append(cleaned)

    for candidate in candidates:
        normalized_input = candidate[2:] if candidate.startswith("./") else candidate
        normalized_path: Optional[str] = None
        try:
            normalized_path = _normalize_builder_path(normalized_input)
        except HTTPException:
            normalized_path = None

        if normalized_path and normalized_path in files and normalized_path not in focus_paths:
            focus_paths.append(normalized_path)
            if len(focus_paths) >= max_paths:
                break
            continue

        basename = PurePosixPath(normalized_input).name
        if not basename:
            continue
        basename_matches = [
            path
            for path in sorted(files.keys())
            if PurePosixPath(path).name == basename
        ]
        if len(basename_matches) == 1 and basename_matches[0] not in focus_paths:
            focus_paths.append(basename_matches[0])
            if len(focus_paths) >= max_paths:
                break

    return focus_paths[:max_paths]


def _serialize_patch_ops(operations: List[BuilderPatchOp]) -> List[Dict[str, Any]]:
    return [op.model_dump(exclude_none=True) for op in operations]


def _builder_conversation_to_response(turn: PublishedAppBuilderConversationTurn) -> BuilderConversationTurnResponse:
    return BuilderConversationTurnResponse(
        id=str(turn.id),
        published_app_id=str(turn.published_app_id),
        revision_id=str(turn.revision_id) if turn.revision_id else None,
        result_revision_id=str(turn.result_revision_id) if turn.result_revision_id else None,
        request_id=turn.request_id,
        status=turn.status.value if hasattr(turn.status, "value") else str(turn.status),
        user_prompt=turn.user_prompt,
        assistant_summary=turn.assistant_summary,
        assistant_rationale=turn.assistant_rationale,
        assistant_assumptions=list(turn.assistant_assumptions or []),
        patch_operations=list(turn.patch_operations or []),
        tool_trace=list(turn.tool_trace or []),
        tool_summary=dict(turn.tool_summary or {}),
        diagnostics=list(turn.diagnostics or []),
        failure_code=turn.failure_code,
        checkpoint_type=turn.checkpoint_type.value if hasattr(turn.checkpoint_type, "value") else str(turn.checkpoint_type),
        checkpoint_label=turn.checkpoint_label,
        created_by=str(turn.created_by) if turn.created_by else None,
        created_at=turn.created_at,
    )


def _build_tool_summary(trace_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "total": 0,
        "failed": 0,
        "completed": 0,
        "tools": [],
    }
    tools_seen: List[str] = []
    for event in trace_events:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "")
        if event_name not in {"tool_started", "tool_completed", "tool_failed"}:
            continue
        summary["total"] += 1
        data = event.get("data")
        if isinstance(data, dict):
            tool_name = str(data.get("tool") or "").strip()
            if tool_name and tool_name not in tools_seen:
                tools_seen.append(tool_name)
        if event_name == "tool_failed":
            summary["failed"] += 1
        if event_name == "tool_completed":
            summary["completed"] += 1
    summary["tools"] = tools_seen
    return summary


def _builder_checkpoint_to_response(turn: PublishedAppBuilderConversationTurn) -> BuilderCheckpointResponse:
    if turn.result_revision_id is None:
        raise ValueError("Checkpoint turn is missing result revision")
    return BuilderCheckpointResponse(
        turn_id=str(turn.id),
        request_id=turn.request_id,
        revision_id=str(turn.result_revision_id),
        source_revision_id=None,
        checkpoint_type=turn.checkpoint_type.value if hasattr(turn.checkpoint_type, "value") else str(turn.checkpoint_type),
        checkpoint_label=turn.checkpoint_label,
        assistant_summary=turn.assistant_summary,
        created_at=turn.created_at,
    )


async def _persist_builder_conversation_turn(
    db: AsyncSession,
    *,
    app_id: UUID,
    revision_id: Optional[UUID],
    actor_id: Optional[UUID],
    request_id: str,
    user_prompt: str,
    status: BuilderConversationTurnStatus,
    generation_result: Optional[BuilderPatchGenerationResult] = None,
    trace_events: Optional[List[Dict[str, Any]]] = None,
    diagnostics: Optional[List[Dict[str, str]]] = None,
    failure_code: Optional[str] = None,
    result_revision_id: Optional[UUID] = None,
    checkpoint_type: BuilderCheckpointType = BuilderCheckpointType.auto_run,
    checkpoint_label: Optional[str] = None,
) -> None:
    trace = list(trace_events or [])
    turn = PublishedAppBuilderConversationTurn(
        published_app_id=app_id,
        revision_id=revision_id,
        result_revision_id=result_revision_id,
        request_id=request_id,
        status=status,
        user_prompt=user_prompt,
        assistant_summary=generation_result.summary if generation_result else None,
        assistant_rationale=generation_result.rationale if generation_result else None,
        assistant_assumptions=list(generation_result.assumptions) if generation_result else [],
        patch_operations=_serialize_patch_ops(generation_result.operations) if generation_result else [],
        tool_trace=trace,
        tool_summary=_build_tool_summary(trace),
        diagnostics=list(diagnostics or []),
        failure_code=failure_code,
        checkpoint_type=checkpoint_type,
        checkpoint_label=checkpoint_label,
        created_by=actor_id,
    )
    db.add(turn)
    await db.flush()
