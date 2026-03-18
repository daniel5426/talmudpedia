from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_principal
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.registry import ToolRegistry, ToolStatus, ToolVersion
from app.services.agent_service import AgentService
from app.services.tool_binding_service import ToolBindingService
from main import app


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Agent Binding Tenant", slug=f"agent-binding-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"agent-binding-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Agent Binding Org",
        slug=f"agent-binding-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _override_principal(tenant_id, user, scopes: list[str]):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "scopes": scopes,
        }

    return _inner


async def _seed_agent(db_session, *, tenant_id, user_id, status: AgentStatus = AgentStatus.draft) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Delegated Helper",
        slug=f"delegated-helper-{uuid.uuid4().hex[:8]}",
        description="Agent export target",
        graph_definition={
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                {"id": "end", "type": "end", "position": {"x": 240, "y": 0}},
            ],
            "edges": [
                {"id": "edge-1", "source": "start", "target": "end", "type": "control"},
            ],
        },
        status=status,
        version=1,
        created_by=user_id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _get_agent_tool(db_session, agent_id) -> ToolRegistry | None:
    slug = f"agent-tool-{str(agent_id).replace('-', '')[:12]}"
    return (await db_session.execute(select(ToolRegistry).where(ToolRegistry.slug == slug))).scalar_one_or_none()


@pytest.mark.asyncio
async def test_export_agent_tool_creates_agent_bound_registry_row(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    agent = await _seed_agent(db_session, tenant_id=tenant.id, user_id=user.id)
    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        user,
        ["agents.read", "agents.write", "tools.read"],
    )

    try:
        response = await client.post(
            f"/agents/{agent.id}/export-tool",
            json={
                "name": "Delegated Helper Tool",
                "description": "Agent-owned export",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        )
        assert response.status_code == 200, response.text

        tool = await _get_agent_tool(db_session, agent.id)
        assert tool is not None
        assert tool.name == "Delegated Helper Tool"
        assert str(getattr(getattr(tool, "implementation_type", None), "value", tool.implementation_type)) == "AGENT_CALL"
        assert tool.config_schema["agent_binding"]["agent_id"] == str(agent.id)
        assert tool.config_schema["implementation"]["target_agent_id"] == str(agent.id)
        assert tool.status == ToolStatus.DRAFT

        tool_response = await client.get(f"/tools/{tool.id}")
        assert tool_response.status_code == 200, tool_response.text
        body = tool_response.json()
        assert body["ownership"] == "agent_bound"
        assert body["managed_by"] == "agents"
        assert body["source_object_type"] == "agent"
        assert body["source_object_id"] == str(agent.id)
        assert body["can_edit_in_registry"] is False
        assert body["can_publish_in_registry"] is False
        assert body["can_delete_in_registry"] is False
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_publishing_agent_syncs_existing_exported_tool(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    agent = await _seed_agent(db_session, tenant_id=tenant.id, user_id=user.id)
    service = AgentService(db_session, tenant.id)

    exported = await ToolBindingService(db_session).export_agent_tool_binding(
        agent=agent,
        name="Delegated Helper Tool",
        created_by=user.id,
    )
    await db_session.commit()

    published = await service.publish_agent(agent.id, user_id=user.id)
    synced_tool = await _get_agent_tool(db_session, agent.id)
    assert synced_tool is not None
    assert published.status == AgentStatus.published
    assert synced_tool.status == ToolStatus.PUBLISHED
    assert synced_tool.config_schema["implementation"]["target_agent_id"] == str(agent.id)

    versions = (
        await db_session.execute(select(ToolVersion).where(ToolVersion.tool_id == exported.id))
    ).scalars().all()
    assert versions


@pytest.mark.asyncio
async def test_deleting_agent_deletes_exported_tool_binding(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    agent = await _seed_agent(db_session, tenant_id=tenant.id, user_id=user.id)
    tool = await ToolBindingService(db_session).export_agent_tool_binding(agent=agent, created_by=user.id)
    await db_session.commit()

    assert tool.id is not None
    assert await _get_agent_tool(db_session, agent.id) is not None

    await AgentService(db_session, tenant.id).delete_agent(agent.id)

    assert await _get_agent_tool(db_session, agent.id) is None
