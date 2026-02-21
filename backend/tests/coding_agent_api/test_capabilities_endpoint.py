from uuid import uuid4

import pytest

from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app(client, headers: dict[str, str], agent_id: str) -> str:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": f"Coding Capabilities App {uuid4().hex[:6]}",
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    return str(create_resp.json()["id"])


@pytest.mark.asyncio
async def test_coding_agent_capabilities_endpoint_returns_policy_and_native_tools(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_DEFAULT_ENGINE", "native")
    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "1")

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, str(agent.id))

    response = await client.get(f"/admin/apps/{app_id}/coding-agent/capabilities", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["app_id"] == app_id
    assert payload["default_engine"] == "native"
    assert payload["native_enabled"] is True
    assert payload["native_tool_count"] > 0
    assert any(item["slug"] == "apply_patch" for item in payload["native_tools"])
    assert payload["opencode_policy"]["tooling_mode"] == "delegated_to_upstream_opencode"
    assert payload["opencode_policy"]["repo_tool_allowlist_configured"] is True
    assert payload["opencode_policy"]["workspace_permission_model"] == "project_local_custom_tools_and_context_file"


@pytest.mark.asyncio
async def test_coding_agent_capabilities_endpoint_reflects_native_disabled_policy(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_DEFAULT_ENGINE", "opencode")
    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "0")

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, str(agent.id))

    response = await client.get(f"/admin/apps/{app_id}/coding-agent/capabilities", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["default_engine"] == "opencode"
    assert payload["native_enabled"] is False


@pytest.mark.asyncio
async def test_coding_agent_capabilities_endpoint_enforces_app_tenant_scope(client, db_session):
    tenant_a, user_a, org_unit_a, agent_a = await seed_admin_tenant_and_agent(db_session)
    headers_a = admin_headers(str(user_a.id), str(tenant_a.id), str(org_unit_a.id))
    app_id = await _create_app(client, headers_a, str(agent_a.id))

    tenant_b, user_b, org_unit_b, _agent_b = await seed_admin_tenant_and_agent(db_session)
    headers_b = admin_headers(str(user_b.id), str(tenant_b.id), str(org_unit_b.id))

    response = await client.get(f"/admin/apps/{app_id}/coding-agent/capabilities", headers=headers_b)
    assert response.status_code == 404
