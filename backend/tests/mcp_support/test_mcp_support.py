from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from app.db.postgres.base import Base

from app.api.dependencies import get_current_principal
from app.core.runtime_urls import resolve_local_backend_origin
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.mcp import (
    McpAgentMount,
    McpApprovalPolicy,
    McpAuthMode,
    McpDiscoveredTool,
    McpOauthState,
    McpServer,
    McpUserAccountConnection,
)
from app.services.mcp_service import (
    McpApprovalRequiredRuntimeError,
    McpAuthRequiredRuntimeError,
    McpRuntimeService,
    McpService,
)


@pytest_asyncio.fixture(autouse=True)
async def ensure_mcp_tables(db_session):
    connection = await db_session.connection()
    await connection.run_sync(
        lambda sync_conn: Base.metadata.create_all(
            bind=sync_conn,
            tables=[
                McpServer.__table__,
                McpDiscoveredTool.__table__,
                McpAgentMount.__table__,
                McpUserAccountConnection.__table__,
                McpOauthState.__table__,
            ],
        )
    )
    yield


@pytest_asyncio.fixture
async def mcp_fixture(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"user-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    org = OrgUnit(tenant_id=tenant.id, name="Root", slug=f"root-{suffix}", type=OrgUnitType.org)
    db_session.add(org)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            org_unit_id=org.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    agent = Agent(
        tenant_id=tenant.id,
        created_by=user.id,
        name=f"Agent {suffix}",
        slug=f"agent-{suffix}",
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add(agent)
    await db_session.flush()
    return {"tenant": tenant, "user": user, "agent": agent}


@pytest.fixture
def principal_override():
    from main import app

    def _install(*, tenant_id, user, scopes: list[str]):
        async def _principal():
            return {
                "type": "user",
                "tenant_id": str(tenant_id),
                "user_id": str(user.id),
                "user": user,
                "scopes": scopes,
            }

        app.dependency_overrides[get_current_principal] = _principal

    yield _install
    app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_mcp_runtime_lists_virtual_tools_for_applied_snapshot(db_session, mcp_fixture):
    tenant = mcp_fixture["tenant"]
    agent = mcp_fixture["agent"]

    server = McpServer(
        tenant_id=tenant.id,
        name="Notion",
        server_url="https://mcp.notion.com/mcp",
        auth_mode=McpAuthMode.NONE.value,
        tool_snapshot_version=2,
    )
    db_session.add(server)
    await db_session.flush()

    db_session.add_all(
        [
            McpDiscoveredTool(
                tenant_id=tenant.id,
                server_id=server.id,
                snapshot_version=2,
                name="search_pages",
                title="Search Pages",
                description="Search the connected workspace",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            ),
            McpAgentMount(
                tenant_id=tenant.id,
                agent_id=agent.id,
                server_id=server.id,
                applied_snapshot_version=2,
                approval_policy=McpApprovalPolicy.ALWAYS_ALLOW.value,
            ),
        ]
    )
    await db_session.flush()

    runtime = McpRuntimeService(db_session, tenant.id)
    tools = await runtime.list_agent_tools(agent_id=agent.id, user_id=mcp_fixture["user"].id)

    assert len(tools) == 1
    assert tools[0].id.startswith("mcp:")
    assert tools[0].slug == "mcp_notion_search_pages"
    assert tools[0].schema["input"]["properties"]["query"]["type"] == "string"


@pytest.mark.asyncio
async def test_mcp_runtime_requires_user_account_for_oauth_mount(db_session, mcp_fixture):
    tenant = mcp_fixture["tenant"]
    agent = mcp_fixture["agent"]

    server = McpServer(
        tenant_id=tenant.id,
        name="Slack",
        server_url="https://mcp.slack.com/mcp",
        auth_mode=McpAuthMode.OAUTH_USER_ACCOUNT.value,
        tool_snapshot_version=1,
        auth_metadata={
            "authorization_server_metadata": {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
            }
        },
    )
    db_session.add(server)
    await db_session.flush()

    tool = McpDiscoveredTool(
        tenant_id=tenant.id,
        server_id=server.id,
        snapshot_version=1,
        name="post_message",
        input_schema={"type": "object"},
    )
    mount = McpAgentMount(
        tenant_id=tenant.id,
        agent_id=agent.id,
        server_id=server.id,
        applied_snapshot_version=1,
        approval_policy=McpApprovalPolicy.ALWAYS_ALLOW.value,
    )
    db_session.add_all([tool, mount])
    await db_session.flush()

    runtime = McpRuntimeService(db_session, tenant.id)
    with pytest.raises(McpAuthRequiredRuntimeError):
        await runtime.execute_virtual_tool(
            tool_id=f"mcp:{mount.id}:post_message",
            arguments={"text": "hello"},
            user_id=None,
        )


@pytest.mark.asyncio
async def test_mcp_runtime_requires_approval_when_mount_policy_is_ask(db_session, mcp_fixture):
    tenant = mcp_fixture["tenant"]
    agent = mcp_fixture["agent"]

    server = McpServer(
        tenant_id=tenant.id,
        name="Notion",
        server_url="https://mcp.notion.com/mcp",
        auth_mode=McpAuthMode.NONE.value,
        tool_snapshot_version=1,
    )
    db_session.add(server)
    await db_session.flush()

    tool = McpDiscoveredTool(
        tenant_id=tenant.id,
        server_id=server.id,
        snapshot_version=1,
        name="create_page",
        input_schema={"type": "object"},
    )
    mount = McpAgentMount(
        tenant_id=tenant.id,
        agent_id=agent.id,
        server_id=server.id,
        applied_snapshot_version=1,
        approval_policy=McpApprovalPolicy.ASK.value,
    )
    db_session.add_all([tool, mount])
    await db_session.flush()

    runtime = McpRuntimeService(db_session, tenant.id)
    with pytest.raises(McpApprovalRequiredRuntimeError):
        await runtime.execute_virtual_tool(
            tool_id=f"mcp:{mount.id}:create_page",
            arguments={"title": "Draft"},
            user_id=mcp_fixture["user"].id,
        )


@pytest.mark.asyncio
async def test_mcp_oauth_start_creates_state_and_uses_client_metadata_document(db_session, mcp_fixture, monkeypatch):
    tenant = mcp_fixture["tenant"]
    user = mcp_fixture["user"]

    server = McpServer(
        tenant_id=tenant.id,
        name="Slack",
        server_url="https://mcp.slack.com/mcp",
        auth_mode=McpAuthMode.OAUTH_USER_ACCOUNT.value,
        auth_config={"scopes": ["mcp:tools"]},
    )
    db_session.add(server)
    await db_session.flush()

    async def _fake_metadata(self, _server):
        return {
            "protected_resource_metadata": {"scopes_supported": ["mcp:tools"]},
            "authorization_server_metadata": {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "client_id_metadata_document_supported": True,
            },
        }

    monkeypatch.setattr(McpService, "ensure_oauth_metadata", _fake_metadata)

    service = McpService(db_session, tenant.id)
    payload = await service.start_oauth(server.id, user_id=user.id)

    parsed = urlparse(payload["authorization_url"])
    query = parse_qs(parsed.query)
    states = (await db_session.execute(select(McpOauthState).where(McpOauthState.server_id == server.id))).scalars().all()

    assert parsed.netloc == "auth.example.com"
    assert query["redirect_uri"] == [f"{resolve_local_backend_origin().rstrip('/')}/mcp/auth/callback"]
    assert query["client_id"] == [f"{resolve_local_backend_origin().rstrip('/')}/mcp/oauth/client-metadata/{server.id}"]
    assert len(states) == 1
    assert states[0].user_id == user.id


@pytest.mark.asyncio
async def test_mcp_routes_create_server_and_list_mounts(client, db_session, mcp_fixture, principal_override):
    tenant = mcp_fixture["tenant"]
    user = mcp_fixture["user"]
    agent = mcp_fixture["agent"]
    principal_override(
        tenant_id=tenant.id,
        user=user,
        scopes=["tools.read", "tools.write", "agents.read", "agents.write"],
    )

    create_response = await client.post(
        "/mcp/servers",
        json={
            "name": "Docs",
            "server_url": "https://mcp.notion.com/mcp",
            "auth_mode": "none",
        },
    )
    assert create_response.status_code == 200, create_response.text
    server_id = create_response.json()["id"]

    server = await db_session.get(McpServer, server_id)
    server.tool_snapshot_version = 1
    db_session.add(
        McpDiscoveredTool(
            tenant_id=tenant.id,
            server_id=server.id,
            snapshot_version=1,
            name="search_docs",
            input_schema={"type": "object"},
        )
    )
    await db_session.commit()

    mount_response = await client.post(
        f"/agents/{agent.id}/mcp-mounts",
        json={"server_id": str(server.id), "approval_policy": "always_allow"},
    )
    assert mount_response.status_code == 200, mount_response.text
    assert mount_response.json()["applied_snapshot_version"] == 1

    list_response = await client.get(f"/agents/{agent.id}/mcp-mounts")
    assert list_response.status_code == 200, list_response.text
    assert len(list_response.json()) == 1
