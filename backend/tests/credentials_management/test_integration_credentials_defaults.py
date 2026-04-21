from uuid import uuid4

import pytest

from app.api.dependencies import get_tenant_context
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.registry import (
    IntegrationCredential,
    IntegrationCredentialCategory,
    ModelRegistry,
    ModelProviderBinding,
    ModelProviderType,
    ModelCapabilityType,
    ToolRegistry,
    ToolDefinitionScope,
)
from app.db.postgres.models.rag import KnowledgeStore, StorageBackend
from app.services.credentials_service import CredentialsService


@pytest.mark.asyncio
async def test_default_resolution_prefers_tenant_default_over_env(db_session, monkeypatch):
    tenant = Organization(name="Default Resolution Organization", slug=f"default-resolution-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    organization_id = tenant.id
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")
    tenant_default = IntegrationCredential(
        organization_id=organization_id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        provider_variant=None,
        display_name="Organization OpenAI",
        credentials={"api_key": "tenant-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(tenant_default)
    await db_session.commit()

    resolved = await CredentialsService(db_session, organization_id).get_default_provider_credential(
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
    )

    assert resolved is not None
    assert resolved.id == tenant_default.id
    assert resolved.credentials.get("api_key") == "tenant-key"

    merged = await CredentialsService(db_session, organization_id).resolve_backend_config(
        {},
        None,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
    )
    assert merged.get("api_key") == "tenant-key"


@pytest.mark.asyncio
async def test_create_credentials_switches_default_for_same_provider(client, db_session):
    tenant = Organization(name="Credentials Organization", slug=f"creds-{uuid4().hex[:8]}")
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="test", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()

    from main import app

    async def override_get_current_user():
        return user

    async def override_get_tenant_context():
        return {"organization_id": str(tenant.id), "tenant": tenant}

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_tenant_context] = override_get_tenant_context

    try:
        payload_one = {
            "category": "llm_provider",
            "provider_key": "openai",
            "provider_variant": None,
            "display_name": "OpenAI Primary",
            "credentials": {"api_key": "key-1"},
            "is_enabled": True,
            "is_default": True,
        }
        payload_two = {
            "category": "llm_provider",
            "provider_key": "openai",
            "provider_variant": None,
            "display_name": "OpenAI Secondary",
            "credentials": {"api_key": "key-2"},
            "is_enabled": True,
            "is_default": True,
        }

        created_one = await client.post("/admin/settings/credentials", json=payload_one)
        created_two = await client.post("/admin/settings/credentials", json=payload_two)

        assert created_one.status_code == 201
        assert created_two.status_code == 201

        listed = await client.get("/admin/settings/credentials", params={"category": "llm_provider"})
        assert listed.status_code == 200
        rows = [row for row in listed.json()["items"] if row["provider_key"] == "openai"]
        assert len(rows) == 2

        defaults = [row for row in rows if row["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["display_name"] == "OpenAI Secondary"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_provider_key_validation_enforced_for_tool_provider_but_not_custom(client, db_session):
    tenant = Organization(name="Validation Organization", slug=f"validation-{uuid4().hex[:8]}")
    user = User(email=f"validator-{uuid4().hex[:8]}@example.com", hashed_password="test", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()

    from main import app

    async def override_get_current_user():
        return user

    async def override_get_tenant_context():
        return {"organization_id": str(tenant.id), "tenant": tenant}

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_tenant_context] = override_get_tenant_context

    try:
        invalid_tool_payload = {
            "category": "tool_provider",
            "provider_key": "unknown_tool",
            "display_name": "Unknown Tool",
            "credentials": {"api_key": "x"},
            "is_enabled": True,
            "is_default": True,
        }
        invalid_resp = await client.post("/admin/settings/credentials", json=invalid_tool_payload)
        assert invalid_resp.status_code == 422

        custom_payload = {
            "category": "custom",
            "provider_key": "google_oauth",
            "display_name": "Google OAuth",
            "credentials": {"client_id": "abc"},
            "is_enabled": True,
            "is_default": True,
        }
        custom_resp = await client.post("/admin/settings/credentials", json=custom_payload)
        assert custom_resp.status_code == 201
        assert custom_resp.json()["provider_key"] == "google_oauth"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_backend_config_falls_back_to_env_when_no_tenant_default(db_session, monkeypatch):
    organization_id = uuid4()
    monkeypatch.setenv("PINECONE_API_KEY", "pinecone-env-key")

    merged = await CredentialsService(db_session, organization_id).resolve_backend_config(
        {"index_name": "idx"},
        None,
        category=IntegrationCredentialCategory.VECTOR_STORE,
        provider_key="pinecone",
    )

    assert merged["index_name"] == "idx"
    assert merged["api_key"] == "pinecone-env-key"


@pytest.mark.asyncio
async def test_delete_credential_with_usage_requires_force_then_disconnects(client, db_session):
    tenant = Organization(name="Disconnect Organization", slug=f"disconnect-{uuid4().hex[:8]}")
    user = User(email=f"disconnect-{uuid4().hex[:8]}@example.com", hashed_password="test", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    credential = IntegrationCredential(
        organization_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        provider_variant=None,
        display_name="OpenAI Linked",
        credentials={"api_key": "key-linked"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.flush()

    model = ModelRegistry(
        organization_id=tenant.id,
        name="Linked Model",
        capability_type=ModelCapabilityType.CHAT,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        organization_id=tenant.id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o-mini",
        credentials_ref=credential.id,
        config={},
        priority=0,
        is_enabled=True,
    )
    db_session.add(binding)

    store = KnowledgeStore(
        organization_id=tenant.id,
        name="Linked Store",
        embedding_model_id="text-embedding-3-small",
        backend=StorageBackend.PINECONE,
        backend_config={"index_name": "idx"},
        credentials_ref=credential.id,
    )
    db_session.add(store)

    tool = ToolRegistry(
        organization_id=tenant.id,
        name="Linked Tool",
        slug=f"linked-tool-{uuid4().hex[:8]}",
        scope=ToolDefinitionScope.TENANT,
        schema={"type": "object"},
        config_schema={"implementation": {"type": "builtin", "builtin": "web_search", "credentials_ref": str(credential.id)}},
    )
    db_session.add(tool)
    await db_session.commit()

    from main import app

    async def override_get_current_user():
        return user

    async def override_get_tenant_context():
        return {"organization_id": str(tenant.id), "tenant": tenant}

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_tenant_context] = override_get_tenant_context

    try:
        usage_resp = await client.get(f"/admin/settings/credentials/{credential.id}/usage")
        assert usage_resp.status_code == 200
        usage = usage_resp.json()
        assert len(usage["model_providers"]) == 1
        assert len(usage["knowledge_stores"]) == 1
        assert len(usage["tools"]) == 1

        blocked_delete = await client.delete(f"/admin/settings/credentials/{credential.id}")
        assert blocked_delete.status_code == 409

        forced_delete = await client.delete(f"/admin/settings/credentials/{credential.id}?force_disconnect=true")
        assert forced_delete.status_code == 200

        await db_session.refresh(binding)
        await db_session.refresh(store)
        await db_session.refresh(tool)

        assert binding.credentials_ref is None
        assert store.credentials_ref is None
        impl = ((tool.config_schema or {}).get("implementation") or {})
        assert "credentials_ref" not in impl

        credential_after = await db_session.get(IntegrationCredential, credential.id)
        assert credential_after is None
    finally:
        app.dependency_overrides.clear()
