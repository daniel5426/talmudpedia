from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, func

from app.db.postgres.models.identity import User, Tenant
from app.db.postgres.models.rag import RAGPipeline, IngestionJob, IngestionStatus
from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission, Permission, Action, ResourceType, parse_id
from app.core.audit import log_simple_action

from app.api.schemas.rag import (
    RAGIndex, 
    RAGStats, 
    CreateIndexRequest, 
    ChunkPreviewRequest, 
    IngestionRequest
)
from app.services.rag_admin_service import RAGAdminService
from app.rag.factory import RAGFactory

router = APIRouter()

async def get_rag_admin_service(db: AsyncSession = Depends(get_db)):
    return RAGAdminService(db)

@router.get("/stats", response_model=RAGStats)
async def get_rag_stats(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    tenant = None
    if tenant_slug:
        ctx = await get_tenant_context(tenant_slug, current_user, service.db)
        tenant, _ = ctx

    if current_user.role != "admin" and not tenant:
         raise HTTPException(status_code=403, detail="Access denied")

    tid = tenant.id if tenant else None
    return await service.get_stats(tenant_id=tid)

@router.get("/indices", response_model=Dict[str, List[RAGIndex]])
async def list_indices(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    # Permission check
    if current_user.role != "admin":
        if not tenant_slug:
             raise HTTPException(status_code=403, detail="Admin role or tenant context required")
        await get_tenant_context(tenant_slug, current_user, service.db)
    
    indices = await service.list_indices()
    return {"indices": indices}

@router.post("/indices")
async def create_index(
    request: CreateIndexRequest,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    # Permission check
    if current_user.role != "admin":
        if not tenant_slug:
             raise HTTPException(status_code=403, detail="Admin role or tenant context required")
        await get_tenant_context(tenant_slug, current_user, service.db)

    success = await service.create_index(request.name, request.dimension)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create index")
    
    return {"status": "created", "name": request.name, "dimension": request.dimension}

@router.get("/indices/{name}", response_model=RAGIndex)
async def get_index(
    name: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    # Permission check
    if current_user.role != "admin":
        if not tenant_slug:
             raise HTTPException(status_code=403, detail="Admin role or tenant context required")
        await get_tenant_context(tenant_slug, current_user, service.db)

    index = await service.get_index(name)
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    
    return index

@router.delete("/indices/{name}")
async def delete_index(
    name: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    service: RAGAdminService = Depends(get_rag_admin_service),
):
    # Permission check
    if current_user.role != "admin":
        if not tenant_slug:
             raise HTTPException(status_code=403, detail="Admin role or tenant context required")
        await get_tenant_context(tenant_slug, current_user, service.db)

    success = await service.delete_index(name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete index")
    
    return {"status": "deleted", "name": name}

@router.get("/pipelines")
async def list_pipelines(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = None
    if tenant_slug:
        ctx = await get_tenant_context(tenant_slug, current_user, db)
        tenant, _ = ctx
        
    stmt = select(RAGPipeline)
    if tenant:
        stmt = stmt.where(RAGPipeline.tenant_id == tenant.id)
    elif current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    res = await db.execute(stmt)
    pipelines = res.scalars().all()
    
    return {"pipelines": [
        {
            "id": str(p.id),
            "name": p.name,
            "slug": p.slug,
            "description": p.description,
            "is_default": p.is_default,
            "created_at": p.created_at
        } for p in pipelines
    ]}

@router.post("/pipelines")
async def create_pipeline(
    request: Dict[str, Any], # Simplifed for now
    tenant_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ctx = await get_tenant_context(tenant_slug, current_user, db)
    tenant, _ = ctx

    # Check permission
    has_perm = await check_permission(current_user.id, tenant.id, Permission(resource_type=ResourceType.INDEX, action=Action.WRITE), db=db)
    if not has_perm and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    new_pipeline = RAGPipeline(
        tenant_id=tenant.id,
        name=request.get("name"),
        slug=request.get("slug") or f"{tenant.slug}-{request.get('name').lower().replace(' ', '-')}",
        description=request.get("description"),
        chunk_size=request.get("chunk_size", 512),
        chunk_overlap=request.get("chunk_overlap", 50),
        created_by=current_user.id
    )
    db.add(new_pipeline)
    await db.commit()
    await db.refresh(new_pipeline)
    
    return {"id": str(new_pipeline.id), "status": "created"}

@router.get("/jobs")
async def list_jobs(
    tenant_slug: Optional[str] = None,
    status: Optional[IngestionStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = None
    if tenant_slug:
        ctx = await get_tenant_context(tenant_slug, current_user, db)
        tenant, _ = ctx
        
    stmt = select(IngestionJob)
    if tenant:
        stmt = stmt.where(IngestionJob.tenant_id == tenant.id)
    elif current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized")

    if status:
        stmt = stmt.where(IngestionJob.status == status)
        
    res = await db.execute(stmt.order_by(IngestionJob.created_at.desc()))
    jobs = res.scalars().all()
    
    return {"items": [
        {
            "id": str(j.id),
            "pipeline_id": str(j.pipeline_id),
            "status": j.status.value,
            "document_count": j.document_count,
            "chunk_count": j.chunk_count,
            "error_message": j.error_message,
            "created_at": j.created_at,
            "completed_at": j.completed_at
        } for j in jobs
    ]}

@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    jid = parse_id(job_id)
    stmt = select(IngestionJob).where(IngestionJob.id == jid)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if current_user.role != "admin" and job.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    await db.delete(job)
    await db.commit()
    return {"status": "deleted"}
