"""
Knowledge Stores Router - CRUD for logical knowledge repositories.

This router manages KnowledgeStore entities which abstract away
vector database implementation details.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.db.postgres.session import get_db
from app.api.dependencies import get_current_principal, get_organization_context, require_scopes
from app.db.postgres.models import (
    KnowledgeStore, 
    KnowledgeStoreStatus, 
    StorageBackend, 
    RetrievalPolicy,
    IntegrationCredential,
    IntegrationCredentialCategory,
    Organization,
)
from app.services.credentials_service import CredentialsService
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.knowledge_store_admin_service import KnowledgeStoreAdminService, serialize_store


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
    organization_id: UUID
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
        organization_id=store.organization_id,
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
    organization_ctx: Dict[str, Any],
    organization_id: Optional[str],
) -> Organization:
    organization_id= organization_ctx.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=400, detail="Organization context is required")
    result = await db.execute(select(Organization).where(Organization.id == UUID(str(organization_id))))
    organization = result.scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if organization_id and str(organization.id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Organization does not match request context")
    return organization


def _service_context(*, organization_ctx: Dict[str, Any], principal: Dict[str, Any], organization_id: Optional[str]) -> ControlPlaneContext:
    created_by = UUID(str(principal["user_id"])) if principal.get("type") == "user" and principal.get("user_id") else None
    return ControlPlaneContext.from_organization_context(
        {
            "organization_id": organization_ctx.get("organization_id") or organization_ctx.get("organization_id"),
            "project_id": organization_ctx.get("project_id"),
        },
        user=principal.get("user"),
        user_id=created_by,
        auth_token=principal.get("auth_token"),
        scopes=principal.get("scopes"),
    )


async def validate_vector_store_credential(
    db: AsyncSession,
    organization_id: UUID,
    backend: StorageBackend,
    credentials_ref: Optional[UUID],
) -> Optional[UUID]:
    if not credentials_ref:
        if backend in {StorageBackend.PINECONE, StorageBackend.QDRANT}:
            has_effective_default = await CredentialsService(db, organization_id).has_effective_provider_credentials(
                category=IntegrationCredentialCategory.VECTOR_STORE,
                provider_key=backend.value,
            )
            if not has_effective_default:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{backend.value.capitalize()} knowledge stores require a matching organization credential "
                        "or platform default environment key."
                    ),
                )
        return None

    cred = await db.get(IntegrationCredential, credentials_ref)
    if not cred or cred.organization_id != organization_id:
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

@router.get("", response_model=Dict[str, Any])
async def list_knowledge_stores(
    organization_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    view: str = "summary",
    db: AsyncSession = Depends(get_db),
    organization_ctx: Dict[str, Any] = Depends(get_organization_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        query = ListQuery.from_payload({"skip": skip, "limit": limit, "view": view})
        stores = await KnowledgeStoreAdminService(db).list_stores(
            ctx=_service_context(organization_ctx=organization_ctx, principal=principal, organization_id=organization_id),
            organization_id=organization_id,
        )
        sliced = stores[query.skip: query.skip + query.limit]
        return {
            "items": [serialize_store(s, view=query.view) for s in sliced],
            "total": len(stores),
            "has_more": query.skip + len(sliced) < len(stores),
            "skip": query.skip,
            "limit": query.limit,
            "view": query.view,
        }
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("", response_model=KnowledgeStoreResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_store(
    request: CreateKnowledgeStoreRequest,
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    organization_ctx: Dict[str, Any] = Depends(get_organization_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        store = await KnowledgeStoreAdminService(db).create_store(
            ctx=_service_context(organization_ctx=organization_ctx, principal=principal, organization_id=organization_id),
            organization_id=organization_id,
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
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    organization_ctx: Dict[str, Any] = Depends(get_organization_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        store = await KnowledgeStoreAdminService(db).get_store(
            ctx=_service_context(organization_ctx=organization_ctx, principal=principal, organization_id=organization_id),
            store_id=store_id,
            organization_id=organization_id,
        )
        return store_to_response(store)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.patch("/{store_id}", response_model=KnowledgeStoreResponse)
async def update_knowledge_store(
    store_id: UUID,
    request: UpdateKnowledgeStoreRequest,
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    organization_ctx: Dict[str, Any] = Depends(get_organization_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        store = await KnowledgeStoreAdminService(db).update_store(
            ctx=_service_context(organization_ctx=organization_ctx, principal=principal, organization_id=organization_id),
            store_id=store_id,
            organization_id=organization_id,
            patch=request.model_dump(exclude_unset=True),
        )
        return store_to_response(store)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_store(
    store_id: UUID,
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    organization_ctx: Dict[str, Any] = Depends(get_organization_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    try:
        await KnowledgeStoreAdminService(db).delete_store(
            ctx=_service_context(organization_ctx=organization_ctx, principal=principal, organization_id=organization_id),
            store_id=store_id,
            organization_id=organization_id,
        )
        return None
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.get("/{store_id}/stats")
async def get_knowledge_store_stats(
    store_id: UUID,
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    organization_ctx: Dict[str, Any] = Depends(get_organization_context),
    _: Dict[str, Any] = Depends(require_scopes("knowledge_stores.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
):
    """Get detailed statistics for a knowledge store."""
    del principal
    organization = await resolve_request_tenant(db=db, organization_ctx=organization_ctx, organization_id=organization_id)
    store = await db.get(KnowledgeStore, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    if store.organization_id != organization.id:
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
