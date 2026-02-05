import pytest
import pytest_asyncio

from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ToolRegistry, ToolDefinitionScope, ToolStatus, ToolImplementationType
from app.api.routers.auth import get_current_user
from main import app

@pytest_asyncio.fixture
async def setup_tools_env(db_session):
    tenant = Tenant(name="Tool Type Tenant", slug="tool-type-tenant")
    db_session.add(tenant)
    await db_session.flush()

    user = User(email="tool-type@example.com", full_name="Tool Type Tester", role="admin")
    db_session.add(user)
    await db_session.flush()

    await db_session.commit()
    return tenant, user

@pytest_asyncio.fixture
async def authorized_client(client, setup_tools_env):
    _, user = setup_tools_env

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_tool_type_derivation(authorized_client, db_session, setup_tools_env):
    tenant, _ = setup_tools_env

    tool_artifact = ToolRegistry(
        tenant_id=tenant.id,
        name="Artifact Tool",
        slug="artifact-tool",
        description="Artifact",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {}, "output": {}},
        config_schema={"implementation": {"type": "artifact"}},
        artifact_id="custom/tool_alpha",
        artifact_version="1.0.0",
        implementation_type=ToolImplementationType.ARTIFACT,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        is_active=True,
        is_system=False,
    )

    tool_builtin = ToolRegistry(
        tenant_id=None,
        name="Built-in Tool",
        slug="builtin-tool",
        description="Built in",
        scope=ToolDefinitionScope.GLOBAL,
        schema={"input": {}, "output": {}},
        config_schema={"implementation": {"type": "internal"}},
        implementation_type=ToolImplementationType.INTERNAL,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        is_active=True,
        is_system=True,
    )

    tool_mcp = ToolRegistry(
        tenant_id=tenant.id,
        name="MCP Tool",
        slug="mcp-tool",
        description="MCP",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {}, "output": {}},
        config_schema={"implementation": {"type": "mcp"}},
        implementation_type=ToolImplementationType.MCP,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        is_active=True,
        is_system=False,
    )

    tool_custom = ToolRegistry(
        tenant_id=tenant.id,
        name="Custom Tool",
        slug="custom-tool",
        description="Custom",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {}, "output": {}},
        config_schema={"implementation": {"type": "http"}},
        implementation_type=ToolImplementationType.HTTP,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        is_active=True,
        is_system=False,
    )

    db_session.add_all([tool_artifact, tool_builtin, tool_mcp, tool_custom])
    await db_session.commit()

    response = await authorized_client.get("/tools")
    assert response.status_code == 200
    tools = {t["slug"]: t for t in response.json()["tools"]}

    assert tools["artifact-tool"]["tool_type"] == "artifact"
    assert tools["builtin-tool"]["tool_type"] == "built_in"
    assert tools["mcp-tool"]["tool_type"] == "mcp"
    assert tools["custom-tool"]["tool_type"] == "custom"

    response = await authorized_client.get("/tools?tool_type=artifact")
    assert response.status_code == 200
    filtered = response.json()["tools"]
    assert all(t["tool_type"] == "artifact" for t in filtered)
