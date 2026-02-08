"""
Knowledge Stores Router - CRUD for logical knowledge repositories.

This router manages KnowledgeStore entities which abstract away
vector database implementation details.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.db.postgres.session import get_db
from app.db.postgres.models import (
    KnowledgeStore, 
    KnowledgeStoreStatus, 
    StorageBackend, 
    RetrievalPolicy,
    Tenant,
    User
)
from app.api.routers.auth import get_current_user


router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class ChunkingStrategySchema(BaseModel):
    strategy: str = "recursive"
    chunk_size: int = 512
    chunk_overlap: int = 50


class CreateKnowledgeStoreRequest(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_model_id: str
    chunking_strategy: Optional[ChunkingStrategySchema] = None
    retrieval_policy: RetrievalPolicy = RetrievalPolicy.SEMANTIC_ONLY
    # Advanced (optional)
    backend: StorageBackend = StorageBackend.PGVECTOR
    backend_config: Dict[str, Any] = Field(default_factory=dict)
    credentials_ref: Optional[UUID] = None


class UpdateKnowledgeStoreRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    retrieval_policy: Optional[RetrievalPolicy] = None
    credentials_ref: Optional[UUID] = None
    # Note: embedding_model_id and backend are immutable after creation


class KnowledgeStoreResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str]
    embedding_model_id: str
    chunking_strategy: Dict[str, Any]
    retrieval_policy: str
    backend: str
    credentials_ref: Optional[UUID]
    status: str
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID]

    class Config:
        from_attributes = True


# =============================================================================
# Helpers
# =============================================================================

def store_to_response(store: KnowledgeStore) -> KnowledgeStoreResponse:
    return KnowledgeStoreResponse(
        id=store.id,
        tenant_id=store.tenant_id,
        name=store.name,
        description=store.description,
        embedding_model_id=store.embedding_model_id,
        chunking_strategy=store.chunking_strategy or {},
        retrieval_policy=store.retrieval_policy.value,
        backend=store.backend.value,
        credentials_ref=store.credentials_ref,
        status=store.status.value,
        document_count=store.document_count,
        chunk_count=store.chunk_count,
        created_at=store.created_at,
        updated_at=store.updated_at,
        created_by=store.created_by
    )


async def get_tenant_from_slug(db: AsyncSession, slug: str) -> Optional[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=List[KnowledgeStoreResponse])
async def list_knowledge_stores(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge stores for the tenant."""
    # Resolve tenant
    if tenant_slug:
        tenant = await get_tenant_from_slug(db, tenant_slug)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
    else:
        # For now, require tenant_slug or implement default tenant logic
        raise HTTPException(status_code=400, detail="tenant_slug query param required")
    
    stmt = (
        select(KnowledgeStore)
        .where(KnowledgeStore.tenant_id == tenant_id)
        .where(KnowledgeStore.status != KnowledgeStoreStatus.ARCHIVED)
        .order_by(KnowledgeStore.created_at.desc())
    )
    result = await db.execute(stmt)
    stores = result.scalars().all()
    
    return [store_to_response(s) for s in stores]


@router.post("", response_model=KnowledgeStoreResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_store(
    request: CreateKnowledgeStoreRequest,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge store."""
    if not tenant_slug:
        raise HTTPException(status_code=400, detail="tenant_slug query param required")
    
    tenant = await get_tenant_from_slug(db, tenant_slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Build chunking strategy
    chunking = request.chunking_strategy.model_dump() if request.chunking_strategy else {
        "strategy": "recursive",
        "chunk_size": 512,
        "chunk_overlap": 50
    }
    
    # Generate backend config if not provided
    backend_config = request.backend_config
    if not backend_config:
        # Auto-generate index/collection name
        safe_name = request.name.lower().replace(" ", "_").replace("-", "_")[:32]
        backend_config = {
            "index_name": f"ks_{safe_name}_{str(tenant.id)[:8]}",
            "namespace": "default"
        }
    
    store = KnowledgeStore(
        tenant_id=tenant.id,
        name=request.name,
        description=request.description,
        embedding_model_id=request.embedding_model_id,
        chunking_strategy=chunking,
        retrieval_policy=request.retrieval_policy,
        backend=request.backend,
        backend_config=backend_config,
        credentials_ref=request.credentials_ref,
        status=KnowledgeStoreStatus.ACTIVE,
        created_by=current_user.id
    )
    
    db.add(store)
    await db.commit()
    await db.refresh(store)
    
    return store_to_response(store)


@router.get("/{store_id}", response_model=KnowledgeStoreResponse)
async def get_knowledge_store(
    store_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific knowledge store by ID."""
    store = await db.get(KnowledgeStore, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    # Tenant isolation check
    if tenant_slug:
        tenant = await get_tenant_from_slug(db, tenant_slug)
        if tenant and store.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    return store_to_response(store)


@router.patch("/{store_id}", response_model=KnowledgeStoreResponse)
async def update_knowledge_store(
    store_id: UUID,
    request: UpdateKnowledgeStoreRequest,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge store. Note: embedding_model_id and backend are immutable."""
    store = await db.get(KnowledgeStore, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    # Tenant isolation
    if tenant_slug:
        tenant = await get_tenant_from_slug(db, tenant_slug)
        if tenant and store.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    # Apply updates
    if request.name is not None:
        store.name = request.name
    if request.description is not None:
        store.description = request.description
    if request.retrieval_policy is not None:
        store.retrieval_policy = request.retrieval_policy
    if request.credentials_ref is not None:
        store.credentials_ref = request.credentials_ref
    
    await db.commit()
    await db.refresh(store)
    
    return store_to_response(store)


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_store(
    store_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete (archive) a knowledge store."""
    store = await db.get(KnowledgeStore, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    # Tenant isolation
    if tenant_slug:
        tenant = await get_tenant_from_slug(db, tenant_slug)
        if tenant and store.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    # Soft delete - mark as archived
    store.status = KnowledgeStoreStatus.ARCHIVED
    await db.commit()
    
    return None


@router.get("/{store_id}/stats")
async def get_knowledge_store_stats(
    store_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed statistics for a knowledge store."""
    store = await db.get(KnowledgeStore, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    
    return {
        "id": store.id,
        "name": store.name,
        "document_count": store.document_count,
        "chunk_count": store.chunk_count,
        "backend": store.backend.value,
        "status": store.status.value,
        "embedding_model": store.embedding_model_id,
        "retrieval_policy": store.retrieval_policy.value
    }
