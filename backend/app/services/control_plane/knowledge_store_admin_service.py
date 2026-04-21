from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models import (
    IntegrationCredential,
    IntegrationCredentialCategory,
    KnowledgeStore,
    KnowledgeStoreStatus,
    RetrievalPolicy,
    StorageBackend,
    Organization,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import forbidden, not_found, validation
from app.services.credentials_service import CredentialsService


def _normalize_retrieval_policy(value: RetrievalPolicy | str | None) -> RetrievalPolicy:
    if isinstance(value, RetrievalPolicy):
        return value
    raw = str(value or RetrievalPolicy.SEMANTIC_ONLY.value).strip().lower()
    try:
        return RetrievalPolicy(raw)
    except ValueError as exc:
        raise validation("Invalid retrieval_policy", field="retrieval_policy", value=raw) from exc


def _normalize_storage_backend(value: StorageBackend | str | None) -> StorageBackend:
    if isinstance(value, StorageBackend):
        return value
    raw = str(value or StorageBackend.PGVECTOR.value).strip().lower()
    try:
        return StorageBackend(raw)
    except ValueError as exc:
        raise validation("Invalid backend", field="backend", value=raw) from exc


async def resolve_request_tenant(
    *,
    db: AsyncSession,
    ctx: ControlPlaneContext,
    organization_id: str | None,
) -> Organization:
    organization = (await db.execute(select(Organization).where(Organization.id == ctx.organization_id))).scalar_one_or_none()
    if organization is None:
        raise not_found("Organization not found")
    if organization_id and str(organization.id) != str(organization_id):
        raise forbidden("Organization does not match request context")
    return organization


async def validate_vector_store_credential(
    *,
    db: AsyncSession,
    organization_id: UUID,
    backend: StorageBackend,
    credentials_ref: UUID | None,
) -> UUID | None:
    if not credentials_ref:
        if backend in {StorageBackend.PINECONE, StorageBackend.QDRANT}:
            has_default = await CredentialsService(db, organization_id).has_effective_provider_credentials(
                category=IntegrationCredentialCategory.VECTOR_STORE,
                provider_key=backend.value,
            )
            if not has_default:
                raise validation(
                    f"{backend.value.capitalize()} knowledge stores require a matching organization credential or platform default environment key."
                )
        return None
    cred = await db.get(IntegrationCredential, credentials_ref)
    if not cred or cred.organization_id != organization_id:
        raise not_found("Credential not found")
    if cred.category != IntegrationCredentialCategory.VECTOR_STORE:
        raise validation("Credential must be in category 'vector_store'")
    if not cred.is_enabled:
        raise validation("Credential is disabled")
    provider_key = (cred.provider_key or "").strip().lower()
    if backend == StorageBackend.PINECONE and provider_key != "pinecone":
        raise validation("Pinecone stores require a Pinecone credential")
    if backend == StorageBackend.QDRANT and provider_key != "qdrant":
        raise validation("Qdrant stores require a Qdrant credential")
    return cred.id


def serialize_store(store: KnowledgeStore, *, view: str = "full") -> dict[str, Any]:
    payload = {
        "id": str(store.id),
        "organization_id": str(store.organization_id),
        "name": store.name,
        "description": store.description,
        "embedding_model_id": store.embedding_model_id,
        "retrieval_policy": getattr(store.retrieval_policy, "value", store.retrieval_policy),
        "backend": getattr(store.backend, "value", store.backend),
        "status": getattr(store.status, "value", store.status),
        "document_count": int(store.document_count or 0),
        "chunk_count": int(store.chunk_count or 0),
        "created_at": store.created_at.isoformat() if store.created_at else None,
        "updated_at": store.updated_at.isoformat() if store.updated_at else None,
    }
    if view == "summary":
        return payload
    payload.update(
        {
            "chunking_strategy": store.chunking_strategy or {},
            "backend_config": store.backend_config or {},
            "credentials_ref": str(store.credentials_ref) if store.credentials_ref else None,
            "created_by": str(store.created_by) if store.created_by else None,
        }
    )
    return payload


class KnowledgeStoreAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_stores(self, *, ctx: ControlPlaneContext, organization_id: str | None = None) -> list[KnowledgeStore]:
        organization = await resolve_request_tenant(db=self.db, ctx=ctx, organization_id=organization_id)
        stmt = (
            select(KnowledgeStore)
            .where(KnowledgeStore.organization_id == organization.id)
            .where(KnowledgeStore.status != KnowledgeStoreStatus.ARCHIVED)
            .order_by(KnowledgeStore.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_store(self, *, ctx: ControlPlaneContext, store_id: UUID, organization_id: str | None = None) -> KnowledgeStore:
        organization = await resolve_request_tenant(db=self.db, ctx=ctx, organization_id=organization_id)
        store = await self.db.get(KnowledgeStore, store_id)
        if not store or store.organization_id != organization.id:
            raise not_found("Knowledge store not found")
        return store

    async def create_store(
        self,
        *,
        ctx: ControlPlaneContext,
        organization_id: str | None,
        name: str,
        description: str | None,
        embedding_model_id: str,
        chunking_strategy: dict[str, Any] | None,
        retrieval_policy: RetrievalPolicy,
        backend: StorageBackend,
        backend_config: dict[str, Any],
        credentials_ref: UUID | None,
    ) -> KnowledgeStore:
        organization = await resolve_request_tenant(db=self.db, ctx=ctx, organization_id=organization_id)
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise validation("name is required", field="name")
        normalized_embedding_model_id = str(embedding_model_id or "").strip()
        if not normalized_embedding_model_id:
            raise validation("embedding_model_id is required", field="embedding_model_id")
        normalized_retrieval_policy = _normalize_retrieval_policy(retrieval_policy)
        normalized_backend = _normalize_storage_backend(backend)
        validated_credential_ref = await validate_vector_store_credential(
            db=self.db,
            organization_id=organization.id,
            backend=normalized_backend,
            credentials_ref=credentials_ref,
        )
        chunking = chunking_strategy or {"strategy": "recursive", "chunk_size": 512, "chunk_overlap": 50}
        effective_backend_config = dict(backend_config or {})
        if not effective_backend_config:
            safe_name = normalized_name.lower().replace(" ", "_").replace("-", "_")[:32]
            effective_backend_config = {
                "index_name": f"ks_{safe_name}_{str(organization.id)[:8]}",
                "namespace": "default",
            }
        store = KnowledgeStore(
            organization_id=organization.id,
            name=normalized_name,
            description=description,
            embedding_model_id=normalized_embedding_model_id,
            chunking_strategy=chunking,
            retrieval_policy=normalized_retrieval_policy,
            backend=normalized_backend,
            backend_config=effective_backend_config,
            credentials_ref=validated_credential_ref,
            status=KnowledgeStoreStatus.ACTIVE,
            created_by=ctx.user_id,
        )
        self.db.add(store)
        await self.db.commit()
        await self.db.refresh(store)
        return store

    async def update_store(
        self,
        *,
        ctx: ControlPlaneContext,
        store_id: UUID,
        organization_id: str | None,
        patch: dict[str, Any],
    ) -> KnowledgeStore:
        store = await self.get_store(ctx=ctx, store_id=store_id, organization_id=organization_id)
        if patch.get("name") is not None:
            store.name = patch["name"]
        if patch.get("description") is not None:
            store.description = patch["description"]
        if patch.get("retrieval_policy") is not None:
            store.retrieval_policy = patch["retrieval_policy"]
        if "credentials_ref" in patch:
            store.credentials_ref = await validate_vector_store_credential(
                db=self.db,
                organization_id=store.organization_id,
                backend=store.backend,
                credentials_ref=patch.get("credentials_ref"),
            )
        await self.db.commit()
        await self.db.refresh(store)
        return store

    async def delete_store(self, *, ctx: ControlPlaneContext, store_id: UUID, organization_id: str | None = None) -> None:
        store = await self.get_store(ctx=ctx, store_id=store_id, organization_id=organization_id)
        store.status = KnowledgeStoreStatus.ARCHIVED
        await self.db.commit()
