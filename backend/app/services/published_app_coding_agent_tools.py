from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from fastapi import HTTPException
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


def _build_verification_plan(changed_paths: list[str]) -> dict[str, Any]:
    normalized = [str(path) for path in changed_paths if isinstance(path, str) and path.strip()]
    plan: dict[str, Any] = {"changed_paths": normalized[:40], "recommended_commands": []}
    if not normalized:
        return plan
    extensions = {path.rsplit(".", 1)[-1].lower() for path in normalized if "." in path}
    if any(ext in {"ts", "tsx", "js", "jsx"} for ext in extensions):
        plan["recommended_commands"].append(["npm", "run", "typecheck"])
        plan["recommended_commands"].append(["npm", "run", "test", "--", "--run", "--passWithNoTests"])
    if any(ext in {"py"} for ext in extensions):
        plan["recommended_commands"].append(["pytest", "-q"])
    if any(path.endswith((".css", ".scss", ".tsx", ".jsx")) for path in normalized):
        plan["recommended_commands"].append(["npm", "run", "build"])
    return plan


def _normalize_command_payload(command: Any) -> list[str]:
    if command is None:
        return ["npm", "run", "test", "--", "--run", "--passWithNoTests"]
    if isinstance(command, list):
        normalized = [str(token) for token in command if str(token).strip()]
        if not normalized:
            raise ValueError("command list cannot be empty")
        return normalized
    if isinstance(command, str):
        parsed = [token for token in shlex.split(command.strip()) if token.strip()]
        if not parsed:
            raise ValueError("command string cannot be empty")
        return parsed
    raise ValueError("command must be an array of tokens or a shell-style string")


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
        session = await runtime_service.ensure_active_session(
            app=app,
            revision=revision,
            user_id=actor_id,
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


def _coerce_string_arg(payload: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for key in aliases:
        value = payload.get(key)
        if value is None:
            continue
        text = value.strip() if isinstance(value, str) else str(value).strip()
        if text:
            return text
    return ""


def _parse_json_object(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    candidates: list[str] = [text]

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1].strip())

    trimmed = text.strip().rstrip(",")
    if not trimmed.startswith("{") and ":" in trimmed:
        candidates.append("{" + trimmed.strip("{} \t\r\n,") + "}")

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            parsed = None
        if isinstance(parsed, str):
            inner = parsed.strip()
            if inner and inner != candidate:
                try:
                    parsed = json.loads(inner)
                except Exception:
                    parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_loose_kv_string(raw: Any, aliases: tuple[str, ...], *, multiline_tail: bool = False) -> str:
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    if not text:
        return ""
    alias_group = "|".join(re.escape(alias) for alias in aliases)
    candidate_texts = [text]
    unescaped = text.replace('\\"', '"').replace("\\'", "'")
    if unescaped != text:
        candidate_texts.append(unescaped)

    for candidate in candidate_texts:
        for quote in ('"', "'"):
            quoted_match = re.search(
                rf"(?is)(?:{alias_group})(?:\s|\\?{re.escape(quote)})*[:=](?:\s|\\?{re.escape(quote)})*((?:\\.|[^{re.escape(quote)}])*)",
                candidate,
            )
            if quoted_match:
                value = quoted_match.group(1).strip()
                if value:
                    return value

        bare_match = re.search(
            rf"(?is)(?:{alias_group})(?:\s|\\?['\"])*[:=]\s*([^\s,}}]+)",
            candidate,
        )
        if bare_match:
            value = bare_match.group(1).strip().strip("'\"")
            if value:
                return value

        if multiline_tail:
            tail_match = re.search(rf"(?is)(?:{alias_group})(?:\s|\\?['\"])*[:=]\s*(.+)$", candidate)
            if tail_match:
                value = tail_match.group(1).strip().rstrip("}").strip("'\"")
                if value:
                    return value
    return ""


def _canonical_arg_key(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _coerce_nested_string_arg(
    payload: dict[str, Any],
    aliases: tuple[str, ...],
    *,
    max_depth: int = 5,
) -> str:
    alias_tokens = {_canonical_arg_key(alias) for alias in aliases}
    queue: list[tuple[Any, int]] = [(payload, 0)]
    seen: set[int] = set()

    while queue:
        current, depth = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)

        if isinstance(current, dict):
            for key, value in current.items():
                if _canonical_arg_key(str(key)) not in alias_tokens:
                    continue
                if isinstance(value, str):
                    parsed_value = _parse_json_object(value)
                    if isinstance(parsed_value, dict):
                        queue.append((parsed_value, depth + 1))
                if isinstance(value, str):
                    text = value.strip()
                elif isinstance(value, (int, float)):
                    text = str(value)
                else:
                    text = ""
                if text:
                    return text
                if isinstance(value, dict):
                    nested_path = _coerce_string_arg(value, ("path", "file_path", "filepath", "filePath"))
                    if nested_path:
                        return nested_path
                if isinstance(value, (dict, list, tuple)) and depth < max_depth:
                    queue.append((value, depth + 1))
            if depth >= max_depth:
                continue
            for value in current.values():
                if isinstance(value, str):
                    parsed_value = _parse_json_object(value)
                    if isinstance(parsed_value, dict):
                        queue.append((parsed_value, depth + 1))
                if isinstance(value, (dict, list, tuple)):
                    queue.append((value, depth + 1))
            continue

        if isinstance(current, (list, tuple)) and depth < max_depth:
            for value in current:
                if isinstance(value, str):
                    parsed_value = _parse_json_object(value)
                    if isinstance(parsed_value, dict):
                        queue.append((parsed_value, depth + 1))
                if isinstance(value, (dict, list, tuple)):
                    queue.append((value, depth + 1))

    return ""


def _resolve_string_arg(payload: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for wrapper_key in ("input", "args", "parameters", "payload", "data", "arguments", "value"):
        wrapper_value = payload.get(wrapper_key)
        if isinstance(wrapper_value, str):
            parsed_wrapper = _parse_json_object(wrapper_value)
            if isinstance(parsed_wrapper, dict):
                payload = dict(payload)
                payload[wrapper_key] = parsed_wrapper
                break

    direct = _coerce_string_arg(payload, aliases)
    if direct:
        return direct
    return _coerce_nested_string_arg(payload, aliases)


def _resolve_path_arg(payload: dict[str, Any]) -> str:
    aliases = (
        "path",
        "file_path",
        "filepath",
        "filePath",
        "file_name",
        "fileName",
        "filename",
        "file",
        "target_path",
        "targetPath",
        "target_file",
        "targetFile",
        "relative_path",
        "relativePath",
        "pathname",
    )
    resolved = _resolve_string_arg(
        payload,
        aliases,
    )
    if resolved:
        return resolved
    return _extract_loose_kv_string(payload.get("value"), aliases)


def _resolve_from_path_arg(payload: dict[str, Any]) -> str:
    aliases = (
        "from_path",
        "fromPath",
        "source_path",
        "sourcePath",
        "old_path",
        "oldPath",
        "from",
        "source",
    )
    resolved = _resolve_string_arg(
        payload,
        aliases,
    )
    if resolved:
        return resolved
    return _extract_loose_kv_string(payload.get("value"), aliases)


def _resolve_to_path_arg(payload: dict[str, Any]) -> str:
    aliases = (
        "to_path",
        "toPath",
        "destination_path",
        "destinationPath",
        "dest_path",
        "destPath",
        "new_path",
        "newPath",
        "to",
        "destination",
    )
    resolved = _resolve_string_arg(
        payload,
        aliases,
    )
    if resolved:
        return resolved
    return _extract_loose_kv_string(payload.get("value"), aliases)


def _resolve_content_arg(payload: dict[str, Any]) -> str:
    aliases = (
        "content",
        "contents",
        "text",
        "body",
        "code",
        "source",
        "file_content",
        "fileContent",
        "new_content",
        "newContent",
    )
    resolved = _resolve_string_arg(
        payload,
        aliases,
    )
    if resolved:
        return resolved
    return _extract_loose_kv_string(payload.get("value"), aliases, multiline_tail=True)


def _resolve_patch_arg(payload: dict[str, Any]) -> str:
    aliases = (
        "patch",
        "diff",
        "unified_diff",
        "unifiedDiff",
        "patch_text",
        "patchText",
    )
    resolved = _resolve_string_arg(payload, aliases)
    if resolved:
        return resolved
    return _extract_loose_kv_string(payload.get("value"), aliases, multiline_tail=True)


def _resolve_int_arg(payload: dict[str, Any], aliases: tuple[str, ...], default: int | None = None) -> int | None:
    raw = _resolve_string_arg(payload, aliases)
    if not raw:
        if default is None:
            return None
        return int(default)
    try:
        return int(raw)
    except Exception:
        if default is None:
            return None
        return int(default)


def _resolve_bool_arg(payload: dict[str, Any], aliases: tuple[str, ...], default: bool = False) -> bool:
    raw = _resolve_string_arg(payload, aliases)
    if not raw:
        return bool(default)
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _resolve_expected_hashes(payload: dict[str, Any]) -> dict[str, str]:
    candidate = payload.get("expected_hashes")
    if not isinstance(candidate, dict):
        preconditions = payload.get("preconditions")
        if isinstance(preconditions, dict):
            candidate = preconditions.get("expected_hashes")
    if not isinstance(candidate, dict):
        return {}
    expected: dict[str, str] = {}
    for key, value in candidate.items():
        if not isinstance(key, str):
            continue
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        expected[key] = text
    return expected


def _snake_to_camel(field: str) -> str:
    parts = [token for token in str(field).split("_") if token]
    if not parts:
        return str(field)
    return parts[0] + "".join(token.capitalize() for token in parts[1:])


def _resolve_required_string_field(payload: dict[str, Any], field: str) -> str:
    value_raw = payload.get("value")
    if field == "path":
        resolved = _resolve_path_arg(payload)
        if resolved:
            return resolved
        return _extract_loose_kv_string(
            value_raw,
            (
                "path",
                "file_path",
                "filepath",
                "filePath",
                "file_name",
                "fileName",
                "filename",
                "file",
                "target_path",
                "targetPath",
                "target_file",
                "targetFile",
                "relative_path",
                "relativePath",
                "pathname",
            ),
        )
    if field == "from_path":
        resolved = _resolve_from_path_arg(payload)
        if resolved:
            return resolved
        return _extract_loose_kv_string(
            value_raw,
            ("from_path", "fromPath", "source_path", "sourcePath", "old_path", "oldPath", "from", "source"),
        )
    if field == "to_path":
        resolved = _resolve_to_path_arg(payload)
        if resolved:
            return resolved
        return _extract_loose_kv_string(
            value_raw,
            ("to_path", "toPath", "destination_path", "destinationPath", "dest_path", "destPath", "new_path", "newPath", "to", "destination"),
        )
    if field == "checkpoint_revision_id":
        resolved = _resolve_string_arg(payload, ("checkpoint_revision_id", "checkpoint_id", "checkpointRevisionId"))
        if resolved:
            return resolved
        return _extract_loose_kv_string(value_raw, ("checkpoint_revision_id", "checkpoint_id", "checkpointRevisionId"))
    if field == "content":
        return _resolve_content_arg(payload)
    if field == "patch":
        return _resolve_patch_arg(payload)
    aliases = (
        field,
        _snake_to_camel(field),
        field.replace("_", ""),
    )
    resolved = _resolve_string_arg(payload, aliases)
    if resolved:
        return resolved
    return _extract_loose_kv_string(value_raw, aliases, multiline_tail=(field == "content"))


def validate_coding_agent_required_fields(
    function_name: str,
    payload: dict[str, Any] | None,
) -> list[str]:
    tool_payload = payload if isinstance(payload, dict) else {}
    spec = next((item for item in CODING_AGENT_TOOL_SPECS if item.get("function_name") == function_name), None)
    if not isinstance(spec, dict):
        return []
    schema = spec.get("schema")
    if not isinstance(schema, dict):
        return []
    input_schema = schema.get("input")
    if not isinstance(input_schema, dict):
        return []
    required = input_schema.get("required")
    if not isinstance(required, list):
        return []
    properties = input_schema.get("properties")
    property_map = properties if isinstance(properties, dict) else {}

    missing: list[str] = []
    for field in required:
        if not isinstance(field, str):
            continue
        expected = property_map.get(field) if isinstance(property_map.get(field), dict) else {}
        expected_type = expected.get("type")
        if expected_type == "string":
            candidate = _resolve_required_string_field(tool_payload, field)
            text = candidate if isinstance(candidate, str) else (str(candidate) if candidate is not None else "")
            if not text.strip():
                missing.append(field)
            continue

        if field == "path":
            candidate = _resolve_path_arg(tool_payload)
        elif field == "from_path":
            candidate = _resolve_from_path_arg(tool_payload)
        elif field == "to_path":
            candidate = _resolve_to_path_arg(tool_payload)
        elif field == "checkpoint_revision_id":
            candidate = _resolve_string_arg(tool_payload, ("checkpoint_revision_id", "checkpoint_id"))
        else:
            candidate = tool_payload.get(field)

        if candidate is None:
            missing.append(field)
    return missing


def normalize_coding_agent_tool_payload(
    function_name: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    tool_payload = dict(payload or {}) if isinstance(payload, dict) else {}
    spec = next((item for item in CODING_AGENT_TOOL_SPECS if item.get("function_name") == function_name), None)
    if not isinstance(spec, dict):
        return tool_payload
    schema = spec.get("schema")
    if not isinstance(schema, dict):
        return tool_payload
    input_schema = schema.get("input")
    if not isinstance(input_schema, dict):
        return tool_payload
    properties = input_schema.get("properties")
    property_map = properties if isinstance(properties, dict) else {}

    for field, raw_spec in property_map.items():
        if not isinstance(field, str) or not isinstance(raw_spec, dict):
            continue
        if raw_spec.get("type") != "string":
            continue
        existing = tool_payload.get(field)
        if isinstance(existing, str) and existing.strip():
            continue
        resolved = _resolve_required_string_field(tool_payload, field)
        if isinstance(resolved, str) and resolved.strip():
            tool_payload[field] = resolved
    return tool_payload


def normalize_coding_agent_tool_exception(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("detail") or "Tool execution failed")
            payload: dict[str, Any] = {
                "error": message,
                "code": str(detail.get("code") or "TOOL_EXECUTION_FAILED"),
            }
            field = detail.get("field")
            if field:
                payload["field"] = str(field)
            return payload
        return {"error": str(detail or "Tool execution failed"), "code": "TOOL_EXECUTION_FAILED"}

    if isinstance(exc, PermissionError):
        return {"error": str(exc) or "Tool policy violation", "code": "BUILDER_PATCH_POLICY_VIOLATION"}

    return {"error": str(exc) or "Tool execution failed", "code": "TOOL_EXECUTION_FAILED"}


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
    path = _normalize_builder_path(_resolve_path_arg(tool_payload))
    _assert_builder_path_allowed(path)
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.read_file(sandbox_id=ctx.sandbox_id, path=path)
        await db.commit()
        return result


@register_tool_function("coding_agent_read_file_range")
async def coding_agent_read_file_range(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_builder_path(_resolve_path_arg(tool_payload))
    _assert_builder_path_allowed(path)
    start_line = _resolve_int_arg(tool_payload, ("start_line", "startLine"))
    end_line = _resolve_int_arg(tool_payload, ("end_line", "endLine"))
    context_before = _resolve_int_arg(tool_payload, ("context_before", "contextBefore"), default=0) or 0
    context_after = _resolve_int_arg(tool_payload, ("context_after", "contextAfter"), default=0) or 0
    max_bytes = _resolve_int_arg(tool_payload, ("max_bytes", "maxBytes"), default=12000) or 12000
    with_line_numbers = _resolve_bool_arg(
        tool_payload,
        ("with_line_numbers", "withLineNumbers", "line_numbers", "lineNumbers"),
        default=False,
    )
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.read_file_range(
            sandbox_id=ctx.sandbox_id,
            path=path,
            start_line=start_line,
            end_line=end_line,
            context_before=context_before,
            context_after=context_after,
            max_bytes=max_bytes,
            with_line_numbers=with_line_numbers,
        )
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


@register_tool_function("coding_agent_workspace_index")
async def coding_agent_workspace_index(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    limit = _resolve_int_arg(tool_payload, ("limit",), default=300) or 300
    query = _resolve_string_arg(tool_payload, ("query", "search", "needle")) or None
    max_symbols = _resolve_int_arg(
        tool_payload,
        ("max_symbols_per_file", "maxSymbolsPerFile"),
        default=16,
    ) or 16
    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.workspace_index(
            sandbox_id=ctx.sandbox_id,
            limit=limit,
            query=query,
            max_symbols_per_file=max_symbols,
        )
        await db.commit()
        return result


@register_tool_function("coding_agent_collect_context")
async def coding_agent_collect_context(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    query = _resolve_string_arg(tool_payload, ("query", "q", "search_query", "needle")).strip()
    if not query:
        raise ValueError("query is required")

    max_snippets = _resolve_int_arg(tool_payload, ("max_snippets", "maxSnippets"), default=10) or 10
    max_total_bytes = _resolve_int_arg(tool_payload, ("max_total_bytes", "maxTotalBytes"), default=12000) or 12000
    context_before = _resolve_int_arg(tool_payload, ("context_before", "contextBefore"), default=6) or 6
    context_after = _resolve_int_arg(tool_payload, ("context_after", "contextAfter"), default=6) or 6

    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        search = await ctx.runtime_service.client.search_code(
            sandbox_id=ctx.sandbox_id,
            query=query,
            max_results=max(20, max_snippets * 4),
        )
        matches = search.get("matches") if isinstance(search.get("matches"), list) else []
        snippets: list[dict[str, Any]] = []
        consumed = 0
        used_ranges: set[tuple[str, int]] = set()
        for match in matches:
            if len(snippets) >= max_snippets or consumed >= max_total_bytes:
                break
            if not isinstance(match, dict):
                continue
            path_value = str(match.get("path") or "").strip()
            line_no = int(match.get("line") or 1)
            if not path_value:
                continue
            dedupe_key = (path_value, line_no)
            if dedupe_key in used_ranges:
                continue
            used_ranges.add(dedupe_key)
            remaining = max_total_bytes - consumed
            if remaining < 256:
                break
            range_payload = await ctx.runtime_service.client.read_file_range(
                sandbox_id=ctx.sandbox_id,
                path=path_value,
                start_line=line_no,
                end_line=line_no,
                context_before=context_before,
                context_after=context_after,
                max_bytes=remaining,
                with_line_numbers=True,
            )
            content = str(range_payload.get("content") or "")
            size_bytes = len(content.encode("utf-8"))
            consumed += size_bytes
            snippets.append(
                {
                    "path": path_value,
                    "line": line_no,
                    "score": max(1, 100 - len(snippets)),
                    "content": content,
                    "size_bytes": size_bytes,
                    "recommended_for_prompt": consumed <= max_total_bytes,
                }
            )
        await db.commit()
        return {
            "query": query,
            "snippets": snippets,
            "snippet_count": len(snippets),
            "consumed_bytes": consumed,
            "max_total_bytes": max_total_bytes,
            "compacted": consumed >= max_total_bytes or len(snippets) >= max_snippets,
        }


@register_tool_function("coding_agent_apply_patch")
async def coding_agent_apply_patch(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    patch = _resolve_patch_arg(tool_payload)
    if not patch:
        raise ValueError("patch is required")

    options = {
        "strip": _resolve_int_arg(tool_payload, ("strip",), default=1) or 1,
        "atomic": _resolve_bool_arg(tool_payload, ("atomic",), default=True),
        "allow_create": _resolve_bool_arg(tool_payload, ("allow_create", "allowCreate"), default=True),
        "allow_delete": _resolve_bool_arg(tool_payload, ("allow_delete", "allowDelete"), default=True),
    }
    expected_hashes = _resolve_expected_hashes(tool_payload)
    preconditions: dict[str, Any] = {}
    if expected_hashes:
        preconditions["expected_hashes"] = expected_hashes

    async with get_session() as db:
        ctx = await _resolve_run_tool_context(db, tool_payload)
        result = await ctx.runtime_service.client.apply_patch(
            sandbox_id=ctx.sandbox_id,
            patch=patch,
            options=options,
            preconditions=preconditions,
        )
        if not bool(result.get("ok")):
            failures = result.get("failures") if isinstance(result.get("failures"), list) else []
            refresh_windows: list[dict[str, Any]] = []
            for failure in failures[:4]:
                if not isinstance(failure, dict):
                    continue
                path_value = failure.get("path")
                refresh = failure.get("recommended_refresh")
                if not isinstance(path_value, str) or not isinstance(refresh, dict):
                    continue
                start_line = int(refresh.get("start_line") or 1)
                end_line = int(refresh.get("end_line") or start_line)
                try:
                    window = await ctx.runtime_service.client.read_file_range(
                        sandbox_id=ctx.sandbox_id,
                        path=path_value,
                        start_line=start_line,
                        end_line=end_line,
                        max_bytes=min(int(os.getenv("APPS_CODING_AGENT_READ_RANGE_MAX_BYTES", "12000")), 16000),
                        with_line_numbers=True,
                    )
                except Exception:
                    continue
                refresh_windows.append(window)
            await db.commit()
            return {
                "error": str(result.get("summary") or "Patch apply failed"),
                "code": str(result.get("code") or "PATCH_HUNK_MISMATCH"),
                "result": result,
                "refresh_windows": refresh_windows,
                "failures": failures,
            }
        changed_paths = result.get("applied_files") if isinstance(result.get("applied_files"), list) else []
        verification_plan = _build_verification_plan(changed_paths)
        result["verification_plan"] = verification_plan
        auto_verify_enabled = os.getenv("APPS_CODING_AGENT_AUTO_VERIFY_PATCH", "0").strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
        if auto_verify_enabled:
            verification_runs: list[dict[str, Any]] = []
            timeout_seconds = int(os.getenv("APPS_CODING_AGENT_TEST_TIMEOUT_SECONDS", "240"))
            max_output_bytes = int(os.getenv("APPS_CODING_AGENT_MAX_COMMAND_OUTPUT_BYTES", "12000"))
            for command in verification_plan.get("recommended_commands", [])[:2]:
                if not isinstance(command, list):
                    continue
                normalized_command = [str(token) for token in command if str(token).strip()]
                if not _is_command_allowed(normalized_command):
                    continue
                run_result = await ctx.runtime_service.client.run_command(
                    sandbox_id=ctx.sandbox_id,
                    command=normalized_command,
                    timeout_seconds=timeout_seconds,
                    max_output_bytes=max_output_bytes,
                )
                verification_runs.append(
                    {
                        "command": normalized_command,
                        "code": int(run_result.get("code") or 0),
                        "stdout": run_result.get("stdout"),
                        "stderr": run_result.get("stderr"),
                    }
                )
            if verification_runs:
                result["verification_runs"] = verification_runs
        await db.commit()
        return result


@register_tool_function("coding_agent_write_file")
async def coding_agent_write_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    legacy_write_enabled = os.getenv("APPS_CODING_AGENT_ENABLE_LEGACY_WRITE_FILE", "0").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    if not legacy_write_enabled:
        return {
            "error": "coding_agent_write_file is deprecated and disabled; use coding_agent_apply_patch",
            "code": "LEGACY_WRITE_FILE_DISABLED",
        }
    path = _normalize_builder_path(_resolve_path_arg(tool_payload))
    _assert_builder_path_allowed(path)
    content = _resolve_content_arg(tool_payload)
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
    from_path = _normalize_builder_path(_resolve_from_path_arg(tool_payload))
    to_path = _normalize_builder_path(_resolve_to_path_arg(tool_payload))
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
    path = _normalize_builder_path(_resolve_path_arg(tool_payload))
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
    normalized_command = _normalize_command_payload(command)
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
        "name": "Read File Range",
        "slug": "read_file_range",
        "function_name": "coding_agent_read_file_range",
        "description": "Read a focused line range from a file (with optional context lines).",
        "timeout_s": 20,
        "is_pure": True,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "context_before": {"type": "integer", "minimum": 0, "maximum": 200},
                    "context_after": {"type": "integer", "minimum": 0, "maximum": 200},
                    "max_bytes": {"type": "integer", "minimum": 256, "maximum": 50000},
                    "with_line_numbers": {"type": "boolean"},
                },
                "required": ["path"],
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Workspace Index",
        "slug": "workspace_index",
        "function_name": "coding_agent_workspace_index",
        "description": "Return file metadata index (size, hash, language, symbol outline) for search-first planning.",
        "timeout_s": 30,
        "is_pure": True,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                    "query": {"type": "string"},
                    "max_symbols_per_file": {"type": "integer", "minimum": 1, "maximum": 64},
                },
                "additionalProperties": True,
            },
            "output": {"type": "object", "additionalProperties": True},
        },
    },
    {
        "name": "Collect Context",
        "slug": "collect_context",
        "function_name": "coding_agent_collect_context",
        "description": "Rank and compact query-relevant snippets within a byte budget.",
        "timeout_s": 30,
        "is_pure": True,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_snippets": {"type": "integer", "minimum": 1, "maximum": 40},
                    "max_total_bytes": {"type": "integer", "minimum": 512, "maximum": 80000},
                    "context_before": {"type": "integer", "minimum": 0, "maximum": 60},
                    "context_after": {"type": "integer", "minimum": 0, "maximum": 60},
                },
                "required": ["query"],
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
        "name": "Write File (Deprecated)",
        "slug": "write_file",
        "function_name": "coding_agent_write_file",
        "description": "Legacy full overwrite tool. Disabled by default; use Apply Patch.",
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
        "name": "Apply Patch",
        "slug": "apply_patch",
        "function_name": "coding_agent_apply_patch",
        "description": "Apply unified diff patch with strict context matching and atomic semantics.",
        "timeout_s": 45,
        "is_pure": False,
        "schema": {
            "input": {
                "type": "object",
                "properties": {
                    "patch": {"type": "string"},
                    "strip": {"type": "integer", "minimum": 0, "maximum": 3},
                    "atomic": {"type": "boolean"},
                    "allow_create": {"type": "boolean"},
                    "allow_delete": {"type": "boolean"},
                    "preconditions": {
                        "type": "object",
                        "properties": {
                            "expected_hashes": {"type": "object", "additionalProperties": {"type": "string"}},
                        },
                        "additionalProperties": True,
                    },
                },
                "required": ["patch"],
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
