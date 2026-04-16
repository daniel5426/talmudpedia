from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import sessionmaker as get_session
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    set_tool_management_metadata,
)
from app.db.postgres.models.files import FileAccessMode
from app.services.file_spaces.service import (
    FileSpaceNotFoundError,
    FileSpacePermissionError,
    FileSpaceService,
    FileSpaceValidationError,
)
from app.services.tool_function_registry import register_tool_function


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
        "slug": "files-list",
        "name": "Files List",
        "description": "List the live tree entries in a linked file space.",
        "function_name": "files_list",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(properties={"space_id": {"type": "string"}}, required=["space_id"]),
    },
    {
        "slug": "files-read",
        "name": "Files Read",
        "description": "Read a text file from a linked file space.",
        "function_name": "files_read",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={"space_id": {"type": "string"}, "path": {"type": "string"}},
            required=["space_id", "path"],
        ),
    },
    {
        "slug": "files-write",
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
        "slug": "files-patch-text",
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
            },
            required=["space_id", "path", "old_text", "new_text"],
        ),
    },
    {
        "slug": "files-mkdir",
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
        "slug": "files-move",
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
        "slug": "files-delete",
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
        "slug": "files-upload-blob",
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
        "slug": "files-download-meta",
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


def _parse_uuid(value: Any, *, field: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception as exc:
        raise FileSpaceValidationError(f"{field} is required") from exc


def _runtime_context(payload: Any) -> dict[str, Any]:
    return payload.get("__tool_runtime_context__") if isinstance(payload, dict) and isinstance(payload.get("__tool_runtime_context__"), dict) else {}


def _file_space_grant(payload: dict[str, Any], *, space_id: UUID) -> dict[str, Any]:
    runtime_context = _runtime_context(payload)
    grants = runtime_context.get("file_spaces") if isinstance(runtime_context.get("file_spaces"), list) else []
    for grant in grants:
        if not isinstance(grant, dict):
            continue
        try:
            grant_id = UUID(str(grant.get("id")))
        except Exception:
            continue
        if grant_id == space_id:
            return grant
    raise FileSpacePermissionError("file space is not linked to this workflow run")


def _optional_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except Exception:
        return None


def _require_access(payload: dict[str, Any], *, space_id: UUID, write: bool) -> tuple[UUID, UUID, UUID | None, UUID | None]:
    runtime_context = _runtime_context(payload)
    tenant_id = _parse_uuid(runtime_context.get("tenant_id"), field="tenant_id")
    project_id = _parse_uuid(runtime_context.get("project_id"), field="project_id")
    raw_run_id = runtime_context.get("run_id")
    raw_user_id = runtime_context.get("initiator_user_id") or runtime_context.get("user_id")
    run_id = _optional_uuid(raw_run_id)
    user_id = _optional_uuid(raw_user_id)
    grant = _file_space_grant(payload, space_id=space_id)
    access_mode = str(grant.get("access_mode") or "").strip().lower()
    if write and access_mode != FileAccessMode.read_write.value:
        raise FileSpacePermissionError("linked workflow has read-only access to this file space")
    return tenant_id, project_id, user_id, run_id


def _serialize_exception(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, FileSpacePermissionError):
        return {"error": str(exc), "code": "FILE_SPACE_FORBIDDEN"}
    if isinstance(exc, FileSpaceNotFoundError):
        return {"error": str(exc), "code": "FILE_SPACE_NOT_FOUND"}
    if isinstance(exc, FileSpaceValidationError):
        return {"error": str(exc), "code": "FILE_SPACE_VALIDATION_FAILED"}
    raise exc


async def _with_service(
    payload: Any,
    *,
    write: bool,
    handler,
) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    try:
        space_id = _parse_uuid(tool_payload.get("space_id"), field="space_id")
        tenant_id, project_id, user_id, run_id = _require_access(tool_payload, space_id=space_id, write=write)
        async with get_session() as db:
            service = FileSpaceService(db)
            result = await handler(
                db=db,
                service=service,
                tool_payload=tool_payload,
                space_id=space_id,
                tenant_id=tenant_id,
                project_id=project_id,
                user_id=user_id,
                run_id=run_id,
            )
            if write:
                await db.commit()
            return result
    except Exception as exc:
        return _serialize_exception(exc)


@register_tool_function("files_list")
async def files_list(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entries = await kwargs["service"].list_entries(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
        )
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_read")
async def files_read(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry, revision, content = await kwargs["service"].read_text_file(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
        )
        return FileSpaceService.serialize_text_read(entry, revision, content)

    return await _with_service(payload, write=False, handler=_handler)


@register_tool_function("files_write")
async def files_write(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry, revision = await kwargs["service"].write_text_file(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            content=str(kwargs["tool_payload"].get("content") or ""),
            mime_type=str(kwargs["tool_payload"].get("mime_type") or "").strip() or None,
            user_id=kwargs["user_id"],
            run_id=kwargs["run_id"],
        )
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_patch_text")
async def files_patch_text(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry, revision = await kwargs["service"].patch_text_file(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            old_text=str(kwargs["tool_payload"].get("old_text") or ""),
            new_text=str(kwargs["tool_payload"].get("new_text") or ""),
            user_id=kwargs["user_id"],
            run_id=kwargs["run_id"],
        )
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_mkdir")
async def files_mkdir(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry = await kwargs["service"].mkdir(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            user_id=kwargs["user_id"],
        )
        return {"entry": FileSpaceService.serialize_entry(entry)}

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_move")
async def files_move(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entries = await kwargs["service"].move_entry(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            from_path=str(kwargs["tool_payload"].get("from_path") or ""),
            to_path=str(kwargs["tool_payload"].get("to_path") or ""),
            user_id=kwargs["user_id"],
        )
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_delete")
async def files_delete(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entries = await kwargs["service"].delete_entry(
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            user_id=kwargs["user_id"],
        )
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
            tenant_id=kwargs["tenant_id"],
            project_id=kwargs["project_id"],
            space_id=kwargs["space_id"],
            path=str(kwargs["tool_payload"].get("path") or ""),
            payload=content,
            content_type=str(kwargs["tool_payload"].get("content_type") or "").strip() or None,
            user_id=kwargs["user_id"],
            run_id=kwargs["run_id"],
        )
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }

    return await _with_service(payload, write=True, handler=_handler)


@register_tool_function("files_download_meta")
async def files_download_meta(payload: Any) -> dict[str, Any]:
    async def _handler(**kwargs):
        entry, revision = await kwargs["service"].read_entry(
            tenant_id=kwargs["tenant_id"],
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


async def ensure_file_space_tools(db: AsyncSession) -> list[str]:
    tool_ids: list[str] = []
    for spec in FILE_SPACE_TOOL_SPECS:
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
            "implementation": {"type": "function", "function_name": spec["function_name"]},
            "execution": {
                "timeout_s": int(spec["timeout_s"]),
                "is_pure": bool(spec["is_pure"]),
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
                is_active=True,
                is_system=True,
                published_at=datetime.now(timezone.utc),
            )
            set_tool_management_metadata(tool, ownership="system")
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
            set_tool_management_metadata(tool, ownership="system")
        tool_ids.append(str(tool.id))
    await db.flush()
    return tool_ids
