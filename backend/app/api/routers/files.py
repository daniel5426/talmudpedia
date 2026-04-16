from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.db.postgres.models.files import FileAccessMode
from app.services.file_spaces.service import (
    FileSpaceNotFoundError,
    FileSpaceService,
    FileSpaceValidationError,
)


router = APIRouter(prefix="/admin/files", tags=["files"])


class CreateFileSpaceRequest(BaseModel):
    name: str
    description: str | None = None


class UpdateFileSpaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class WriteTextFileRequest(BaseModel):
    path: str
    content: str
    mime_type: str | None = None


class PatchTextFileRequest(BaseModel):
    path: str
    old_text: str
    new_text: str


class MoveEntryRequest(BaseModel):
    from_path: str
    to_path: str


class DeleteEntryRequest(BaseModel):
    path: str


class MkdirRequest(BaseModel):
    path: str


class UpsertWorkflowLinkRequest(BaseModel):
    agent_id: UUID
    access_mode: FileAccessMode


def _principal_user_id(principal: dict[str, Any]) -> UUID | None:
    raw = principal.get("user_id")
    try:
        return UUID(str(raw)) if raw else None
    except Exception:
        return None


def _required_context(principal: dict[str, Any]) -> tuple[UUID, UUID]:
    tenant_id = principal.get("tenant_id")
    project_id = principal.get("project_id")
    try:
        resolved_tenant_id = UUID(str(tenant_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="tenant context is required") from exc
    try:
        resolved_project_id = UUID(str(project_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="project context is required") from exc
    return resolved_tenant_id, resolved_project_id


def _handle_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileSpaceNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, FileSpaceValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="file space request failed")


@router.get("")
async def list_file_spaces(
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    spaces = await FileSpaceService(db).list_spaces(tenant_id=tenant_id, project_id=project_id)
    return {"items": [FileSpaceService.serialize_space(space, view="full") for space in spaces]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_file_space(
    request: CreateFileSpaceRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        space = await FileSpaceService(db).create_space(
            tenant_id=tenant_id,
            project_id=project_id,
            name=request.name,
            description=request.description,
            created_by=_principal_user_id(principal),
        )
        await db.commit()
        await db.refresh(space)
        return FileSpaceService.serialize_space(space, view="full")
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.get("/{space_id}")
async def get_file_space(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        space = await FileSpaceService(db).get_space(tenant_id=tenant_id, project_id=project_id, space_id=space_id)
        return FileSpaceService.serialize_space(space, view="full")
    except Exception as exc:
        raise _handle_service_error(exc) from exc


@router.put("/{space_id}")
async def update_file_space(
    space_id: UUID,
    request: UpdateFileSpaceRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        service = FileSpaceService(db)
        space = await service.get_space(tenant_id=tenant_id, project_id=project_id, space_id=space_id)
        if request.name is not None:
            space.name = service._normalize_name(request.name)
        if request.description is not None:
            space.description = str(request.description).strip() or None
        await db.commit()
        await db.refresh(space)
        return FileSpaceService.serialize_space(space, view="full")
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_file_space(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        await FileSpaceService(db).archive_space(tenant_id=tenant_id, project_id=project_id, space_id=space_id)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{space_id}/tree")
async def list_file_space_tree(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entries = await FileSpaceService(db).list_entries(tenant_id=tenant_id, project_id=project_id, space_id=space_id)
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}
    except Exception as exc:
        raise _handle_service_error(exc) from exc


@router.post("/{space_id}/mkdir")
async def mkdir_file_space(
    space_id: UUID,
    request: MkdirRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entry = await FileSpaceService(db).mkdir(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=request.path,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        await db.refresh(entry)
        return FileSpaceService.serialize_entry(entry)
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.get("/{space_id}/entries/content")
async def read_text_entry(
    space_id: UUID,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entry, revision, content = await FileSpaceService(db).read_text_file(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        return FileSpaceService.serialize_text_read(entry, revision, content)
    except Exception as exc:
        raise _handle_service_error(exc) from exc


@router.put("/{space_id}/entries/content")
async def write_text_entry(
    space_id: UUID,
    request: WriteTextFileRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entry, revision = await FileSpaceService(db).write_text_file(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=request.path,
            content=request.content,
            mime_type=request.mime_type,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.post("/{space_id}/entries/patch")
async def patch_text_entry(
    space_id: UUID,
    request: PatchTextFileRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entry, revision = await FileSpaceService(db).patch_text_file(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=request.path,
            old_text=request.old_text,
            new_text=request.new_text,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.post("/{space_id}/entries/upload")
async def upload_entry(
    space_id: UUID,
    path: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        payload = await file.read()
        entry, revision = await FileSpaceService(db).upload_file(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
            payload=payload,
            content_type=file.content_type,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
        }
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.get("/{space_id}/entries/download")
async def download_entry(
    space_id: UUID,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entry, revision, payload = await FileSpaceService(db).read_file_bytes(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        headers = {"Content-Disposition": f'attachment; filename="{entry.path.rsplit("/", 1)[-1]}"'}
        return Response(content=payload, media_type=revision.mime_type, headers=headers)
    except Exception as exc:
        raise _handle_service_error(exc) from exc


@router.post("/{space_id}/entries/move")
async def move_entry(
    space_id: UUID,
    request: MoveEntryRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entries = await FileSpaceService(db).move_entry(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            from_path=request.from_path,
            to_path=request.to_path,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.post("/{space_id}/entries/delete")
async def delete_entry(
    space_id: UUID,
    request: DeleteEntryRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        entries = await FileSpaceService(db).delete_entry(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=request.path,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        return {"items": [FileSpaceService.serialize_entry(entry) for entry in entries]}
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.get("/{space_id}/entries/revisions")
async def list_entry_revisions(
    space_id: UUID,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        revisions = await FileSpaceService(db).list_revisions(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        return {"items": [FileSpaceService.serialize_revision(revision) for revision in revisions]}
    except Exception as exc:
        raise _handle_service_error(exc) from exc


@router.get("/{space_id}/links")
async def list_workflow_links(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.read")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        links = await FileSpaceService(db).list_agent_links(
            tenant_id=tenant_id,
            project_id=project_id,
            space_id=space_id,
        )
        return {"items": [FileSpaceService.serialize_link(link) for link in links]}
    except Exception as exc:
        raise _handle_service_error(exc) from exc


@router.post("/{space_id}/links")
async def upsert_workflow_link(
    space_id: UUID,
    request: UpsertWorkflowLinkRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        link = await FileSpaceService(db).upsert_agent_link(
            tenant_id=tenant_id,
            project_id=project_id,
            agent_id=request.agent_id,
            space_id=space_id,
            access_mode=request.access_mode,
            user_id=_principal_user_id(principal),
        )
        await db.commit()
        return FileSpaceService.serialize_link(link)
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc


@router.delete("/{space_id}/links/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_link(
    space_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("files.write")),
):
    tenant_id, project_id = _required_context(principal)
    try:
        await FileSpaceService(db).delete_agent_link(
            tenant_id=tenant_id,
            project_id=project_id,
            agent_id=agent_id,
            space_id=space_id,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise _handle_service_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
