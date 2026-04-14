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
)
from app.db.postgres.models.identity import Tenant, User
from app.api.dependencies import get_current_principal, get_tenant_context


@pytest.mark.asyncio
async def test_update_provider_binding_endpoint_allows_local_pricing(client, db_session):
    tenant = Tenant(name="Test Org", slug=f"test-org-{uuid4().hex[:8]}")
    user = User(email=f"admin-{uuid4().hex[:8]}@test.org", hashed_password="test", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Test Chat",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    credential = IntegrationCredential(
        tenant_id=tenant.id,
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
        tenant_id=tenant.id,
        provider=ModelProviderType.LOCAL,
        provider_model_id="local-llm",
        priority=0,
        config={},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    from main import app

    async def override_get_tenant_context():
        return {"tenant_id": str(tenant.id), "tenant": tenant}

    async def override_get_current_principal():
        return {
            "type": "user",
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "scopes": ["*"],
        }

    app.dependency_overrides[get_current_principal] = override_get_current_principal
    app.dependency_overrides[get_tenant_context] = override_get_tenant_context

    response = await client.patch(
        f"/models/{model.id}/providers/{binding.id}",
        json={
            "priority": 2,
            "is_enabled": False,
            "credentials_ref": str(credential.id),
            "pricing_config": {
                "currency": "USD",
                "billing_mode": "per_1k_tokens",
                "rates": {"input": 0.001, "output": 0.002},
            },
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["priority"] == 2
    assert payload["is_enabled"] is False
    assert payload["credentials_ref"] == str(credential.id)
    assert payload["pricing_config"]["billing_mode"] == "per_1k_tokens"
    assert payload["pricing_config"]["rates"]["input"] == 0.001


@pytest.mark.asyncio
async def test_update_provider_binding_rejects_platform_managed_pricing_override(client, db_session):
    tenant = Tenant(name="Test Org 2", slug=f"test-org-{uuid4().hex[:8]}")
    user = User(email=f"admin-{uuid4().hex[:8]}@test.org", hashed_password="test", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Test Chat 2",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant.id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-5.4",
        priority=0,
        config={},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    from main import app

    async def override_get_tenant_context():
        return {"tenant_id": str(tenant.id), "tenant": tenant}

    async def override_get_current_principal():
        return {
            "type": "user",
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "scopes": ["*"],
        }

    app.dependency_overrides[get_current_principal] = override_get_current_principal
    app.dependency_overrides[get_tenant_context] = override_get_tenant_context

    response = await client.patch(
        f"/models/{model.id}/providers/{binding.id}",
        json={
            "pricing_config": {
                "currency": "USD",
                "billing_mode": "per_1k_tokens",
                "rates": {"input": 0.001, "output": 0.002},
            },
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "platform-managed" in response.json()["detail"]
