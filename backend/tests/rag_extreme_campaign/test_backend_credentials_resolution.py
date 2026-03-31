from __future__ import annotations

import uuid

import pytest

from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.credentials_service import CredentialsService


@pytest.mark.asyncio
async def test_credentials_service_env_fallback_preserves_protected_backend_keys(db_session, monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "env-secret")

    resolved = await CredentialsService(db_session, None).resolve_backend_config(
        {
            "index_name": "app-owned-index",
            "namespace": "app-owned-namespace",
            "collection_name": "app-owned-collection",
        },
        None,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key="pinecone",
    )

    assert resolved["api_key"] == "env-secret"
    assert resolved["index_name"] == "app-owned-index"
    assert resolved["namespace"] == "app-owned-namespace"
    assert resolved["collection_name"] == "app-owned-collection"


@pytest.mark.asyncio
async def test_credentials_service_default_provider_credential_preserves_protected_backend_keys(
    db_session, test_tenant_id
):
    provider_key = f"pinecone-campaign-{uuid.uuid4().hex[:8]}"
    credential = IntegrationCredential(
        id=uuid.uuid4(),
        tenant_id=test_tenant_id,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key=provider_key,
        provider_variant=None,
        display_name="Pinecone Default",
        credentials={
            "api_key": "db-secret",
            "index_name": "credential-owned-index",
            "namespace": "credential-owned-namespace",
        },
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.commit()

    resolved = await CredentialsService(db_session, test_tenant_id).resolve_backend_config(
        {
            "index_name": "app-owned-index",
            "namespace": "app-owned-namespace",
            "collection_name": "app-owned-collection",
        },
        None,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key=provider_key,
    )

    assert resolved["api_key"] == "db-secret"
    assert resolved["index_name"] == "app-owned-index"
    assert resolved["namespace"] == "app-owned-namespace"
    assert resolved["collection_name"] == "app-owned-collection"


@pytest.mark.asyncio
async def test_credentials_service_rejects_disabled_explicit_credential(db_session, test_tenant_id):
    credential = IntegrationCredential(
        id=uuid.uuid4(),
        tenant_id=test_tenant_id,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key="pinecone",
        provider_variant=None,
        display_name="Disabled Pinecone",
        credentials={"api_key": "disabled-secret"},
        is_enabled=False,
        is_default=False,
    )
    db_session.add(credential)
    await db_session.commit()

    with pytest.raises(ValueError, match="Credentials disabled"):
        await CredentialsService(db_session, test_tenant_id).resolve_backend_config(
            {"index_name": "app-owned-index"},
            credential.id,
            category=IntegrationCredentialCategory.VECTOR_STORE,
            provider_key="pinecone",
        )
