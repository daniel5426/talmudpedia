import pytest
from uuid import uuid4

from app.db.postgres.models.registry import (
    IntegrationCredential,
    IntegrationCredentialCategory,
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)
from app.services.model_resolver import ModelResolver, ModelResolverError


@pytest.mark.asyncio
async def test_resolver_ignores_disabled_tenant_binding_when_global_binding_is_enabled(
    db_session,
):
    tenant_id = uuid4()
    model = ModelRegistry(
        tenant_id=None,
        name="Shared Chat",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    db_session.add(
        IntegrationCredential(
            tenant_id=tenant_id,
            category=IntegrationCredentialCategory.LLM_PROVIDER,
            provider_key="openai",
            provider_variant=None,
            display_name="OpenAI Default",
            credentials={"api_key": "tenant-openai-key"},
            is_enabled=True,
            is_default=True,
        )
    )
    await db_session.flush()

    db_session.add_all(
        [
            ModelProviderBinding(
                model_id=model.id,
                tenant_id=tenant_id,
                provider=ModelProviderType.XAI,
                provider_model_id="grok-4",
                priority=0,
                config={},
                is_enabled=False,
            ),
            ModelProviderBinding(
                model_id=model.id,
                tenant_id=None,
                provider=ModelProviderType.OPENAI,
                provider_model_id="gpt-4o-mini",
                priority=1,
                config={},
                is_enabled=True,
            ),
        ]
    )
    await db_session.commit()

    resolver = ModelResolver(db_session, tenant_id)
    provider = await resolver.resolve(str(model.id))

    assert provider.model_name == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_resolver_rejects_legacy_slug_identity(db_session):
    tenant_id = uuid4()
    resolver = ModelResolver(db_session, tenant_id)

    with pytest.raises(ModelResolverError, match="Model not found"):
        await resolver.resolve("legacy-slug")
