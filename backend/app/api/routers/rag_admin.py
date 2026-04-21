from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.schemas.rag import ChunkPreviewRequest, CreateIndexRequest, RAGIndex, RAGStats
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.rag import RAGPipeline
from app.db.postgres.session import get_db
from app.services.rag_admin_service import RAGAdminService

router = APIRouter()


def _internal_pipeline_row_key() -> str:
    return f"pipeline-{uuid4().hex[:24]}"


async def get_rag_admin_service(db: AsyncSession = Depends(get_db)):
    return RAGAdminService(db)


async def _organization_for_principal(*, db: AsyncSession, organization_id: UUID, principal: dict) -> tuple[Organization, User]:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    scopes = set(principal.get("scopes") or [])
    if "*" not in scopes and str(organization.id) != str(principal.get("organization_id")):
        raise HTTPException(status_code=403, detail="Active organization does not match requested organization")
    user = await db.get(User, UUID(str(principal["user_id"])))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return organization, user


@router.get("/stats", response_model=RAGStats)
async def get_rag_stats(
    organization_id: Optional[UUID] = None,
    principal: dict = Depends(get_current_principal),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    organization_id= None
    if organization_id:
        organization, _ = await _organization_for_principal(
            db=service.db,
            organization_id=organization_id,
            principal=await require_scopes("stats.read")(principal),
        )
        organization_id= organization.id
    elif "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Access denied")
    return await service.get_stats(organization_id=organization_id)


@router.get("/indices", response_model=Dict[str, List[RAGIndex]])
async def list_indices(
    organization_id: Optional[UUID] = None,
    principal: dict = Depends(get_current_principal),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    if organization_id:
        await _organization_for_principal(
            db=service.db,
            organization_id=organization_id,
            principal=await require_scopes("pipelines.catalog.read")(principal),
        )
    elif "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Admin role or organization context required")
    return {"indices": await service.list_indices()}


@router.post("/indices")
async def create_index(
    request: CreateIndexRequest,
    organization_id: Optional[UUID] = None,
    principal: dict = Depends(get_current_principal),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    if organization_id:
        await _organization_for_principal(db=service.db, organization_id=organization_id, principal=await require_scopes("pipelines.write")(principal))
    elif "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Admin role or organization context required")
    success = await service.create_index(request.name, request.dimension)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create index")
    return {"status": "created", "name": request.name, "dimension": request.dimension}


@router.get("/indices/{name}", response_model=RAGIndex)
async def get_index(
    name: str,
    organization_id: Optional[UUID] = None,
    principal: dict = Depends(get_current_principal),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    if organization_id:
        await _organization_for_principal(
            db=service.db,
            organization_id=organization_id,
            principal=await require_scopes("pipelines.catalog.read")(principal),
        )
    elif "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Admin role or organization context required")
    index = await service.get_index(name)
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    return index


@router.delete("/indices/{name}")
async def delete_index(
    name: str,
    organization_id: Optional[UUID] = None,
    principal: dict = Depends(get_current_principal),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    if organization_id:
        await _organization_for_principal(db=service.db, organization_id=organization_id, principal=await require_scopes("pipelines.write")(principal))
    elif "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Admin role or organization context required")
    success = await service.delete_index(name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete index")
    return {"status": "deleted", "name": name}


@router.get("/pipelines")
async def list_pipelines(
    organization_id: Optional[UUID] = None,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    organization = None
    if organization_id:
        organization, _ = await _organization_for_principal(db=db, organization_id=organization_id, principal=await require_scopes("pipelines.read")(principal))
    elif "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Unauthorized")

    stmt = select(RAGPipeline)
    if organization is not None:
        stmt = stmt.where(RAGPipeline.organization_id == organization.id)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "pipelines": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "is_default": p.is_default,
                "created_at": p.created_at,
            }
            for p in rows
        ]
    }


@router.post("/pipelines")
async def create_pipeline(
    request: Dict[str, Any],
    organization_id: UUID,
    principal: dict = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    organization, user = await _organization_for_principal(db=db, organization_id=organization_id, principal=principal)
    new_pipeline = RAGPipeline(
        organization_id=organization.id,
        name=request.get("name"),
        slug=_internal_pipeline_row_key(),
        description=request.get("description"),
        chunk_size=request.get("chunk_size", 512),
        chunk_overlap=request.get("chunk_overlap", 50),
        created_by=user.id,
    )
    db.add(new_pipeline)
    await db.commit()
    await db.refresh(new_pipeline)
    return {"id": str(new_pipeline.id), "status": "created"}
