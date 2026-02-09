import pytest
from uuid import uuid4

from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import OrgMembership, OrgRole, Tenant, User, MembershipStatus, OrgUnit, OrgUnitType
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType, ModelStatus


@pytest.mark.asyncio
async def test_get_tenant_settings_returns_normalized_defaults(client, db_session):
    tenant = Tenant(
        name="Tenant Settings",
        slug="tenant-settings",
        settings={
            "default_chat_model_id": "chat-123",
            "default_embedding_model_id": None,
            "default_retrieval_policy": "hybrid",
        },
    )
    user = User(email="owner@tenant-settings.com", hashed_password="x", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(tenant_id=tenant.id, parent_id=None, name="Root", slug="root-settings", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.commit()

    from main import app

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.get(f"/api/tenants/{tenant.slug}/settings")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_chat_model_id"] == "chat-123"
    assert payload["default_embedding_model_id"] is None
    assert payload["default_retrieval_policy"] == "hybrid"


@pytest.mark.asyncio
async def test_patch_tenant_settings_accepts_valid_defaults(client, db_session):
    tenant = Tenant(name="Tenant Defaults", slug="tenant-defaults")
    user = User(email="owner@tenant-defaults.com", hashed_password="x", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(tenant_id=tenant.id, parent_id=None, name="Root", slug="root-defaults", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)

    chat_model = ModelRegistry(
        tenant_id=tenant.id,
        name="Chat Model",
        slug="chat-model-default",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    embedding_model = ModelRegistry(
        tenant_id=tenant.id,
        name="Embedding Model",
        slug="embed-model-default",
        capability_type=ModelCapabilityType.EMBEDDING,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add_all([chat_model, embedding_model])
    await db_session.commit()

    from main import app

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.patch(
        f"/api/tenants/{tenant.slug}/settings",
        json={
            "default_chat_model_id": str(chat_model.id),
            "default_embedding_model_id": str(embedding_model.id),
            "default_retrieval_policy": "semantic_only",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_chat_model_id"] == str(chat_model.id)
    assert payload["default_embedding_model_id"] == str(embedding_model.id)
    assert payload["default_retrieval_policy"] == "semantic_only"


@pytest.mark.asyncio
async def test_patch_tenant_settings_rejects_invalid_capability(client, db_session):
    tenant = Tenant(name="Tenant Invalid", slug="tenant-invalid-cap")
    user = User(email="owner@tenant-invalid.com", hashed_password="x", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(tenant_id=tenant.id, parent_id=None, name="Root", slug="root-invalid", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)

    wrong_model = ModelRegistry(
        tenant_id=tenant.id,
        name="Rerank Model",
        slug="rerank-model-default",
        capability_type=ModelCapabilityType.RERANK,
        status=ModelStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(wrong_model)
    await db_session.commit()

    from main import app

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.patch(
        f"/api/tenants/{tenant.slug}/settings",
        json={"default_chat_model_id": str(wrong_model.id)},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid capability/status" in response.json()["detail"]


@pytest.mark.asyncio
async def test_patch_tenant_settings_rejects_unknown_model(client, db_session):
    tenant = Tenant(name="Tenant Unknown", slug="tenant-unknown-model")
    user = User(email="owner@tenant-unknown.com", hashed_password="x", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(tenant_id=tenant.id, parent_id=None, name="Root", slug="root-unknown", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.commit()

    from main import app

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.patch(
        f"/api/tenants/{tenant.slug}/settings",
        json={"default_embedding_model_id": str(uuid4())},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid capability/status" in response.json()["detail"]
