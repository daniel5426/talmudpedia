import pytest

from app.db.postgres.models.workspace import Project
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_settings_api_keys_for_organization_and_project(client, db_session):
    tenant, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    project = Project(
        organization_id=tenant.id,
        name="Build",
        slug="build",
        description="Build project",
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()

    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    org_create = await client.post(
        "/api/settings/api-keys",
        headers=headers,
        json={"owner_scope": "organization", "name": "Org Key", "scopes": ["agents.embed"]},
    )
    assert org_create.status_code == 201
    org_id = org_create.json()["api_key"]["id"]

    org_list = await client.get("/api/settings/api-keys?owner_scope=organization", headers=headers)
    assert org_list.status_code == 200
    assert org_list.json()[0]["name"] == "Org Key"

    project_create = await client.post(
        "/api/settings/api-keys",
        headers=headers,
        json={"owner_scope": "project", "project_id": str(project.id), "name": "Project Key", "scopes": ["agents.embed"]},
    )
    assert project_create.status_code == 201
    project_id = project_create.json()["api_key"]["id"]

    project_revoke = await client.post(
        f"/api/settings/api-keys/{project_id}/revoke?owner_scope=project&project_id={project.id}",
        headers=headers,
    )
    assert project_revoke.status_code == 200
    assert project_revoke.json()["api_key"]["status"] == "revoked"

    delete_resp = await client.delete(
        f"/api/settings/api-keys/{org_id}?owner_scope=organization",
        headers=headers,
    )
    assert delete_resp.status_code == 204
