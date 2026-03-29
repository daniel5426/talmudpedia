from uuid import uuid4

import pytest

from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)

from ._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_builder_agent_contract_returns_resolved_tools_and_optional_x_ui_hints(
    client,
    db_session,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="Stats Tool",
        slug=f"stats-tool-{uuid4().hex[:8]}",
        description="Returns stats payloads",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {
                "type": "object",
                "properties": {"metric": {"type": "string"}},
                "required": ["metric"],
            },
            "output": {
                "type": "object",
                "properties": {"value": {"type": "number"}},
                "required": ["value"],
                "x-ui": {
                    "kind": "chart",
                    "title": "Metric Trend",
                },
            },
        },
        config_schema={},
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.CUSTOM,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.flush()

    agent.tools = [str(tool.id)]
    agent.referenced_tool_ids = [str(tool.id)]
    agent.graph_definition = {
        "nodes": [
            {
                "id": "agent",
                "type": "agent",
                "position": {"x": 0, "y": 0},
                "config": {
                    "tools": [str(tool.id), "not-a-uuid-tool-ref"],
                },
            }
        ],
        "edges": [],
    }
    await db_session.commit()

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Contract App",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    contract_resp = await client.get(
        f"/admin/apps/{app_id}/builder/agent-contract",
        headers=headers,
    )
    assert contract_resp.status_code == 200
    payload = contract_resp.json()

    assert payload["app_id"] == app_id
    assert payload["agent_id"] == str(agent.id)
    assert payload["agent"]["id"] == str(agent.id)
    assert payload["resolved_tool_count"] == 1
    assert payload["ui_hint_standard"]["optional"] is True
    assert payload["ui_hint_standard"]["schema_key"] == "x-ui"

    resolved_tool = payload["tools"][0]
    assert resolved_tool["id"] == str(tool.id)
    assert resolved_tool["slug"] == tool.slug
    assert resolved_tool["input_schema"]["properties"]["metric"]["type"] == "string"
    assert resolved_tool["output_schema"]["properties"]["value"]["type"] == "number"
    assert resolved_tool["ui_hints"]["kind"] == "chart"
    assert resolved_tool["ui_hints"]["output"]["title"] == "Metric Trend"

    unresolved = payload["unresolved_tool_references"]
    assert any(
        item["reference"] == "not-a-uuid-tool-ref"
        and item["reason"] == "invalid_tool_reference"
        for item in unresolved
    )


@pytest.mark.asyncio
async def test_builder_agent_contract_includes_ui_blocks_frontend_requirements(
    client,
    db_session,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="UI Blocks",
        slug="builtin-ui-blocks",
        description="Validate UI blocks payloads",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {"type": "object", "properties": {"rows": {"type": "array"}}, "required": ["rows"]},
            "output": {"type": "object", "properties": {"kind": {"type": "string", "const": "ui_blocks_bundle"}}, "required": ["kind"]},
        },
        config_schema={
            "implementation": {"type": "builtin", "builtin": "ui_blocks"},
            "execution": {"strict_input_schema": True},
        },
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.CUSTOM,
        is_active=True,
        is_system=False,
        builtin_key="ui_blocks",
    )
    db_session.add(tool)
    await db_session.flush()

    agent.tools = [str(tool.id)]
    agent.referenced_tool_ids = [str(tool.id)]
    await db_session.commit()

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "UI Blocks Contract App",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    contract_resp = await client.get(
        f"/admin/apps/{app_id}/builder/agent-contract",
        headers=headers,
    )
    assert contract_resp.status_code == 200

    tool_payload = contract_resp.json()["tools"][0]
    assert tool_payload["frontend_requirements"]["required"] is True
    assert tool_payload["frontend_requirements"]["renderer_kind"] == "ui_blocks"
    assert tool_payload["frontend_requirements"]["package_name"] == "@agents24/ui-blocks-react"
    assert tool_payload["frontend_requirements"]["install_command"] == "npx @agents24/ui-blocks-react init"
