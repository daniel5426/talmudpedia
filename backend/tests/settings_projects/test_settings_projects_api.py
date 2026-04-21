import pytest

from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_settings_projects_list_update_and_members(client, db_session):
    organization, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)

    headers = admin_headers(str(owner.id), str(organization.id), str(org_unit.id))

    create_resp = await client.post(
      "/api/settings/projects",
      headers=headers,
      json={"name": "Alpha", "description": "Project Alpha"},
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    list_resp = await client.get("/api/settings/projects", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["id"] == project_id
    assert list_resp.json()[0]["name"] == "Alpha"

    patch_resp = await client.patch(
      f"/api/settings/projects/{project_id}",
      headers=headers,
      json={"name": "Alpha Updated", "description": "Updated"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Alpha Updated"

    members_resp = await client.get(f"/api/settings/projects/{project_id}/members", headers=headers)
    assert members_resp.status_code == 200
    assert len(members_resp.json()) == 1
