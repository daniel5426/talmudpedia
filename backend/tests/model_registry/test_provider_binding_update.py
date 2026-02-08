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
from app.api.routers.auth import get_current_user
from app.api.dependencies import get_tenant_context


@pytest.mark.asyncio
async def test_update_provider_binding_endpoint(client, db_session):
    tenant = Tenant(name="Test Org", slug="test-org")
    user = User(email="admin@test.org", hashed_password="test", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Test Chat",
        slug=f"test-chat-{uuid4().hex}",
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
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o",
        priority=0,
        config={},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    from main import app

    async def override_get_current_user():
        return user

    async def override_get_tenant_context():
        return {"tenant_id": str(tenant.id), "tenant": tenant}

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_tenant_context] = override_get_tenant_context

    response = await client.patch(
        f"/models/{model.id}/providers/{binding.id}",
        json={
            "priority": 2,
            "is_enabled": False,
            "credentials_ref": str(credential.id),
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["priority"] == 2
    assert payload["is_enabled"] is False
    assert payload["credentials_ref"] == str(credential.id)
