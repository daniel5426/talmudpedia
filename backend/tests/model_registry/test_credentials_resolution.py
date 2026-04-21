import pytest
from uuid import uuid4

from app.db.postgres.models.identity import Organization
from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderBinding,
    ModelCapabilityType,
    ModelProviderType,
    ModelStatus,
    IntegrationCredential,
    IntegrationCredentialCategory,
)
from app.services.model_resolver import ModelResolver
from app.rag.providers.embedding.openai import OpenAIEmbeddingProvider


async def _seed_tenant(db_session, organization_id):
    tenant = Organization(id=organization_id, name=f"Organization {organization_id.hex[:8]}", slug=f"tenant-{organization_id.hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    return tenant


@pytest.mark.asyncio
async def test_resolve_credentials_prefers_integration_credentials(db_session):
    organization_id = uuid4()
    await _seed_tenant(db_session, organization_id)
    model = ModelRegistry(
        organization_id=organization_id,
        name="Test Chat",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    credential = IntegrationCredential(
        organization_id=organization_id,
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
        organization_id=organization_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o",
        priority=0,
        config={},
        credentials_ref=credential.id,
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, organization_id)
    payload, api_key, _ = await resolver._resolve_provider_credentials(
        binding, IntegrationCredentialCategory.LLM_PROVIDER
    )

    assert api_key == "cred-key"
    assert payload.get("api_key") == "cred-key"


@pytest.mark.asyncio
async def test_resolve_credentials_prefers_tenant_default_over_env_fallback(db_session, monkeypatch):
    organization_id = uuid4()
    provider_variant = f"tenant-{uuid4().hex[:8]}"
    monkeypatch.setenv("OPENAI_API_KEY", "env-default-key")
    await _seed_tenant(db_session, organization_id)
    model = ModelRegistry(
        organization_id=organization_id,
        name="Test Chat",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    tenant_default = IntegrationCredential(
        organization_id=organization_id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        provider_variant=provider_variant,
        display_name="Organization OpenAI Default",
        credentials={"api_key": "tenant-default-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(tenant_default)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        organization_id=organization_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o-mini",
        priority=0,
        config={"provider_variant": provider_variant},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, organization_id)
    payload, api_key, _ = await resolver._resolve_provider_credentials(
        binding, IntegrationCredentialCategory.LLM_PROVIDER
    )

    assert api_key == "tenant-default-key"
    assert payload.get("api_key") == "tenant-default-key"

@pytest.mark.asyncio
async def test_resolve_credentials_falls_back_to_env_platform_default(db_session, monkeypatch):
    organization_id = uuid4()
    provider_variant = f"platform-{uuid4().hex[:8]}"
    monkeypatch.setenv("OPENAI_API_KEY", "platform-default-key")
    await _seed_tenant(db_session, organization_id)
    model = ModelRegistry(
        organization_id=organization_id,
        name="Test Chat",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        organization_id=organization_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o-mini",
        priority=0,
        config={"provider_variant": provider_variant},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, organization_id)
    payload, api_key, _ = await resolver._resolve_provider_credentials(
        binding, IntegrationCredentialCategory.LLM_PROVIDER
    )

    assert api_key == "platform-default-key"
    assert payload.get("api_key") == "platform-default-key"


@pytest.mark.asyncio
async def test_resolve_embedding_uses_integration_credentials(db_session):
    organization_id = uuid4()
    await _seed_tenant(db_session, organization_id)
    model = ModelRegistry(
        organization_id=organization_id,
        name="Test Embed",
        capability_type=ModelCapabilityType.EMBEDDING,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    credential = IntegrationCredential(
        organization_id=organization_id,
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
        organization_id=organization_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="text-embedding-3-small",
        priority=0,
        config={},
        credentials_ref=credential.id,
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    resolver = ModelResolver(db_session, organization_id)
    provider = await resolver.resolve_embedding(str(model.id))

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider._api_key == "embed-key"
