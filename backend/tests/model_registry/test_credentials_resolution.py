import pytest
from uuid import uuid4

from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderBinding,
    ModelCapabilityType,
    ModelProviderType,
    ModelStatus,
    IntegrationCredential,
    IntegrationCredentialCategory,
    ProviderConfig,
)
from app.services.model_resolver import ModelResolver
from app.rag.providers.embedding.openai import OpenAIEmbeddingProvider


@pytest.mark.asyncio
async def test_resolve_credentials_prefers_integration_credentials(db_session):
    tenant_id = uuid4()
    model = ModelRegistry(
        tenant_id=tenant_id,
        name="Test Chat",
        slug="test-chat",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    credential = IntegrationCredential(
        tenant_id=tenant_id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        provider_variant=None,
        display_name="OpenAI Primary",
        credentials={"api_key": "cred-key"},
        is_enabled=True,
    )
    db_session.add(credential)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o",
        priority=0,
        config={},
        credentials_ref=credential.id,
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, tenant_id)
    payload, api_key, _ = await resolver._resolve_provider_credentials(
        binding, IntegrationCredentialCategory.LLM_PROVIDER
    )

    assert api_key == "cred-key"
    assert payload.get("api_key") == "cred-key"


@pytest.mark.asyncio
async def test_resolve_credentials_falls_back_to_provider_config(db_session):
    tenant_id = uuid4()
    model = ModelRegistry(
        tenant_id=tenant_id,
        name="Test Chat",
        slug="test-chat-legacy",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    provider_config = ProviderConfig(
        tenant_id=tenant_id,
        provider=ModelProviderType.OPENAI,
        provider_variant=None,
        credentials={"api_key": "legacy-key"},
        is_enabled=True,
    )
    db_session.add(provider_config)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o-mini",
        priority=0,
        config={},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, tenant_id)
    payload, api_key, _ = await resolver._resolve_provider_credentials(
        binding, IntegrationCredentialCategory.LLM_PROVIDER
    )

    assert api_key == "legacy-key"
    assert payload.get("api_key") == "legacy-key"


@pytest.mark.asyncio
async def test_resolve_embedding_uses_integration_credentials(db_session):
    tenant_id = uuid4()
    model = ModelRegistry(
        tenant_id=tenant_id,
        name="Test Embed",
        slug="test-embed",
        capability_type=ModelCapabilityType.EMBEDDING,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    credential = IntegrationCredential(
        tenant_id=tenant_id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        provider_variant=None,
        display_name="OpenAI Embedding",
        credentials={"api_key": "embed-key"},
        is_enabled=True,
    )
    db_session.add(credential)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="text-embedding-3-small",
        priority=0,
        config={},
        credentials_ref=credential.id,
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, tenant_id)
    provider = await resolver.resolve_embedding(str(model.id))

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider._api_key == "embed-key"
