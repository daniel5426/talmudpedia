from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.prompts import PromptLibrary, PromptLibraryVersion, PromptScope, PromptStatus
from app.db.postgres.session import get_db
from app.services.prompt_library_service import (
    PromptAccessError,
    PromptCreateData,
    PromptLibraryError,
    PromptLibraryService,
    PromptUpdateData,
    PromptUsageError,
)
from app.services.prompt_reference_resolver import PromptReferenceError

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptRecord(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    content: str
    scope: str
    status: str
    ownership: str
    managed_by: Optional[str] = None
    allowed_surfaces: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    version: int
    created_at: datetime
    updated_at: datetime


class PromptListResponse(BaseModel):
    prompts: list[PromptRecord]
    total: int


class PromptVersionRecord(BaseModel):
    id: UUID
    prompt_id: UUID
    version: int
    name: str
    description: Optional[str] = None
    content: str
    allowed_surfaces: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_by: Optional[UUID] = None
    created_at: datetime


class PromptUsageRecord(BaseModel):
    resource_type: str
    resource_id: str
    resource_name: str
    surface: str
    location_pointer: str
    tenant_id: Optional[str] = None
    node_id: Optional[str] = None


class CreatePromptRequest(BaseModel):
    name: str
    description: Optional[str] = None
    content: str = ""
    scope: PromptScope = PromptScope.TENANT
    allowed_surfaces: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    allowed_surfaces: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class RollbackPromptRequest(BaseModel):
    version: int


class PromptMentionRecord(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    scope: str
    tenant_id: Optional[UUID] = None
    updated_at: datetime


class PromptResolvePreviewRequest(BaseModel):
    text: str = ""
    surface: Optional[str] = None


class PromptResolvePreviewResponse(BaseModel):
    text: str
    bindings: list[dict[str, Any]]
    errors: list[str] = Field(default_factory=list)


def _serialize_prompt(prompt: PromptLibrary) -> PromptRecord:
    return PromptRecord(
        id=prompt.id,
        tenant_id=prompt.tenant_id,
        name=str(prompt.name or ""),
        description=prompt.description,
        content=str(prompt.content or ""),
        scope=str(getattr(prompt.scope, "value", prompt.scope)),
        status=str(getattr(prompt.status, "value", prompt.status)),
        ownership=str(getattr(prompt.ownership, "value", prompt.ownership)),
        managed_by=prompt.managed_by,
        allowed_surfaces=list(prompt.allowed_surfaces or []),
        tags=list(prompt.tags or []),
        version=int(prompt.version or 1),
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


def _serialize_version(version: PromptLibraryVersion) -> PromptVersionRecord:
    return PromptVersionRecord(
        id=version.id,
        prompt_id=version.prompt_id,
        version=int(version.version or 1),
        name=str(version.name or ""),
        description=version.description,
        content=str(version.content or ""),
        allowed_surfaces=list(version.allowed_surfaces or []),
        tags=list(version.tags or []),
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _service_from_context(
    *,
    db: AsyncSession,
    principal: dict[str, Any],
) -> PromptLibraryService:
    user = principal.get("user")
    return PromptLibraryService(
        db,
        tenant_id=(UUID(str(principal["tenant_id"])) if principal.get("tenant_id") else None),
        actor_user_id=(user.id if user is not None else None),
        actor_role=(getattr(user, "role", None) if user is not None else None),
        is_service=bool(principal.get("type") == "workload"),
    )


@router.get("", response_model=PromptListResponse)
async def list_prompts(
    q: Optional[str] = Query(default=None),
    status: Optional[PromptStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: dict[str, Any] = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    prompts, total = await service.list_prompts(q=q, status=status, limit=limit, offset=offset)
    return PromptListResponse(prompts=[_serialize_prompt(item) for item in prompts], total=total)


@router.get("/mentions/search", response_model=list[PromptMentionRecord])
async def search_prompt_mentions(
    q: Optional[str] = Query(default=None),
    surface: Optional[str] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    principal: dict[str, Any] = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    prompts = await service.search_mentions(q=q, surface=surface, limit=limit)
    return [
        PromptMentionRecord(
            id=prompt.id,
            name=str(prompt.name or ""),
            description=prompt.description,
            scope=str(getattr(prompt.scope, "value", prompt.scope)),
            tenant_id=prompt.tenant_id,
            updated_at=prompt.updated_at,
        )
        for prompt in prompts
    ]


@router.post("", response_model=PromptRecord)
async def create_prompt(
    request: CreatePromptRequest,
    principal: dict[str, Any] = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        prompt = await service.create_prompt(
            PromptCreateData(
                name=request.name,
                description=request.description,
                content=request.content,
                scope=request.scope,
                allowed_surfaces=request.allowed_surfaces,
                tags=request.tags,
            )
        )
        await db.commit()
        await db.refresh(prompt)
        return _serialize_prompt(prompt)
    except (PromptAccessError, PromptReferenceError, PromptLibraryError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/resolve-preview", response_model=PromptResolvePreviewResponse)
async def resolve_prompt_preview(
    request: PromptResolvePreviewRequest,
    principal: dict[str, Any] = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        text, bindings = await service.resolver.resolve_text(request.text, surface=request.surface)
        return PromptResolvePreviewResponse(text=text, bindings=bindings, errors=[])
    except PromptReferenceError as exc:
        return PromptResolvePreviewResponse(text=request.text, bindings=[], errors=[str(exc)])


@router.get("/{prompt_id}", response_model=PromptRecord)
async def get_prompt(
    prompt_id: UUID,
    principal: dict[str, Any] = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        prompt = await service.get_prompt(prompt_id)
        return _serialize_prompt(prompt)
    except PromptAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{prompt_id}", response_model=PromptRecord)
async def update_prompt(
    prompt_id: UUID,
    request: UpdatePromptRequest,
    principal: dict[str, Any] = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        prompt = await service.update_prompt(
            prompt_id,
            PromptUpdateData(
                name=request.name,
                description=request.description,
                content=request.content,
                allowed_surfaces=request.allowed_surfaces,
                tags=request.tags,
            ),
        )
        await db.commit()
        await db.refresh(prompt)
        return _serialize_prompt(prompt)
    except PromptAccessError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PromptReferenceError, PromptLibraryError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{prompt_id}/archive", response_model=PromptRecord)
async def archive_prompt(
    prompt_id: UUID,
    principal: dict[str, Any] = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        prompt = await service.archive_prompt(prompt_id)
        await db.commit()
        await db.refresh(prompt)
        return _serialize_prompt(prompt)
    except PromptAccessError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{prompt_id}/restore", response_model=PromptRecord)
async def restore_prompt(
    prompt_id: UUID,
    principal: dict[str, Any] = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        prompt = await service.restore_prompt(prompt_id)
        await db.commit()
        await db.refresh(prompt)
        return _serialize_prompt(prompt)
    except PromptAccessError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{prompt_id}", response_model=dict[str, bool])
async def delete_prompt(
    prompt_id: UUID,
    principal: dict[str, Any] = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        await service.delete_prompt(prompt_id)
        await db.commit()
        return {"deleted": True}
    except PromptAccessError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PromptUsageError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionRecord])
async def list_prompt_versions(
    prompt_id: UUID,
    principal: dict[str, Any] = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        versions = await service.list_versions(prompt_id)
        return [_serialize_version(item) for item in versions]
    except PromptAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{prompt_id}/rollback", response_model=PromptRecord)
async def rollback_prompt(
    prompt_id: UUID,
    request: RollbackPromptRequest,
    principal: dict[str, Any] = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        prompt = await service.rollback(prompt_id, version=request.version)
        await db.commit()
        await db.refresh(prompt)
        return _serialize_prompt(prompt)
    except PromptAccessError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PromptReferenceError, PromptLibraryError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{prompt_id}/usage", response_model=list[PromptUsageRecord])
async def prompt_usage(
    prompt_id: UUID,
    principal: dict[str, Any] = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = _service_from_context(db=db, principal=principal)
    try:
        usage = await service.usage(prompt_id)
        return [PromptUsageRecord(**item) for item in usage]
    except PromptAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
