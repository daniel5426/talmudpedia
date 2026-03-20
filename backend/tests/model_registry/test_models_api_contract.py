import pytest
from uuid import uuid4

from sqlalchemy import select

from app.api.dependencies import get_current_principal, get_tenant_context
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)


async def _override_model_registry_auth(app, *, tenant: Tenant, user: User) -> None:
    async def override_get_tenant_context():
        return {"tenant_id": str(tenant.id), "tenant": tenant}

    async def override_get_current_principal():
        return {
            "type": "user",
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "scopes": ["*"],
        }

    app.dependency_overrides[get_tenant_context] = override_get_tenant_context
    app.dependency_overrides[get_current_principal] = override_get_current_principal


@pytest.mark.asyncio
async def test_models_list_total_matches_filters_and_response_shape(client, db_session):
    tenant = Tenant(name="Tenant A", slug=f"tenant-a-{uuid4().hex[:8]}")
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    db_session.add_all(
        [
            ModelRegistry(
                tenant_id=tenant.id,
                name="Chat Active",
                capability_type=ModelCapabilityType.CHAT,
                status=ModelStatus.ACTIVE,
                is_active=True,
                metadata_={},
            ),
            ModelRegistry(
                tenant_id=tenant.id,
                name="Chat Disabled",
                capability_type=ModelCapabilityType.CHAT,
                status=ModelStatus.DISABLED,
                is_active=False,
                metadata_={},
            ),
            ModelRegistry(
                tenant_id=tenant.id,
                name="Embedding Active",
                capability_type=ModelCapabilityType.EMBEDDING,
                status=ModelStatus.ACTIVE,
                is_active=True,
                metadata_={},
            ),
        ]
    )
    await db_session.commit()

    from main import app

    await _override_model_registry_auth(app, tenant=tenant, user=user)
    response = await client.get("/models?capability_type=chat&status=active&is_active=true")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == len(payload["models"])
    assert "slug" not in payload["models"][0]
    returned_names = {item["name"] for item in payload["models"]}
    assert "Chat Active" in returned_names
    assert "Chat Disabled" not in returned_names
    assert "Embedding Active" not in returned_names


@pytest.mark.asyncio
async def test_setting_default_model_clears_previous_default(client, db_session):
    tenant = Tenant(name="Tenant B", slug=f"tenant-b-{uuid4().hex[:8]}")
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    first = ModelRegistry(
        tenant_id=tenant.id,
        name="First Default",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        is_default=True,
        metadata_={},
    )
    second = ModelRegistry(
        tenant_id=tenant.id,
        name="Second Default",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        is_default=False,
        metadata_={},
    )
    db_session.add_all([first, second])
    await db_session.commit()

    from main import app

    await _override_model_registry_auth(app, tenant=tenant, user=user)
    response = await client.put(
        f"/models/{second.id}",
        json={"is_default": True},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.is_default is False
    assert second.is_default is True


@pytest.mark.asyncio
async def test_add_provider_rejects_unsupported_capability_provider_pair(client, db_session):
    tenant = Tenant(name="Tenant C", slug=f"tenant-c-{uuid4().hex[:8]}")
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Embed Model",
        capability_type=ModelCapabilityType.EMBEDDING,
        status=ModelStatus.ACTIVE,
        is_active=True,
        metadata_={},
    )
    db_session.add(model)
    await db_session.commit()

    from main import app

    await _override_model_registry_auth(app, tenant=tenant, user=user)
    response = await client.post(
        f"/models/{model.id}/providers",
        json={
            "provider": ModelProviderType.ANTHROPIC.value,
            "provider_model_id": "text-embeddings-not-real",
            "priority": 0,
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "not supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_model_endpoint_does_not_accept_or_return_slug(client, db_session):
    tenant = Tenant(name="Tenant D", slug=f"tenant-d-{uuid4().hex[:8]}")
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()

    from main import app

    await _override_model_registry_auth(app, tenant=tenant, user=user)
    response = await client.post(
        "/models",
        json={
            "name": "API Created",
            "capability_type": "chat",
            "slug": "legacy-slug",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "API Created"
    assert "slug" not in payload

    rows = (
        await db_session.execute(
            select(ModelRegistry).where(ModelRegistry.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].system_key is None
