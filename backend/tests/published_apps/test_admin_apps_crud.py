import pytest

from ._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_admin_apps_crud(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Support App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["slug"] == "support-app"
    assert created["template_key"] == "chat-classic"
    app_id = created["id"]

    list_resp = await client.get("/admin/apps", headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == app_id for item in list_resp.json())

    patch_resp = await client.patch(
        f"/admin/apps/{app_id}",
        headers=headers,
        json={"name": "Support App v2", "auth_enabled": False, "auth_providers": ["password", "google"]},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == "Support App v2"
    assert updated["auth_enabled"] is False
    assert "google" in updated["auth_providers"]

    get_resp = await client.get(f"/admin/apps/{app_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == app_id

    delete_resp = await client.delete(f"/admin/apps/{app_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deleted"
