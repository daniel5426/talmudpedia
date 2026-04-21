from __future__ import annotations

import hashlib

import base64
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    set_tool_management_metadata,
)
from app.services.file_reference_access import with_authorized_file_space as _with_service
from app.services.file_representation_service import inspect_file, read_representation
from app.services.file_spaces.service import FileSpaceService, FileSpaceValidationError
from app.services.tool_function_registry import register_tool_function

READ_FILE_DEFAULT_LINE_WINDOW = 200
READ_FILE_FULL_CONTENT_LINE_THRESHOLD = 300
FILE_SPACE_TOOLSET_ID = "file_space_memory"
FILE_SPACE_TOOLSET_NAME = "File Space Memory"
FILE_SPACE_TOOLSET_DESCRIPTION = (
    "Persistent workspace access for linked file spaces. "
    "Select the full toolset to give the agent the complete file-space memory surface."
)


def _tool_schema(
    *,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "input": {
            "type": "object",
            "properties": properties,
            "required": list(required or []),
            "additionalProperties": False,
        },
        "output": {"type": "object", "additionalProperties": True},
    }


FILE_SPACE_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "builtin_key": "files-list",
        "name": "Files List",
        "description": "List the live tree entries in a linked file space.",
        "function_name": "files_list",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path_prefix": {"type": "string"},
            },
            required=["space_id"],
        ),
    },
    {
        "builtin_key": "files-inspect",
        "name": "Files Inspect",
        "description": "Inspect a linked file and return metadata plus supported deterministic representations.",
        "function_name": "files_inspect",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path": {"type": "string"},
            },
            required=["space_id", "path"],
        ),
    },
    {
        "builtin_key": "files-read",
        "name": "Files Read",
        "description": "Read one text file from a linked file space. Supports bounded line reads and optional numbered output.",
        "function_name": "files_read",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "include_line_numbers": {"type": "boolean"},
            },
            required=["space_id", "path"],
        ),
    },
    {
        "builtin_key": "files-read-representation",
        "name": "Files Read Representation",
        "description": "Read a deterministic structured representation from a linked file.",
        "function_name": "files_read_representation",
        "timeout_s": 60,
        "is_pure": True,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path": {"type": "string"},
                "representation": {"type": "string"},
                "options": {"type": "object", "additionalProperties": True},
            },
            required=["space_id", "path", "representation"],
        ),
    },
    {
        "builtin_key": "files-write",
        "name": "Files Write",
        "description": "Create or replace a text file in a linked file space.",
        "function_name": "files_write",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path": {"type": "string"},
                "content": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            required=["space_id", "path", "content"],
        ),
    },
    {
        "builtin_key": "files-patch-text",
        "name": "Files Patch Text",
        "description": "Replace one exact text segment in a linked text file.",
        "function_name": "files_patch_text",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            required=["space_id", "path", "old_text", "new_text"],
        ),
    },
    {
        "builtin_key": "files-search",
        "name": "Files Search",
        "description": "Search text files in a linked file space and return snippets with surrounding context.",
        "function_name": "files_search",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "query": {"type": "string"},
                "path_prefix": {"type": "string"},
                "max_results": {"type": "integer"},
                "context_before": {"type": "integer"},
                "context_after": {"type": "integer"},
            },
            required=["space_id", "query"],
        ),
    },
    {
        "builtin_key": "files-mkdir",
        "name": "Files Mkdir",
        "description": "Create a directory path in a linked file space.",
        "function_name": "files_mkdir",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={"space_id": {"type": "string"}, "path": {"type": "string"}},
            required=["space_id", "path"],
        ),
    },
    {
        "builtin_key": "files-move",
        "name": "Files Move",
        "description": "Rename or move a file or directory in a linked file space.",
        "function_name": "files_move",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "from_path": {"type": "string"},
                "to_path": {"type": "string"},
            },
            required=["space_id", "from_path", "to_path"],
        ),
    },
    {
        "builtin_key": "files-delete",
        "name": "Files Delete",
        "description": "Delete a file or directory from a linked file space.",
        "function_name": "files_delete",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={"space_id": {"type": "string"}, "path": {"type": "string"}},
            required=["space_id", "path"],
        ),
    },
    {
        "builtin_key": "files-upload-blob",
        "name": "Files Upload Blob",
        "description": "Create or replace a binary file in a linked file space from base64 content.",
        "function_name": "files_upload_blob",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={
                "space_id": {"type": "string"},
                "path": {"type": "string"},
                "content_base64": {"type": "string"},
                "content_type": {"type": "string"},
            },
            required=["space_id", "path", "content_base64"],
        ),
    },
    {
        "builtin_key": "files-download-meta",
        "name": "Files Download Meta",
        "description": "Return current metadata for a file, including its revision and download endpoint path.",
        "function_name": "files_download_meta",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={"space_id": {"type": "string"}, "path": {"type": "string"}},
            required=["space_id", "path"],
        ),
    },
]


def _file_space_toolset_payload(member_ids: list[str]) -> dict[str, Any]:
    return {
        "id": FILE_SPACE_TOOLSET_ID,
        "name": FILE_SPACE_TOOLSET_NAME,
        "description": FILE_SPACE_TOOLSET_DESCRIPTION,
        "selection_mode": "expand_to_members",
        "member_ids": list(member_ids),
    }


def _normalize_path_prefix(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return FileSpaceService.normalize_path(raw)


def _require_text(value: Any, field: str) -> str:
    normalized = str(value or "")
    if not normalized:
        raise FileSpaceValidationError(f"{field} is required")
    return normalized


def _slice_text_content(
    *,
    path: str,
    content: str,
    start_line_raw: Any,
    end_line_raw: Any,
    include_line_numbers: bool,
) -> dict[str, Any]:
    lines = content.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        start_line = 1
        end_line = 0
    elif start_line_raw is not None and end_line_raw is not None:
        start_line = int(start_line_raw)
        end_line = int(end_line_raw)
    elif start_line_raw is not None:
        start_line = int(start_line_raw)
        end_line = min(total_lines, start_line + READ_FILE_DEFAULT_LINE_WINDOW - 1)
    elif end_line_raw is not None:
        end_line = int(end_line_raw)
        start_line = max(1, end_line - READ_FILE_DEFAULT_LINE_WINDOW + 1)
    elif total_lines <= READ_FILE_FULL_CONTENT_LINE_THRESHOLD:
        start_line = 1
        end_line = total_lines
    else:
        start_line = 1
        end_line = min(total_lines, READ_FILE_DEFAULT_LINE_WINDOW)
    if total_lines > 0 and (start_line < 1 or end_line < start_line or end_line > total_lines):
        raise FileSpaceValidationError("start_line and end_line must define a valid inclusive range")
    selected_lines = [] if total_lines == 0 else lines[start_line - 1 : end_line]
    response: dict[str, Any] = {
        "path": path,
        "content": "\n".join(selected_lines),
        "total_lines": total_lines,
        "start_line": start_line,
        "end_line": end_line,
        "truncated": total_lines > 0 and (start_line > 1 or end_line < total_lines),
    }
    if include_line_numbers:
        response["numbered_content"] = "\n".join(
            f"{line_no}: {line}"
            for line_no, line in enumerate(selected_lines, start=start_line)
        )
    return response


async def _list_filtered_entries(
    service: FileSpaceService,
    *,
    organization_id: UUID,
    project_id: UUID,
    space_id: UUID,
    path_prefix: str | None,
) -> list[Any]:
    entries = await service.list_entries(
        organization_id=organization_id,
        project_id=project_id,
        space_id=space_id,
    )
    if not path_prefix:
        return entries
    prefix = f"{path_prefix}/"
    return [entry for entry in entries if entry.path == path_prefix or entry.path.startswith(prefix)]


@register_tool_function("files_list")
async def files_list(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        path_prefix = _normalize_path_prefix(
            kwargs["tool_payload"].get("path_prefix") or kwargs["tool_payload"].get("pathPrefix")
        )
        entries = await _list_filtered_entries(
            kwargs["service"],
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path_prefix=path_prefix,
        )
        serialized = [FileSpaceService.serialize_entry(entry) for entry in entries]
        file_count = sum(1 for entry in entries if getattr(entry.entry_type, "value", entry.entry_type) == "file")
        directory_count = len(entries) - file_count
        return {
            "items": serialized,
            "entries": serialized,
            "file_count": file_count,
            "directory_count": directory_count,
            "path_prefix": path_prefix,
        }

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_inspect")
async def files_inspect(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        return await inspect_file(
            kwargs["authorized_context"],
            path=str(kwargs["tool_payload"].get("path") or ""),
        )

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_read")
async def files_read(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        payload = await read_representation(
            kwargs["authorized_context"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            representation="raw_text",
            options={
                "start_line": kwargs["tool_payload"].get("start_line") or kwargs["tool_payload"].get("startLine"),
                "end_line": kwargs["tool_payload"].get("end_line") or kwargs["tool_payload"].get("endLine"),
                "include_line_numbers": kwargs["tool_payload"].get("include_line_numbers")
                or kwargs["tool_payload"].get("includeLineNumbers"),
            },
        )
        return {
            key: value
            for key, value in payload.items()
            if key != "representation"
        }

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_read_representation")
async def files_read_representation(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        return await read_representation(
            kwargs["authorized_context"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            representation=str(kwargs["tool_payload"].get("representation") or ""),
            options=kwargs["tool_payload"].get("options"),
        )

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_write")
async def files_write(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry, revision = await kwargs["service"].write_text_file(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            content=str(kwargs["tool_payload"].get("content") or ""),
            mime_type=str(kwargs["tool_payload"].get("mime_type") or "").strip() or None,
            user_id=kwargs["user_id"],
            run_id=kwargs["run_id"],
        )
        await kwargs["db"].refresh(entry)
        await kwargs["db"].refresh(revision)
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_patch_text")
async def files_patch_text(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        path = str(kwargs["tool_payload"].get("path") or "")
        old_text = _require_text(
            kwargs["tool_payload"].get("old_text") or kwargs["tool_payload"].get("oldText"),
            "old_text",
        )
        new_text = str(kwargs["tool_payload"].get("new_text") or kwargs["tool_payload"].get("newText") or "")
        start_line_raw = kwargs["tool_payload"].get("start_line") or kwargs["tool_payload"].get("startLine")
        end_line_raw = kwargs["tool_payload"].get("end_line") or kwargs["tool_payload"].get("endLine")
        if (start_line_raw is None) != (end_line_raw is None):
            raise FileSpaceValidationError("start_line and end_line must be provided together")

        _entry, _revision, content = await kwargs["service"].read_text_file(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=path,
        )
        if start_line_raw is not None:
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)
            start_line = int(start_line_raw)
            end_line = int(end_line_raw)
            if total_lines == 0 or start_line < 1 or end_line < start_line or end_line > total_lines:
                raise FileSpaceValidationError("start_line and end_line must define a valid inclusive range")
            slice_text = "".join(lines[start_line - 1 : end_line])
            occurrences = slice_text.count(old_text)
            if occurrences == 0:
                raise FileSpaceValidationError("old_text was not found in the selected range")
            if occurrences > 1:
                raise FileSpaceValidationError(
                    "old_text matched multiple times in the selected range; provide a narrower range or a more specific old_text"
                )
            replaced_slice = slice_text.replace(old_text, new_text, 1)
            updated_content = "".join(lines[: start_line - 1]) + replaced_slice + "".join(lines[end_line:])
        else:
            occurrences = content.count(old_text)
            if occurrences == 0:
                raise FileSpaceValidationError("old_text was not found in the file")
            if occurrences > 1:
                raise FileSpaceValidationError(
                    "old_text matched multiple times in the file; provide start_line/end_line or a more specific old_text"
                )
            updated_content = content.replace(old_text, new_text, 1)
        if content.endswith("\n") and updated_content and not updated_content.endswith("\n"):
            updated_content += "\n"

        entry, revision = await kwargs["service"].write_text_file(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=path,
            content=updated_content,
            user_id=kwargs["user_id"],
            run_id=kwargs["run_id"],
        )
        await kwargs["db"].refresh(entry)
        await kwargs["db"].refresh(revision)
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
            "path": path,
            "start_line": start_line_raw,
            "end_line": end_line_raw,
        }

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_search")
async def files_search(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        query = _require_text(kwargs["tool_payload"].get("query") or kwargs["tool_payload"].get("text"), "query")
        path_prefix = _normalize_path_prefix(
            kwargs["tool_payload"].get("path_prefix") or kwargs["tool_payload"].get("pathPrefix")
        )
        max_results = max(1, min(int(kwargs["tool_payload"].get("max_results") or 20), 100))
        context_before = max(
            0,
            min(int(kwargs["tool_payload"].get("context_before") or kwargs["tool_payload"].get("contextBefore") or 0), 20),
        )
        context_after = max(
            0,
            min(int(kwargs["tool_payload"].get("context_after") or kwargs["tool_payload"].get("contextAfter") or 0), 20),
        )
        entries = await _list_filtered_entries(
            kwargs["service"],
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path_prefix=path_prefix,
        )
        matches: list[dict[str, Any]] = []
        for entry in entries:
            if getattr(entry.entry_type, "value", entry.entry_type) != "file" or not bool(entry.is_text):
                continue
            _entry, _revision, content = await kwargs["service"].read_text_file(
                organization_id=kwargs["organization_id"],
                project_id=kwargs["project_id"],
                space_id=kwargs["space_id"],
                path=entry.path,
            )
            file_lines = content.splitlines()
            total_lines = len(file_lines)
            for index, line in enumerate(file_lines, start=1):
                if query.lower() not in line.lower():
                    continue
                snippet_start = max(1, index - context_before)
                snippet_end = min(total_lines, index + context_after)
                matches.append(
                    {
                        "path": entry.path,
                        "name": PurePosixPath(entry.path).name or entry.path,
                        "line": index,
                        "content": line,
                        "start_line": snippet_start,
                        "end_line": snippet_end,
                        "snippet": "\n".join(file_lines[snippet_start - 1 : snippet_end]),
                    }
                )
                if len(matches) >= max_results:
                    return {"query": query, "matches": matches, "path_prefix": path_prefix}
        return {"query": query, "matches": matches, "path_prefix": path_prefix}

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_mkdir")
async def files_mkdir(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry = await kwargs["service"].mkdir(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            user_id=kwargs["user_id"],
        )
        await kwargs["db"].refresh(entry)
        return {"entry": FileSpaceService.serialize_entry(entry)}

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_move")
async def files_move(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entries = await kwargs["service"].move_entry(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            from_path=str(kwargs["tool_payload"].get("from_path") or ""),
            to_path=str(kwargs["tool_payload"].get("to_path") or ""),
            user_id=kwargs["user_id"],
        )
        for entry in entries:
            await kwargs["db"].refresh(entry)
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_delete")
async def files_delete(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entries = await kwargs["service"].delete_entry(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            user_id=kwargs["user_id"],
        )
        for entry in entries:
            await kwargs["db"].refresh(entry)
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_upload_blob")
async def files_upload_blob(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        raw = str(kwargs["tool_payload"].get("content_base64") or "")
        try:
            content = base64.b64decode(raw.encode("ascii"), validate=True)
        except Exception as exc:
            raise FileSpaceValidationError("content_base64 must be valid base64") from exc
        entry, revision = await kwargs["service"].upload_file(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            payload=content,
            content_type=str(kwargs["tool_payload"].get("content_type") or "").strip() or None,
            user_id=kwargs["user_id"],
            run_id=kwargs["run_id"],
        )
        await kwargs["db"].refresh(entry)
        await kwargs["db"].refresh(revision)
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_download_meta")
async def files_download_meta(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry, revision = await kwargs["service"].read_entry(
            organization_id=kwargs["organization_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
        )
        if revision is None:
            raise FileSpaceValidationError("entry is not a file")
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
            "download_endpoint": f"/admin/files/{kwargs['space_id']}/entries/download?path={entry.path}",
        }

    return await _with_service(payload, write=False, handler=_handler)


def _system_tool_row_key(builtin_key: str) -> str:
    digest = hashlib.sha1(builtin_key.encode("utf-8")).hexdigest()[:24]
    return f"sys-tool-{digest}"


async def ensure_file_space_tools(db: AsyncSession) -> list[str]:
    tool_ids: list[str] = []
    tool_rows: list[ToolRegistry] = []
    for spec in FILE_SPACE_TOOL_SPECS:
        system_slug = _system_tool_row_key(spec["builtin_key"])
        result = await db.execute(
            select(ToolRegistry).where(
                ToolRegistry.organization_id.is_(None),
                ToolRegistry.builtin_key == spec["builtin_key"],
            )
        )
        tool = result.scalar_one_or_none()
        config_schema = {
            "implementation": {"type": "function", "function_name": spec["function_name"]},
            "execution": {
                "timeout_s": int(spec["timeout_s"]),
                "is_pure": bool(spec["is_pure"]),
            },
        }
        if tool is None:
            tool = ToolRegistry(
                organization_id=None,
                name=spec["name"],
                slug=system_slug,
                description=spec["description"],
                scope=ToolDefinitionScope.GLOBAL,
                schema=spec["schema"],
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=ToolImplementationType.FUNCTION,
                builtin_key=spec["builtin_key"],
                is_active=True,
                is_system=True,
                published_at=datetime.now(timezone.utc),
            )
            set_tool_management_metadata(tool, ownership="system")
            db.add(tool)
            await db.flush()
        else:
            tool.name = spec["name"]
            tool.slug = system_slug
            tool.description = spec["description"]
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = spec["schema"]
            tool.config_schema = config_schema
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = ToolImplementationType.FUNCTION
            tool.builtin_key = spec["builtin_key"]
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.now(timezone.utc)
            set_tool_management_metadata(tool, ownership="system")
        tool_rows.append(tool)
        tool_ids.append(str(tool.id))

    toolset_payload = _file_space_toolset_payload(tool_ids)
    for tool in tool_rows:
        config_schema = tool.config_schema if isinstance(tool.config_schema, dict) else {}
        tool.config_schema = {
            **config_schema,
            "toolset": toolset_payload,
        }
    await db.flush()
    return tool_ids
