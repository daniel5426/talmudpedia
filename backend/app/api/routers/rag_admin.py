from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import uuid
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, func

from app.db.postgres.models.identity import User, Tenant
from app.db.postgres.models.rag import RAGPipeline, IngestionJob, IngestionStatus
from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission, Permission, Action, ResourceType, parse_id
from app.core.audit import log_simple_action

# Keep the RAG factory and orchestrator imports
from app.rag.factory import (
    RAGFactory,
    RAGConfig,
    EmbeddingConfig,
    VectorStoreConfig,
    ChunkerConfig,
    LoaderConfig,
    EmbeddingProviderType,
    VectorStoreType,
    ChunkerType,
    LoaderType,
)
from app.rag.pipeline.orchestrator import RAGOrchestrator
from app.rag.pipeline.job import IngestionJobConfig

router = APIRouter()

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

class CreateIndexRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    dimension: int = 768
    namespace: Optional[str] = None
    metadata: Dict[str, Any] = {}
    owner_id: Optional[str] = None

class ChunkPreviewRequest(BaseModel):
    text: str
    chunk_size: int = 650
    chunk_overlap: int = 50

class IngestionRequest(BaseModel):
    index_name: str
    documents: List[Dict[str, Any]]
    namespace: Optional[str] = None
    embedding_provider: str = "gemini"
    vector_store_provider: str = "pinecone"
    chunker_strategy: str = "token_based"
    chunk_size: int = 650
    chunk_overlap: int = 50
    use_celery: bool = True

@router.get("/stats")
async def get_rag_stats(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = None
    if tenant_slug:
        ctx = await get_tenant_context(tenant_slug, current_user, db)
        tenant, _ = ctx

    if current_user.role != "admin" and not tenant:
         raise HTTPException(status_code=403, detail="Access denied")

    tid = tenant.id if tenant else None
    
    # Total pipelines
    pipe_stmt = select(func.count(RAGPipeline.id))
    if tid: pipe_stmt = pipe_stmt.where(RAGPipeline.tenant_id == tid)
    total_pipelines = (await db.execute(pipe_stmt)).scalar()
    
    # Jobs
    job_stmt = select(func.count(IngestionJob.id))
    if tid: job_stmt = job_stmt.where(IngestionJob.tenant_id == tid)
    total_jobs = (await db.execute(job_stmt)).scalar()
    
    completed_jobs = (await db.execute(job_stmt.where(IngestionJob.status == IngestionStatus.COMPLETED))).scalar()
    failed_jobs = (await db.execute(job_stmt.where(IngestionJob.status == IngestionStatus.FAILED))).scalar()
    running_jobs = (await db.execute(job_stmt.where(IngestionJob.status == IngestionStatus.PROCESSING))).scalar()

    return {
        "total_pipelines": total_pipelines,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "running_jobs": running_jobs,
        "available_providers": RAGFactory.get_available_providers()
    }

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
