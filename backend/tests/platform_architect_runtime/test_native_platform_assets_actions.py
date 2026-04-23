from __future__ import annotations

from datetime import datetime, UTC
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import platform_native_tools


class _FakeSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_native_platform_assets_tools_list_uses_context_and_paging(monkeypatch):
    captured = {}

    async def fake_list_tools(self, *, ctx, scope, name, is_active, status, implementation_type, tool_type, skip, limit):
        captured.update(
            {
                "organization_id": str(ctx.organization_id),
                "scope": scope,
                "name": name,
                "is_active": is_active,
                "status": status,
                "implementation_type": implementation_type,
                "tool_type": tool_type,
                "skip": skip,
                "limit": limit,
            }
        )
        return ([SimpleNamespace(id=uuid4(), name="Tool A")], 1)

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.ToolRegistryAdminService.list_tools", fake_list_tools)
    monkeypatch.setattr("app.services.platform_native.assets.serialize_tool", lambda tool, view="full": {"name": tool.name, "view": view})

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "tools.list",
            "payload": {"limit": 7, "skip": 3, "view": "summary", "name": "Tool A", "is_active": False, "status": "draft"},
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"]["items"] == [{"name": "Tool A", "view": "summary"}]
    assert result["result"]["total"] == 1
    assert result["result"]["has_more"] is False
    assert result["result"]["skip"] == 3
    assert result["result"]["limit"] == 7
    assert result["result"]["view"] == "summary"
    assert captured["name"] == "Tool A"
    assert captured["is_active"] is False
    assert captured["status"] == "draft"
    assert captured["skip"] == 3
    assert captured["limit"] == 7


@pytest.mark.asyncio
async def test_native_platform_assets_tools_get_requires_tool_id(monkeypatch):
    captured = {}
    tool_id = uuid4()

    async def fake_get_tool(self, *, ctx, tool_id):
        captured["organization_id"] = str(ctx.organization_id)
        captured["tool_id"] = str(tool_id) if tool_id else None
        return SimpleNamespace(id=tool_id or uuid4(), name="Tool B")

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.ToolRegistryAdminService.get_tool", fake_get_tool)
    monkeypatch.setattr(
        "app.services.platform_native.assets.serialize_tool",
        lambda tool, view="full": {"id": str(tool.id), "name": tool.name},
    )

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "tools.get",
            "payload": {"tool_id": str(tool_id)},
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"]["id"] == str(tool_id)
    assert captured["tool_id"] == str(tool_id)


@pytest.mark.asyncio
async def test_native_platform_assets_tools_create_builds_request(monkeypatch):
    captured = {}

    async def fake_create_tool(self, *, ctx, request):
        captured["organization_id"] = str(ctx.organization_id)
        captured["request"] = request
        return SimpleNamespace(id=uuid4(), name=request.name)

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.ToolRegistryAdminService.create_tool", fake_create_tool)
    monkeypatch.setattr(
        "app.services.platform_native.assets.serialize_tool",
        lambda tool: {"id": str(tool.id), "name": tool.name},
    )

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "tools.create",
            "payload": {
                "name": "Native Tool",
                "description": "desc",
                "scope": "tenant",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "implementation_type": "function",
                "execution_config": {"validation_mode": "strict"},
            },
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    request = captured["request"]
    assert result["errors"] == []
    assert result["result"]["name"] == "Native Tool"
    assert captured["organization_id"]
    assert request.name == "Native Tool"
    assert request.description == "desc"
    assert getattr(request.scope, "value", request.scope) == "tenant"
    assert request.input_schema == {"type": "object"}
    assert request.output_schema == {"type": "object"}
    assert request.implementation_type == "function"
    assert request.execution_config == {"validation_mode": "strict"}


@pytest.mark.asyncio
async def test_native_platform_assets_tools_update_builds_request(monkeypatch):
    captured = {}
    tool_id = uuid4()

    async def fake_update_tool(self, *, ctx, tool_id, request):
        captured["organization_id"] = str(ctx.organization_id)
        captured["tool_id"] = str(tool_id)
        captured["request"] = request
        return SimpleNamespace(id=tool_id, name=request.name or "Existing Tool")

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.ToolRegistryAdminService.update_tool", fake_update_tool)
    monkeypatch.setattr(
        "app.services.platform_native.assets.serialize_tool",
        lambda tool: {"id": str(tool.id), "name": tool.name},
    )

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "tools.update",
            "payload": {
                "tool_id": str(tool_id),
                "description": "desc",
                "execution_config": {"validation_mode": "strict"},
            },
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    request = captured["request"]
    assert result["errors"] == []
    assert captured["tool_id"] == str(tool_id)
    assert request.description == "desc"
    assert request.execution_config == {"validation_mode": "strict"}


@pytest.mark.asyncio
async def test_native_platform_assets_tools_update_requires_update_fields(monkeypatch):
    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "tools.update",
            "payload": {"tool_id": str(uuid4())},
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"][0]["code"] == "VALIDATION_ERROR"
    assert result["errors"][0]["message"] == "At least one update field is required."


@pytest.mark.asyncio
async def test_native_platform_assets_credentials_list_paginates(monkeypatch):
    organization_id = uuid4()
    items = [
        SimpleNamespace(
            id=uuid4(),
            category="llm_provider",
            provider_key="openai",
            provider_variant=None,
            display_name="Cred A",
            is_enabled=True,
            is_default=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        SimpleNamespace(
            id=uuid4(),
            category="vector_store",
            provider_key="pinecone",
            provider_variant=None,
            display_name="Cred B",
            is_enabled=True,
            is_default=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]

    async def fake_list_credentials(self, *, ctx, category):
        assert str(ctx.organization_id) == str(organization_id)
        assert category is None
        return items

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.CredentialsAdminService.list_credentials", fake_list_credentials)

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "credentials.list",
            "payload": {"limit": 1, "skip": 1, "view": "summary"},
            "__tool_runtime_context__": {"organization_id": str(organization_id), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert [item["display_name"] for item in result["result"]["items"]] == ["Cred B"]
    assert result["result"]["total"] == 2
    assert result["result"]["has_more"] is False
    assert result["result"]["skip"] == 1
    assert result["result"]["limit"] == 1
    assert result["result"]["view"] == "summary"


@pytest.mark.asyncio
async def test_native_platform_assets_prompts_list_uses_prompt_library_service(monkeypatch):
    organization_id = uuid4()
    actor_user_id = uuid4()
    items = [
        SimpleNamespace(
            id=uuid4(),
            name="Prompt A",
            description="desc",
            scope="organization",
            status="active",
            managed_by="prompts",
            allowed_surfaces=["chat"],
            tags=["ops"],
            version=3,
            content="hidden in summary",
            updated_at=datetime.now(UTC),
        )
    ]
    captured = {}

    async def fake_list_prompts(self, *, q, status, limit, offset):
        captured.update(
            {
                "organization_id": str(self._organization_id),
                "actor_user_id": str(self._actor_user_id),
                "is_service": self._is_service,
                "q": q,
                "status": status,
                "limit": limit,
                "offset": offset,
            }
        )
        return items, 1

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.PromptLibraryService.list_prompts", fake_list_prompts)

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "prompts.list",
            "payload": {"q": "Prompt", "status": "active", "limit": 5, "skip": 2, "view": "summary"},
            "__tool_runtime_context__": {"organization_id": str(organization_id), "user_id": str(actor_user_id), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"]["items"] == [
        {
            "id": str(items[0].id),
            "name": "Prompt A",
            "description": "desc",
            "scope": "organization",
            "status": "active",
            "managed_by": "prompts",
            "allowed_surfaces": ["chat"],
            "tags": ["ops"],
            "version": 3,
            "updated_at": items[0].updated_at.isoformat(),
        }
    ]
    assert result["result"]["total"] == 1
    assert result["result"]["has_more"] is False
    assert result["result"]["skip"] == 2
    assert result["result"]["limit"] == 5
    assert result["result"]["view"] == "summary"
    assert captured["organization_id"] == str(organization_id)
    assert captured["actor_user_id"] == str(actor_user_id)
    assert captured["is_service"] is False
    assert captured["q"] == "Prompt"
    assert captured["status"] == "active"
    assert captured["limit"] == 5
    assert captured["offset"] == 2


@pytest.mark.asyncio
async def test_native_platform_assets_credentials_update_uses_patch(monkeypatch):
    captured = {}
    credential_id = uuid4()

    async def fake_update_credential(self, *, ctx, credential_id, patch):
        captured["organization_id"] = str(ctx.organization_id)
        captured["credential_id"] = str(credential_id)
        captured["patch"] = patch
        return SimpleNamespace(id=credential_id, display_name=patch["display_name"])

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.CredentialsAdminService.update_credential", fake_update_credential)

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "credentials.create_or_update",
            "payload": {"credential_id": str(credential_id), "patch": {"display_name": "Updated Cred", "is_enabled": False}},
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"] == {"id": str(credential_id), "display_name": "Updated Cred"}
    assert captured["credential_id"] == str(credential_id)
    assert captured["patch"] == {"display_name": "Updated Cred", "is_enabled": False}


@pytest.mark.asyncio
async def test_native_platform_assets_knowledge_stores_list_paginates(monkeypatch):
    organization_id = uuid4()
    stores = [
        SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            name="Store A",
            description="A",
            embedding_model_id="embed-a",
            chunking_strategy={"strategy": "recursive"},
            retrieval_policy="semantic_only",
            backend="pinecone",
            backend_config={"index_name": "a"},
            credentials_ref=None,
            status="active",
            document_count=4,
            chunk_count=9,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            name="Store B",
            description="B",
            embedding_model_id="embed-b",
            chunking_strategy={"strategy": "recursive"},
            retrieval_policy="semantic_only",
            backend="qdrant",
            backend_config={"collection": "b"},
            credentials_ref=None,
            status="active",
            document_count=2,
            chunk_count=5,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]

    async def fake_list_stores(self, *, ctx, organization_id=None):
        assert str(ctx.organization_id) == str(organization_id_ctx)
        assert organization_id is None
        return stores

    organization_id_ctx = organization_id

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.KnowledgeStoreAdminService.list_stores", fake_list_stores)

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "knowledge_stores.list",
            "payload": {"limit": 1, "skip": 0, "view": "summary"},
            "__tool_runtime_context__": {"organization_id": str(organization_id), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert [item["name"] for item in result["result"]["items"]] == ["Store A"]
    assert result["result"]["items"][0]["document_count"] == 4
    assert result["result"]["total"] == 2
    assert result["result"]["has_more"] is True
    assert result["result"]["skip"] == 0
    assert result["result"]["limit"] == 1
    assert result["result"]["view"] == "summary"


@pytest.mark.asyncio
async def test_native_platform_assets_knowledge_store_create_passes_expected_fields(monkeypatch):
    captured = {}
    organization_id = uuid4()
    store_id = uuid4()

    async def fake_create_store(
        self,
        *,
        ctx,
        organization_id,
        name,
        description,
        embedding_model_id,
        chunking_strategy,
        retrieval_policy,
        backend,
        backend_config,
        credentials_ref,
    ):
        captured.update(
            {
                "ctx_organization_id": str(ctx.organization_id),
                "organization_id": organization_id,
                "name": name,
                "description": description,
                "embedding_model_id": embedding_model_id,
                "chunking_strategy": chunking_strategy,
                "retrieval_policy": retrieval_policy,
                "backend": backend,
                "backend_config": backend_config,
                "credentials_ref": credentials_ref,
            }
        )
        return SimpleNamespace(id=store_id, name=name)

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.KnowledgeStoreAdminService.create_store", fake_create_store)

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "knowledge_stores.create",
            "payload": {
                "name": "Customer Docs",
                "description": "primary store",
                "embedding_model_id": "embed-1",
                "chunking_strategy": {"strategy": "recursive"},
                "retrieval_policy": "semantic_only",
                "backend": "pinecone",
                "backend_config": {"index_name": "customer-docs"},
                "credentials_ref": str(uuid4()),
            },
            "__tool_runtime_context__": {"organization_id": str(organization_id), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"] == {"id": str(store_id), "name": "Customer Docs"}
    assert captured["ctx_organization_id"] == str(organization_id)
    assert captured["organization_id"] is None
    assert captured["embedding_model_id"] == "embed-1"
    assert captured["backend_config"] == {"index_name": "customer-docs"}


@pytest.mark.asyncio
async def test_native_platform_assets_knowledge_store_update_passes_expected_fields(monkeypatch):
    captured = {}
    organization_id = uuid4()
    store_id = uuid4()

    async def fake_update_store(self, *, ctx, store_id, organization_id, patch):
        captured["ctx_organization_id"] = str(ctx.organization_id)
        captured["store_id"] = str(store_id)
        captured["organization_id"] = organization_id
        captured["patch"] = patch
        return SimpleNamespace(id=store_id, name="Customer Docs")

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.assets.KnowledgeStoreAdminService.update_store", fake_update_store)

    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "knowledge_stores.update",
            "payload": {"store_id": str(store_id), "description": "updated"},
            "__tool_runtime_context__": {"organization_id": str(organization_id), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"] == {"id": str(store_id), "name": "Customer Docs"}
    assert captured["ctx_organization_id"] == str(organization_id)
    assert captured["organization_id"] is None
    assert captured["patch"] == {"description": "updated"}


@pytest.mark.asyncio
async def test_native_platform_assets_knowledge_store_update_requires_update_fields():
    result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "knowledge_stores.update",
            "payload": {"store_id": str(uuid4())},
            "__tool_runtime_context__": {"organization_id": str(uuid4()), "user_id": str(uuid4()), "scopes": ["*"]},
        }
    )

    assert result["errors"][0]["code"] == "VALIDATION_ERROR"
    assert result["errors"][0]["message"] == "At least one update field is required."
