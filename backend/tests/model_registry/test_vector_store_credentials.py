import pytest
from uuid import uuid4

from app.db.postgres.models.identity import Organization
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.db.postgres.models.rag import KnowledgeStore, StorageBackend, RetrievalPolicy, KnowledgeStoreStatus
from app.services.retrieval_service import RetrievalService


async def _seed_tenant(db_session, organization_id):
    tenant = Organization(id=organization_id, name=f"Organization {organization_id.hex[:8]}", slug=f"tenant-{organization_id.hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    return tenant


@pytest.mark.asyncio
async def test_vector_store_credentials_merge(db_session):
    organization_id = uuid4()
    await _seed_tenant(db_session, organization_id)
    credential = IntegrationCredential(
        organization_id=organization_id,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key="pinecone",
        provider_variant=None,
        display_name="Pinecone Key",
        credentials={"api_key": "pinecone-key", "environment": "us-east-1"},
        is_enabled=True,
    )
    db_session.add(credential)
    await db_session.flush()

    store = KnowledgeStore(
        organization_id=organization_id,
        name="Test Store",
        description="",
        embedding_model_id="test-embed",
        chunking_strategy={"strategy": "recursive"},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PINECONE,
        backend_config={"index_name": "test-index"},
        credentials_ref=credential.id,
        status=KnowledgeStoreStatus.ACTIVE,
    )
    db_session.add(store)
    await db_session.commit()

    service = RetrievalService(db_session)
    merged = await service._resolve_backend_config(store)

    assert merged["index_name"] == "test-index"
    assert merged["api_key"] == "pinecone-key"
    assert merged["environment"] == "us-east-1"


@pytest.mark.asyncio
async def test_vector_store_credentials_disabled_raises(db_session):
    organization_id = uuid4()
    await _seed_tenant(db_session, organization_id)
    credential = IntegrationCredential(
        organization_id=organization_id,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key="pinecone",
        provider_variant=None,
        display_name="Pinecone Disabled",
        credentials={"api_key": "pinecone-key"},
        is_enabled=False,
    )
    db_session.add(credential)
    await db_session.commit()

    service = RetrievalService(db_session)
    with pytest.raises(ValueError):
        store = KnowledgeStore(
            organization_id=organization_id,
            name="Disabled Store",
            description="",
            embedding_model_id="test-embed",
            chunking_strategy={"strategy": "recursive"},
            retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
            backend=StorageBackend.PINECONE,
            backend_config={},
            credentials_ref=credential.id,
            status=KnowledgeStoreStatus.ACTIVE,
        )
        db_session.add(store)
        await db_session.commit()
        await service._resolve_backend_config(store)
