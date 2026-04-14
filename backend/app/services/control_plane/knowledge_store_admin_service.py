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
    Tenant,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import forbidden, not_found, validation
from app.services.credentials_service import CredentialsService


async def resolve_request_tenant(
    *,
    db: AsyncSession,
    ctx: ControlPlaneContext,
    tenant_slug: str | None,
) -> Tenant:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))).scalar_one_or_none()
    if tenant is None:
        raise not_found("Tenant not found")
    if tenant_slug and str(tenant.slug) != str(tenant_slug):
        raise forbidden("Tenant slug does not match request context")
    return tenant


async def validate_vector_store_credential(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    backend: StorageBackend,
    credentials_ref: UUID | None,
) -> UUID | None:
    if not credentials_ref:
        if backend in {StorageBackend.PINECONE, StorageBackend.QDRANT}:
            has_default = await CredentialsService(db, tenant_id).has_effective_provider_credentials(
                category=IntegrationCredentialCategory.VECTOR_STORE,
                provider_key=backend.value,
            )
            if not has_default:
                raise validation(
                    f"{backend.value.capitalize()} knowledge stores require a matching tenant credential or platform default environment key."
                )
        return None
    cred = await db.get(IntegrationCredential, credentials_ref)
    if not cred or cred.tenant_id != tenant_id:
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
        "tenant_id": str(store.tenant_id),
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

    async def list_stores(self, *, ctx: ControlPlaneContext, tenant_slug: str | None = None) -> list[KnowledgeStore]:
        tenant = await resolve_request_tenant(db=self.db, ctx=ctx, tenant_slug=tenant_slug)
        stmt = (
            select(KnowledgeStore)
            .where(KnowledgeStore.tenant_id == tenant.id)
            .where(KnowledgeStore.status != KnowledgeStoreStatus.ARCHIVED)
            .order_by(KnowledgeStore.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_store(self, *, ctx: ControlPlaneContext, store_id: UUID, tenant_slug: str | None = None) -> KnowledgeStore:
        tenant = await resolve_request_tenant(db=self.db, ctx=ctx, tenant_slug=tenant_slug)
        store = await self.db.get(KnowledgeStore, store_id)
        if not store or store.tenant_id != tenant.id:
            raise not_found("Knowledge store not found")
        return store

    async def create_store(
        self,
        *,
        ctx: ControlPlaneContext,
        tenant_slug: str | None,
        name: str,
        description: str | None,
        embedding_model_id: str,
        chunking_strategy: dict[str, Any] | None,
        retrieval_policy: RetrievalPolicy,
        backend: StorageBackend,
        backend_config: dict[str, Any],
        credentials_ref: UUID | None,
    ) -> KnowledgeStore:
        tenant = await resolve_request_tenant(db=self.db, ctx=ctx, tenant_slug=tenant_slug)
        validated_credential_ref = await validate_vector_store_credential(
            db=self.db,
            tenant_id=tenant.id,
            backend=backend,
            credentials_ref=credentials_ref,
        )
        chunking = chunking_strategy or {"strategy": "recursive", "chunk_size": 512, "chunk_overlap": 50}
        effective_backend_config = dict(backend_config or {})
        if not effective_backend_config:
            safe_name = name.lower().replace(" ", "_").replace("-", "_")[:32]
            effective_backend_config = {
                "index_name": f"ks_{safe_name}_{str(tenant.id)[:8]}",
                "namespace": "default",
            }
        store = KnowledgeStore(
            tenant_id=tenant.id,
            name=name,
            description=description,
            embedding_model_id=embedding_model_id,
            chunking_strategy=chunking,
            retrieval_policy=retrieval_policy,
            backend=backend,
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
        tenant_slug: str | None,
        patch: dict[str, Any],
    ) -> KnowledgeStore:
        store = await self.get_store(ctx=ctx, store_id=store_id, tenant_slug=tenant_slug)
        if patch.get("name") is not None:
            store.name = patch["name"]
        if patch.get("description") is not None:
            store.description = patch["description"]
        if patch.get("retrieval_policy") is not None:
            store.retrieval_policy = patch["retrieval_policy"]
        if "credentials_ref" in patch:
            store.credentials_ref = await validate_vector_store_credential(
                db=self.db,
                tenant_id=store.tenant_id,
                backend=store.backend,
                credentials_ref=patch.get("credentials_ref"),
            )
        await self.db.commit()
        await self.db.refresh(store)
        return store

    async def delete_store(self, *, ctx: ControlPlaneContext, store_id: UUID, tenant_slug: str | None = None) -> None:
        store = await self.get_store(ctx=ctx, store_id=store_id, tenant_slug=tenant_slug)
        store.status = KnowledgeStoreStatus.ARCHIVED
        await self.db.commit()
