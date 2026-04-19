from uuid import uuid4

import pytest

from app.db.postgres.models.workspace import Project
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_settings_projects_list_update_and_members(client, db_session):
    tenant, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    project = Project(
      organization_id=tenant.id,
      name="Alpha",
      slug="alpha",
      description="Project Alpha",
      created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()

    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    list_resp = await client.get("/api/settings/projects", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["slug"] == "alpha"

    patch_resp = await client.patch(
      "/api/settings/projects/alpha",
      headers=headers,
      json={"name": "Alpha Updated", "description": "Updated"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Alpha Updated"

    members_resp = await client.get("/api/settings/projects/alpha/members", headers=headers)
    assert members_resp.status_code == 200
    assert members_resp.json() == []
