from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import engine as postgres_engine
from app.db.postgres.models.files import FileAccessMode
from app.services.file_spaces.service import (
    FileSpaceNotFoundError,
    FileSpacePermissionError,
    FileSpaceService,
    FileSpaceValidationError,
)


@dataclass(slots=True)
class AuthorizedFileSpaceContext:
    db: AsyncSession
    service: FileSpaceService
    space_id: UUID
    organization_id: UUID
    project_id: UUID
    user_id: UUID | None
    run_id: UUID | None
    grant: dict[str, Any]
    runtime_context: dict[str, Any]


@dataclass(slots=True)
class AuthorizedFileReference:
    context: AuthorizedFileSpaceContext
    path: str
    entry: Any
    revision: Any | None


def _parse_uuid(value: Any, *, field: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception as exc:
        raise FileSpaceValidationError(f"{field} is required") from exc


def tool_runtime_context(payload: Any) -> dict[str, Any]:
    return (
        payload.get("__tool_runtime_context__")
        if isinstance(payload, dict) and isinstance(payload.get("__tool_runtime_context__"), dict)
        else {}
    )


def _file_space_grant(payload: dict[str, Any], *, space_id: UUID) -> dict[str, Any]:
    runtime_context = tool_runtime_context(payload)
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


def resolve_space_id(payload: dict[str, Any]) -> UUID:
    raw_value = payload.get("space_id")
    runtime_context = tool_runtime_context(payload)
    grants = runtime_context.get("file_spaces") if isinstance(runtime_context.get("file_spaces"), list) else []

    normalized = str(raw_value or "").strip()
    if normalized.lower() == "default":
        if len(grants) != 1:
            raise FileSpaceValidationError("space_id='default' requires exactly one linked file space in the workflow run")
        grant = grants[0] if isinstance(grants[0], dict) else None
        if not isinstance(grant, dict):
            raise FileSpaceValidationError("default linked file space is invalid")
        try:
            return UUID(str(grant.get("id")))
        except Exception as exc:
            raise FileSpaceValidationError("default linked file space is invalid") from exc

    try:
        return UUID(normalized)
    except Exception as exc:
        raise FileSpaceValidationError("space_id must be a UUID or 'default'") from exc


def _optional_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except Exception:
        return None


def _serialize_exception(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, FileSpacePermissionError):
        return {"error": str(exc), "code": "FILE_SPACE_FORBIDDEN"}
    if isinstance(exc, FileSpaceNotFoundError):
        return {"error": str(exc), "code": "FILE_SPACE_NOT_FOUND"}
    if isinstance(exc, FileSpaceValidationError):
        return {"error": str(exc), "code": "FILE_SPACE_VALIDATION_FAILED"}
    raise exc


async def resolve_authorized_file_space(
    *,
    db: AsyncSession,
    payload: dict[str, Any],
    write: bool,
) -> AuthorizedFileSpaceContext:
    space_id = resolve_space_id(payload)
    runtime_context = tool_runtime_context(payload)
    organization_id= _parse_uuid(runtime_context.get("organization_id"), field="organization_id")
    project_id = _parse_uuid(runtime_context.get("project_id"), field="project_id")
    raw_run_id = runtime_context.get("run_id")
    raw_user_id = runtime_context.get("initiator_user_id") or runtime_context.get("user_id")
    run_id = _optional_uuid(raw_run_id)
    user_id = _optional_uuid(raw_user_id)
    grant = _file_space_grant(payload, space_id=space_id)
    access_mode = str(grant.get("access_mode") or "").strip().lower()
    if write and access_mode != FileAccessMode.read_write.value:
        raise FileSpacePermissionError("linked workflow has read-only access to this file space")
    service = FileSpaceService(db)
    return AuthorizedFileSpaceContext(
        db=db,
        service=service,
        space_id=space_id,
        organization_id=organization_id,
        project_id=project_id,
        user_id=user_id,
        run_id=run_id,
        grant=grant,
        runtime_context=runtime_context,
    )


async def resolve_authorized_file_reference(
    ctx: AuthorizedFileSpaceContext,
    *,
    path: str,
) -> AuthorizedFileReference:
    entry, revision = await ctx.service.read_entry(
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
        space_id=ctx.space_id,
        path=path,
    )
    return AuthorizedFileReference(context=ctx, path=entry.path, entry=entry, revision=revision)


async def read_authorized_text_reference(
    ctx: AuthorizedFileSpaceContext,
    *,
    path: str,
) -> tuple[AuthorizedFileReference, str]:
    entry, revision, content = await ctx.service.read_text_file(
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
        space_id=ctx.space_id,
        path=path,
    )
    return AuthorizedFileReference(context=ctx, path=entry.path, entry=entry, revision=revision), content


async def read_authorized_bytes_reference(
    ctx: AuthorizedFileSpaceContext,
    *,
    path: str,
) -> tuple[AuthorizedFileReference, bytes]:
    entry, revision, payload = await ctx.service.read_file_bytes(
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
        space_id=ctx.space_id,
        path=path,
    )
    return AuthorizedFileReference(context=ctx, path=entry.path, entry=entry, revision=revision), payload


async def with_authorized_file_space(
    payload: Any,
    *,
    write: bool,
    handler,
) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    try:
        async with postgres_engine.sessionmaker() as db:
            ctx = await resolve_authorized_file_space(db=db, payload=tool_payload, write=write)
            result = await handler(
                db=ctx.db,
                service=ctx.service,
                tool_payload=tool_payload,
                space_id=ctx.space_id,
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                user_id=ctx.user_id,
                run_id=ctx.run_id,
                runtime_context=ctx.runtime_context,
                grant=ctx.grant,
                authorized_context=ctx,
            )
            if write:
                await db.commit()
            return result
    except Exception as exc:
        return _serialize_exception(exc)
