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
from app.api.dependencies import get_current_principal, get_tenant_context, require_scopes
from app.db.postgres.models import (
    KnowledgeStore, 
    KnowledgeStoreStatus, 
    StorageBackend, 
    RetrievalPolicy,
    IntegrationCredential,
    IntegrationCredentialCategory,
    Tenant,
)
from app.services.credentials_service import CredentialsService
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.knowledge_store_admin_service import KnowledgeStoreAdminService


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


async def resolve_request_tenant(
    *,
    db: AsyncSession,
    tenant_ctx: Dict[str, Any],
    tenant_slug: Optional[str],
) -> Tenant:
    tenant_id = tenant_ctx.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context is required")
    result = await db.execute(select(Tenant).where(Tenant.id == UUID(str(tenant_id))))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant_slug and str(tenant.slug) != str(tenant_slug):
        raise HTTPException(status_code=403, detail="Tenant slug does not match request context")
    return tenant


def _service_context(*, tenant_ctx: Dict[str, Any], principal: Dict[str, Any], tenant_slug: Optional[str]) -> ControlPlaneContext:
    created_by = UUID(str(principal["user_id"])) if principal.get("type") == "user" and principal.get("user_id") else None
    return ControlPlaneContext.from_tenant_context(
        tenant_ctx,
        user=principal.get("user"),
        user_id=created_by,
        auth_token=principal.get("auth_token"),
        scopes=principal.get("scopes"),
        tenant_slug=tenant_slug,
    )


async def validate_vector_store_credential(
    db: AsyncSession,
    tenant_id: UUID,
    backend: StorageBackend,
    credentials_ref: Optional[UUID],
) -> Optional[UUID]:
    if not credentials_ref:
        if backend in {StorageBackend.PINECONE, StorageBackend.QDRANT}:
            has_effective_default = await CredentialsService(db, tenant_id).has_effective_provider_credentials(
                category=IntegrationCredentialCategory.VECTOR_STORE,
                provider_key=backend.value,
            )
            if not has_effective_default:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{backend.value.capitalize()} knowledge stores require a matching tenant credential "
                        "or platform default environment key."
                    ),
                )
        return None

    cred = await db.get(IntegrationCredential, credentials_ref)
    if not cred or cred.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential not found")
    if cred.category != IntegrationCredentialCategory.VECTOR_STORE:
        raise HTTPException(status_code=422, detail="Credential must be in category 'vector_store'")
    if not cred.is_enabled:
        raise HTTPException(status_code=422, detail="Credential is disabled")

    provider_key = (cred.provider_key or "").strip().lower()
    if backend == StorageBackend.PINECONE and provider_key != "pinecone":
        raise HTTPException(status_code=422, detail="Pinecone stores require a Pinecone credential")
    if backend == StorageBackend.QDRANT and provider_key != "qdrant":
        raise HTTPException(status_code=422, detail="Qdrant stores require a Qdrant credential")
    return cred.id


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=List[KnowledgeStoreResponse])
async def list_knowledge_stores(
    tenant_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: Dict[str, Any] = Depends(get_tenant_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        stores = await KnowledgeStoreAdminService(db).list_stores(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal, tenant_slug=tenant_slug),
            tenant_slug=tenant_slug,
        )
        return [store_to_response(s) for s in stores]
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("", response_model=KnowledgeStoreResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_store(
    request: CreateKnowledgeStoreRequest,
    tenant_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: Dict[str, Any] = Depends(get_tenant_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        store = await KnowledgeStoreAdminService(db).create_store(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal, tenant_slug=tenant_slug),
            tenant_slug=tenant_slug,
            name=request.name,
            description=request.description,
            embedding_model_id=request.embedding_model_id,
            chunking_strategy=request.chunking_strategy.model_dump() if request.chunking_strategy else None,
            retrieval_policy=request.retrieval_policy,
            backend=request.backend,
            backend_config=request.backend_config,
            credentials_ref=request.credentials_ref,
        )
        return store_to_response(store)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.get("/{store_id}", response_model=KnowledgeStoreResponse)
async def get_knowledge_store(
    store_id: UUID,
    tenant_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: Dict[str, Any] = Depends(get_tenant_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        store = await KnowledgeStoreAdminService(db).get_store(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal, tenant_slug=tenant_slug),
            store_id=store_id,
            tenant_slug=tenant_slug,
        )
        return store_to_response(store)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.patch("/{store_id}", response_model=KnowledgeStoreResponse)
async def update_knowledge_store(
    store_id: UUID,
    request: UpdateKnowledgeStoreRequest,
    tenant_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: Dict[str, Any] = Depends(get_tenant_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        store = await KnowledgeStoreAdminService(db).update_store(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal, tenant_slug=tenant_slug),
            store_id=store_id,
            tenant_slug=tenant_slug,
            patch=request.model_dump(exclude_unset=True),
        )
        return store_to_response(store)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_store(
    store_id: UUID,
    tenant_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: Dict[str, Any] = Depends(get_tenant_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        await KnowledgeStoreAdminService(db).delete_store(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal, tenant_slug=tenant_slug),
            store_id=store_id,
            tenant_slug=tenant_slug,
        )
        return None
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.get("/{store_id}/stats")
async def get_knowledge_store_stats(
    store_id: UUID,
    tenant_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: Dict[str, Any] = Depends(get_tenant_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    """Get detailed statistics for a knowledge store."""
    del principal
    tenant = await resolve_request_tenant(db=db, tenant_ctx=tenant_ctx, tenant_slug=tenant_slug)
    store = await db.get(KnowledgeStore, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    if store.tenant_id != tenant.id:
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
