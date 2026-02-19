import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService

from .published_apps_admin_builder_core import (
    _builder_chat_command_allowlist,
    _builder_targeted_tests_enabled,
    _builder_worker_build_gate_enabled,
    _extract_http_error_details,
    _is_allowed_sandbox_command,
    _next_build_seq,
    _run_worker_build_preflight,
    _summarize_dist_manifest,
    _truncate_for_context,
)
from .published_apps_admin_files import (
    _apply_patch_operations,
    _filter_builder_snapshot_files,
    _validate_builder_project_or_raise,
)
from .published_apps_admin_shared import (
    BUILDER_AGENT_MAX_SEARCH_RESULTS,
    BUILDER_CONTEXT_MAX_FILES,
    BUILDER_CHAT_COMMAND_TIMEOUT_SECONDS,
    BUILDER_CHAT_MAX_COMMAND_OUTPUT_BYTES,
    BUILDER_CONTEXT_MAX_FILE_BYTES,
    BuilderPatchOp,
)

def _builder_tool_list_files(files: Dict[str, str]) -> Dict[str, Any]:
    paths = sorted(files.keys())
    return {"count": len(paths), "paths": paths[:BUILDER_CONTEXT_MAX_FILES]}


def _builder_tool_read_file(files: Dict[str, str], path: str) -> Dict[str, Any]:
    if path not in files:
        return {"ok": False, "path": path, "message": "file not found"}
    content = files[path]
    return {
        "ok": True,
        "path": path,
        "size_bytes": len(content.encode("utf-8")),
        "preview": _truncate_for_context(content, max_bytes=min(1024, BUILDER_CONTEXT_MAX_FILE_BYTES)),
    }


def _builder_tool_search_code(files: Dict[str, str], query: str) -> Dict[str, Any]:
    needle = query.strip().lower()
    if not needle:
        return {"query": query, "matches": []}
    matches: List[Dict[str, Any]] = []
    for path in sorted(files.keys()):
        lines = files[path].splitlines()
        for index, line in enumerate(lines, start=1):
            if needle in line.lower():
                matches.append(
                    {
                        "path": path,
                        "line": index,
                        "preview": line[:180],
                    }
                )
                if len(matches) >= BUILDER_AGENT_MAX_SEARCH_RESULTS:
                    return {"query": query, "matches": matches}
    return {"query": query, "matches": matches}


def _builder_tool_apply_patch_dry_run(
    files: Dict[str, str],
    entry_file: str,
    operations: List[BuilderPatchOp],
) -> Dict[str, Any]:
    try:
        next_files, next_entry = _apply_patch_operations(files, entry_file, operations)
    except HTTPException as exc:
        message, diagnostics = _extract_http_error_details(exc)
        return {"ok": False, "message": message, "diagnostics": diagnostics}
    return {
        "ok": True,
        "entry_file": next_entry,
        "file_count": len(next_files),
        "diagnostics": [],
    }


def _builder_tool_compile_project(files: Dict[str, str], entry_file: str) -> Dict[str, Any]:
    try:
        diagnostics = _validate_builder_project_or_raise(files, entry_file)
    except HTTPException as exc:
        message, bad_diagnostics = _extract_http_error_details(exc)
        return {"ok": False, "message": message, "diagnostics": bad_diagnostics}
    return {"ok": True, "diagnostics": diagnostics}


def _looks_like_test_file(path: str) -> bool:
    lowered = path.lower()
    if "/__tests__/" in lowered:
        return True
    return lowered.endswith(
        (
            ".test.ts",
            ".test.tsx",
            ".test.js",
            ".test.jsx",
            ".test.mts",
            ".test.cts",
            ".spec.ts",
            ".spec.tsx",
            ".spec.js",
            ".spec.jsx",
            ".spec.mts",
            ".spec.cts",
        )
    )


def _read_package_scripts(files: Dict[str, str]) -> Dict[str, str]:
    package_source = files.get("package.json")
    if not isinstance(package_source, str) or not package_source.strip():
        return {}
    try:
        payload = json.loads(package_source)
    except json.JSONDecodeError:
        return {}
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    normalized: Dict[str, str] = {}
    for key, value in scripts.items():
        if isinstance(key, str) and isinstance(value, str):
            normalized[key] = value
    return normalized


def _select_test_script(files: Dict[str, str]) -> Optional[str]:
    scripts = _read_package_scripts(files)
    for key in ("test", "test:unit", "test:ci"):
        if key in scripts:
            return key
    return None


def _test_related_paths(files: Dict[str, str], changed_paths: List[str]) -> List[str]:
    test_files = [path for path in sorted(files.keys()) if _looks_like_test_file(path)]
    if not test_files:
        return []
    direct = [path for path in changed_paths if path in files and _looks_like_test_file(path)]
    if direct:
        return direct[:8]
    return test_files[:6]


async def _run_builder_targeted_tests(
    files: Dict[str, str],
    script_name: str,
    related_paths: List[str],
) -> Dict[str, Any]:
    from app.workers.tasks import _materialize_project_files, _run_subprocess

    npm_ci_timeout = int(os.getenv("APPS_BUILD_NPM_CI_TIMEOUT_SECONDS", "300"))
    test_timeout = int(os.getenv("APPS_BUILD_TEST_TIMEOUT_SECONDS", "240"))
    started_at = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="apps-builder-tests-") as temp_dir:
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
                f"`{install_name}` failed with exit code {install_code}\\n{install_stderr or install_stdout}"
            )

        command = ["npm", "run", script_name, "--", "--run", "--passWithNoTests"]
        if related_paths:
            command.extend(related_paths[:6])

        env = dict(os.environ)
        env["CI"] = "1"
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(project_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=test_timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            raise RuntimeError(f"Targeted tests timed out after {test_timeout}s (elapsed {elapsed_ms}ms)")

        return {
            "code": process.returncode or 0,
            "elapsed_ms": int((time.monotonic() - started_at) * 1000),
            "command": command,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }


async def _builder_tool_run_targeted_tests(files: Dict[str, str], changed_paths: List[str]) -> Dict[str, Any]:
    if not _builder_targeted_tests_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "message": "targeted tests disabled (`APPS_BUILDER_TARGETED_TESTS_ENABLED=0`)",
            "changed_paths": changed_paths[:6],
        }

    script_name = _select_test_script(files)
    if not script_name:
        return {
            "ok": True,
            "status": "skipped",
            "message": "No test script found in package.json",
            "changed_paths": changed_paths[:6],
        }

    related_paths = _test_related_paths(files, changed_paths)
    if not related_paths:
        return {
            "ok": True,
            "status": "skipped",
            "message": "No test files detected in draft project",
            "changed_paths": changed_paths[:6],
        }

    try:
        result = await _run_builder_targeted_tests(files, script_name, related_paths)
    except Exception as exc:
        message = str(exc).strip() or "targeted test execution failed"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "changed_paths": changed_paths[:6],
            "test_paths": related_paths,
            "diagnostics": [{"message": message}],
        }

    code = int(result.get("code") or 0)
    if code != 0:
        output = str(result.get("stderr") or result.get("stdout") or "").strip()
        message = output or f"targeted tests failed with exit code {code}"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "changed_paths": changed_paths[:6],
            "test_paths": related_paths,
            "command": result.get("command"),
            "elapsed_ms": result.get("elapsed_ms"),
            "diagnostics": [{"message": message}],
        }

    return {
        "ok": True,
        "status": "passed",
        "message": "targeted tests passed",
        "changed_paths": changed_paths[:6],
        "test_paths": related_paths,
        "command": result.get("command"),
        "elapsed_ms": result.get("elapsed_ms"),
    }

async def _builder_tool_build_project_worker(files: Dict[str, str]) -> Dict[str, Any]:
    if not _builder_worker_build_gate_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "message": "worker build tool disabled (`APPS_BUILDER_WORKER_BUILD_GATE_ENABLED=0`)",
        }
    try:
        dist_manifest = await _run_worker_build_preflight(files, include_dist_manifest=True)
    except Exception as exc:
        message = str(exc).strip() or "worker build failed"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "diagnostics": [{"message": message}],
        }
    if not isinstance(dist_manifest, dict):
        return {
            "ok": False,
            "status": "failed",
            "message": "worker build did not produce a dist manifest",
            "diagnostics": [{"message": "worker build did not produce a dist manifest"}],
        }
    return {
        "ok": True,
        "status": "succeeded",
        "dist_manifest": dist_manifest,
        "summary": _summarize_dist_manifest(dist_manifest),
    }


def _builder_tool_prepare_static_bundle(worker_build_result: Dict[str, Any]) -> Dict[str, Any]:
    status = str(worker_build_result.get("status") or "")
    if status == "skipped":
        return {
            "ok": True,
            "status": "skipped",
            "message": "worker build was skipped; static bundle preparation skipped",
        }
    if not worker_build_result.get("ok"):
        message = str(worker_build_result.get("message") or "worker build failed")
        diagnostics = worker_build_result.get("diagnostics")
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "diagnostics": diagnostics if isinstance(diagnostics, list) else [{"message": message}],
        }

    manifest = worker_build_result.get("dist_manifest")
    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "status": "failed",
            "message": "dist manifest is missing for static bundle preparation",
            "diagnostics": [{"message": "dist manifest is missing for static bundle preparation"}],
        }
    return {
        "ok": True,
        "status": "ready",
        "message": "static bundle manifest prepared",
        "summary": _summarize_dist_manifest(manifest),
    }


def _collect_changed_paths(operations: List[BuilderPatchOp]) -> List[str]:
    changed: List[str] = []
    for op in operations:
        if op.path:
            changed.append(op.path)
        if op.from_path:
            changed.append(op.from_path)
        if op.to_path:
            changed.append(op.to_path)
    deduped: List[str] = []
    for path in changed:
        if path and path not in deduped:
            deduped.append(path)
    return deduped


async def _apply_patch_operations_to_sandbox(
    runtime_service: PublishedAppDraftDevRuntimeService,
    *,
    sandbox_id: str,
    operations: List[BuilderPatchOp],
) -> None:
    for op in operations:
        if op.op == "upsert_file" and op.path:
            await runtime_service.client.write_file(
                sandbox_id=sandbox_id,
                path=op.path,
                content=op.content or "",
            )
        elif op.op == "delete_file" and op.path:
            await runtime_service.client.delete_file(
                sandbox_id=sandbox_id,
                path=op.path,
            )
        elif op.op == "rename_file" and op.from_path and op.to_path:
            await runtime_service.client.rename_file(
                sandbox_id=sandbox_id,
                from_path=op.from_path,
                to_path=op.to_path,
            )


async def _snapshot_files_from_sandbox(
    runtime_service: PublishedAppDraftDevRuntimeService,
    *,
    sandbox_id: str,
) -> Dict[str, str]:
    payload = await runtime_service.client.snapshot_files(sandbox_id=sandbox_id)
    files = payload.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("Sandbox snapshot did not return a files map")
    return _filter_builder_snapshot_files(files)


async def _run_allowlisted_sandbox_command(
    runtime_service: PublishedAppDraftDevRuntimeService,
    *,
    sandbox_id: str,
    command: List[str],
) -> Dict[str, Any]:
    allowlist = _builder_chat_command_allowlist()
    if not _is_allowed_sandbox_command(command, allowlist=allowlist):
        return {
            "ok": False,
            "status": "failed",
            "message": f"Sandbox command is not allowed: {' '.join(command)}",
            "diagnostics": [{"message": "Command not allowlisted"}],
        }
    result = await runtime_service.client.run_command(
        sandbox_id=sandbox_id,
        command=command,
        timeout_seconds=BUILDER_CHAT_COMMAND_TIMEOUT_SECONDS,
        max_output_bytes=BUILDER_CHAT_MAX_COMMAND_OUTPUT_BYTES,
    )
    code = int(result.get("code") or 0)
    if code != 0:
        message = str(result.get("stderr") or result.get("stdout") or "").strip()
        return {
            "ok": False,
            "status": "failed",
            "message": message or f"Command failed with exit code {code}",
            "diagnostics": [{"message": message or f"Command failed with exit code {code}"}],
            "command": command,
            "code": code,
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
        }
    return {
        "ok": True,
        "status": "passed",
        "message": "command passed",
        "command": command,
        "code": code,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
    }


async def _create_draft_revision_from_files(
    db: AsyncSession,
    *,
    app: PublishedApp,
    current: PublishedAppRevision,
    actor_id: Optional[UUID],
    files: Dict[str, str],
    entry_file: str,
) -> PublishedAppRevision:
    sanitized_files = _filter_builder_snapshot_files(files)
    _validate_builder_project_or_raise(sanitized_files, entry_file)
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=entry_file,
        files=sanitized_files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(sanitized_files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()
    app.current_draft_revision_id = revision.id
    return revision
