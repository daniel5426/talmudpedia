from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.published_apps_admin_files import (
    _assert_builder_path_allowed,
    _normalize_builder_path,
    _validate_builder_project_or_raise,
)
from app.db.postgres.engine import sessionmaker as get_session
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppDraftDevSessionStatus, PublishedAppRevision, PublishedAppRevisionBuildStatus, PublishedAppRevisionKind
from app.db.postgres.models.registry import ToolDefinitionScope, ToolImplementationType, ToolRegistry, ToolStatus
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.tool_function_registry import register_tool_function

CODING_AGENT_SURFACE = "published_app_coding_agent"
CODING_AGENT_TOOL_NAMESPACE = "coding-agent"


def _command_allowlist() -> list[list[str]]:
    raw = (os.getenv("APPS_CODING_AGENT_COMMAND_ALLOWLIST") or "").strip()
    defaults = [
        ["npm", "run", "build"],
        ["npm", "run", "lint"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "test", "--", "--run", "--passWithNoTests"],
    ]
    if not raw:
        return defaults
    parsed: list[list[str]] = []
    for item in raw.split(";"):
        tokens = [token for token in item.strip().split(" ") if token]
        if tokens:
            parsed.append(tokens)
    return parsed or defaults


def _is_command_allowed(command: list[str]) -> bool:
    if not command:
        return False
    forbidden_tokens = {"|", "&&", "||", ";", "$(", "`", ">", "<"}
    for token in command:
        if any(mark in token for mark in forbidden_tokens):
            return False
    allowlist = _command_allowlist()
    return any(command == allowed for allowed in allowlist)


@dataclass
class _RunToolContext:
    db: AsyncSession
    run: AgentRun
    app: PublishedApp
    revision: PublishedAppRevision
    runtime_service: PublishedAppDraftDevRuntimeService
    sandbox_id: str
    actor_id: UUID


def _parse_uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception as exc:
        raise ValueError(f"Invalid {field}") from exc


async def _resolve_run_tool_context(
    db: AsyncSession,
    payload: dict[str, Any],
) -> _RunToolContext:
    run_id_raw = payload.get("run_id")
    if run_id_raw is None and isinstance(payload.get("context"), dict):
        run_id_raw = payload["context"].get("run_id")
    if run_id_raw is None:
        raise ValueError("run_id is required in tool context")

    run_id = _parse_uuid(run_id_raw, "run_id")
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise ValueError("Run not found")
    if str(run.surface or "") != CODING_AGENT_SURFACE:
        raise PermissionError("Run is not a coding-agent run")
    if run.published_app_id is None:
        raise ValueError("Run is missing published_app_id")

    app = await db.get(PublishedApp, run.published_app_id)
    if app is None:
        raise ValueError("Published app not found for run")

    actor_id = run.initiator_user_id or run.user_id
    if actor_id is None:
        raise PermissionError("Coding-agent tools require a user-scoped run")

    revision_id = app.current_draft_revision_id or run.base_revision_id
    if revision_id is None:
        raise ValueError("No draft revision available for coding-agent run")

    revision = await db.get(PublishedAppRevision, revision_id)
    if revision is None:
        raise ValueError("Draft revision not found")
    if str(revision.published_app_id) != str(app.id):
        raise PermissionError("Revision does not belong to run app")

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.ensure_session(
            app=app,
            revision=revision,
            user_id=actor_id,
            files=dict(revision.files or {}),
            entry_file=revision.entry_file,
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise RuntimeError(str(exc)) from exc

    if session.status == PublishedAppDraftDevSessionStatus.error:
        raise RuntimeError(session.last_error or "Draft dev sandbox failed")
    if not session.sandbox_id:
        raise RuntimeError("Draft dev sandbox id is missing")

    return _RunToolContext(
        db=db,
        run=run,
        app=app,
        revision=revision,
        runtime_service=runtime_service,
        sandbox_id=session.sandbox_id,
        actor_id=actor_id,
    )


async def _create_draft_revision_from_files(
    *,
    db: AsyncSession,
    app: PublishedApp,
    current: PublishedAppRevision,
    actor_id: UUID | None,
    files: dict[str, str],
    entry_file: str,
) -> PublishedAppRevision:
    _validate_builder_project_or_raise(files, entry_file)
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=entry_file,
        files=files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=int(current.build_seq or 0) + 1,
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()
    app.current_draft_revision_id = revision.id
    return revision


async def _snapshot_files(ctx: _RunToolContext) -> dict[str, str]:
    payload = await ctx.runtime_service.client.snapshot_files(sandbox_id=ctx.sandbox_id)
    raw_files = payload.get("files")
    if not isinstance(raw_files, dict):
        raise RuntimeError("Sandbox snapshot did not return files")
    files: dict[str, str] = {}
    for path, content in raw_files.items():
        if isinstance(path, str):
            files[path] = content if isinstance(content, str) else str(content)
    return files


@register_tool_function("coding_agent_list_files")
async def coding_agent_list_files(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    limit = int(tool_payload.get("limit") or 500)
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.list_files(sandbox_id=ctx.sandbox_id, limit=limit)
        await db.commit()
        return result


@register_tool_function("coding_agent_read_file")
async def coding_agent_read_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_builder_path(str(tool_payload.get("path") or ""))
    _assert_builder_path_allowed(path)
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.read_file(sandbox_id=ctx.sandbox_id, path=path)
        await db.commit()
        return result


@register_tool_function("coding_agent_search_code")
async def coding_agent_search_code(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    query = str(tool_payload.get("query") or "").strip()
    max_results = int(tool_payload.get("max_results") or 30)
    if not query:
        raise ValueError("query is required")
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.search_code(
            sandbox_id=ctx.sandbox_id,
            query=query,
            max_results=max_results,
        )
        await db.commit()
        return result


@register_tool_function("coding_agent_write_file")
async def coding_agent_write_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_builder_path(str(tool_payload.get("path") or ""))
    _assert_builder_path_allowed(path)
    content = tool_payload.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        content = str(content)
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.write_file(
            sandbox_id=ctx.sandbox_id,
            path=path,
            content=content,
        )
        await db.commit()
        return result


@register_tool_function("coding_agent_rename_file")
async def coding_agent_rename_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    from_path = _normalize_builder_path(str(tool_payload.get("from_path") or ""))
    to_path = _normalize_builder_path(str(tool_payload.get("to_path") or ""))
    _assert_builder_path_allowed(from_path)
    _assert_builder_path_allowed(to_path)
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.rename_file(
            sandbox_id=ctx.sandbox_id,
            from_path=from_path,
            to_path=to_path,
        )
        await db.commit()
        return result


@register_tool_function("coding_agent_delete_file")
async def coding_agent_delete_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_builder_path(str(tool_payload.get("path") or ""))
    _assert_builder_path_allowed(path)
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.delete_file(sandbox_id=ctx.sandbox_id, path=path)
        await db.commit()
        return result


@register_tool_function("coding_agent_snapshot_files")
async def coding_agent_snapshot_files(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        files = await _snapshot_files(ctx)
        await db.commit()
        return {"sandbox_id": ctx.sandbox_id, "files": files, "file_count": len(files)}


@register_tool_function("coding_agent_run_targeted_tests")
async def coding_agent_run_targeted_tests(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    command = tool_payload.get("command")
    if isinstance(command, list):
        normalized_command = [str(token) for token in command if str(token).strip()]
    else:
        normalized_command = ["npm", "run", "test", "--", "--run", "--passWithNoTests"]
    if not _is_command_allowed(normalized_command):
        raise PermissionError(f"Command is not allowlisted: {' '.join(normalized_command)}")

    timeout_seconds = int(os.getenv("APPS_CODING_AGENT_TEST_TIMEOUT_SECONDS", "240"))
    max_output_bytes = int(os.getenv("APPS_CODING_AGENT_MAX_COMMAND_OUTPUT_BYTES", "12000"))
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.run_command(
            sandbox_id=ctx.sandbox_id,
            command=normalized_command,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        code = int(result.get("code") or 0)
        status = "passed" if code == 0 else "failed"
        await db.commit()
        return {
            "status": status,
            "ok": code == 0,
            "command": normalized_command,
            "result": result,
        }


@register_tool_function("coding_agent_build_worker_precheck")
async def coding_agent_build_worker_precheck(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    command = ["npm", "run", "build"]
    if not _is_command_allowed(command):
        raise PermissionError("npm run build is not allowlisted")
    timeout_seconds = int(os.getenv("APPS_CODING_AGENT_BUILD_TIMEOUT_SECONDS", "300"))
    max_output_bytes = int(os.getenv("APPS_CODING_AGENT_MAX_COMMAND_OUTPUT_BYTES", "12000"))
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.run_command(
            sandbox_id=ctx.sandbox_id,
            command=command,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        code = int(result.get("code") or 0)
        await db.commit()
        return {
            "status": "succeeded" if code == 0 else "failed",
            "ok": code == 0,
            "command": command,
            "result": result,
        }


@register_tool_function("coding_agent_create_checkpoint")
async def coding_agent_create_checkpoint(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        current = await db.get(PublishedAppRevision, ctx.app.current_draft_revision_id)
        if current is None:
            raise ValueError("Current draft revision not found")

        files = await _snapshot_files(ctx)
        entry_file = str(tool_payload.get("entry_file") or current.entry_file)
        entry_file = _normalize_builder_path(entry_file)
        _assert_builder_path_allowed(entry_file, field="entry_file")
        revision = await _create_draft_revision_from_files(
            db=db,
            app=ctx.app,
            current=current,
            actor_id=ctx.actor_id,
            files=files,
            entry_file=entry_file,
        )
        ctx.run.checkpoint_revision_id = revision.id
        if ctx.run.result_revision_id is None:
            ctx.run.result_revision_id = revision.id
        await db.commit()
        return {
            "checkpoint_revision_id": str(revision.id),
            "created_at": revision.created_at.isoformat() if revision.created_at else datetime.now(timezone.utc).isoformat(),
            "file_count": len(files),
            "entry_file": entry_file,
        }


@register_tool_function("coding_agent_restore_checkpoint")
async def coding_agent_restore_checkpoint(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    checkpoint_id_raw = tool_payload.get("checkpoint_revision_id") or tool_payload.get("checkpoint_id")
    if checkpoint_id_raw is None:
        raise ValueError("checkpoint_revision_id is required")
    checkpoint_revision_id = _parse_uuid(checkpoint_id_raw, "checkpoint_revision_id")

    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        checkpoint_revision = await db.get(PublishedAppRevision, checkpoint_revision_id)
        if checkpoint_revision is None:
            raise ValueError("Checkpoint revision not found")
        if str(checkpoint_revision.published_app_id) != str(ctx.app.id):
            raise PermissionError("Checkpoint revision does not belong to this app")

        current = await db.get(PublishedAppRevision, ctx.app.current_draft_revision_id)
        if current is None:
            raise ValueError("Current draft revision not found")

        files = dict(checkpoint_revision.files or {})
        entry_file = checkpoint_revision.entry_file
        restored = await _create_draft_revision_from_files(
            db=db,
            app=ctx.app,
            current=current,
            actor_id=ctx.actor_id,
            files=files,
            entry_file=entry_file,
        )

        await ctx.runtime_service.sync_session(
            app=ctx.app,
            revision=restored,
            user_id=ctx.actor_id,
            files=files,
            entry_file=entry_file,
        )

        ctx.run.result_revision_id = restored.id
        ctx.run.checkpoint_revision_id = checkpoint_revision.id
        await db.commit()
        return {
            "restored_revision_id": str(restored.id),
            "from_checkpoint_revision_id": str(checkpoint_revision.id),
            "entry_file": entry_file,
            "file_count": len(files),
        }


CODING_AGENT_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "List Files",
        "slug": "list_files",
        "function_name": "coding_agent_list_files",
        "description": "List editable files in the app coding sandbox.",
        "timeout_s": 15,
        "is_pure": True,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Read File",
        "slug": "read_file",
        "function_name": "coding_agent_read_file",
        "description": "Read a file from the app coding sandbox.",
        "timeout_s": 20,
        "is_pure": True,
        "schema": {
            "input": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Search Code",
        "slug": "search_code",
        "function_name": "coding_agent_search_code",
        "description": "Search for text across sandbox files.",
        "timeout_s": 20,
        "is_pure": True,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["query"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Write File",
        "slug": "write_file",
        "function_name": "coding_agent_write_file",
        "description": "Create or overwrite a file in the sandbox.",
        "timeout_s": 25,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Rename File",
        "slug": "rename_file",
        "function_name": "coding_agent_rename_file",
        "description": "Rename a file in the sandbox.",
        "timeout_s": 25,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "from_path": {"type": "string"},
                    "to_path": {"type": "string"},
                },
                "required": ["from_path", "to_path"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Delete File",
        "slug": "delete_file",
        "function_name": "coding_agent_delete_file",
        "description": "Delete a file from the sandbox.",
        "timeout_s": 20,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Snapshot Files",
        "slug": "snapshot_files",
        "function_name": "coding_agent_snapshot_files",
        "description": "Snapshot all sandbox files.",
        "timeout_s": 30,
        "is_pure": True,
        "schema": {
            "input": {"type": "object", "additionalProperties": True},
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Run Targeted Tests",
        "slug": "run_targeted_tests",
        "function_name": "coding_agent_run_targeted_tests",
        "description": "Run allowlisted test commands inside sandbox.",
        "timeout_s": 300,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "command": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Build Worker Precheck",
        "slug": "build_worker_precheck",
        "function_name": "coding_agent_build_worker_precheck",
        "description": "Run allowlisted build precheck command in sandbox.",
        "timeout_s": 360,
        "is_pure": False,
        "schema": {
            "input": {"type": "object", "additionalProperties": True},
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Create Checkpoint",
        "slug": "create_checkpoint",
        "function_name": "coding_agent_create_checkpoint",
        "description": "Create a durable checkpoint revision from current sandbox files.",
        "timeout_s": 60,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "entry_file": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Restore Checkpoint",
        "slug": "restore_checkpoint",
        "function_name": "coding_agent_restore_checkpoint",
        "description": "Restore sandbox/app draft from a checkpoint revision.",
        "timeout_s": 60,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "checkpoint_revision_id": {"type": "string"},
                },
                "required": ["checkpoint_revision_id"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
]


async def ensure_coding_agent_tools(db: AsyncSession) -> list[str]:
    tool_ids: list[str] = []
    for spec in CODING_AGENT_TOOL_SPECS:
        result = await db.execute(
            select(ToolRegistry).where(
                and_(
                    ToolRegistry.tenant_id.is_(None),
                    ToolRegistry.slug == spec["slug"],
                )
            )
        )
        tool = result.scalar_one_or_none()
        config_schema = {
            "implementation": {
                "type": "function",
                "function_name": spec["function_name"],
            },
            "execution": {
                "timeout_s": int(spec["timeout_s"]),
                "is_pure": bool(spec["is_pure"]),
                "concurrency_group": CODING_AGENT_TOOL_NAMESPACE,
                "max_concurrency": 1,
            },
        }
        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name=spec["name"],
                slug=spec["slug"],
                description=spec["description"],
                scope=ToolDefinitionScope.GLOBAL,
                schema=spec["schema"],
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=ToolImplementationType.FUNCTION,
                artifact_id=None,
                artifact_version=None,
                builtin_key=None,
                builtin_template_id=None,
                is_builtin_template=False,
                is_active=True,
                is_system=True,
                published_at=datetime.now(timezone.utc),
            )
            db.add(tool)
            await db.flush()
        else:
            tool.name = spec["name"]
            tool.description = spec["description"]
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = spec["schema"]
            tool.config_schema = config_schema
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = ToolImplementationType.FUNCTION
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.now(timezone.utc)
        tool_ids.append(str(tool.id))

    await db.flush()
    return tool_ids
