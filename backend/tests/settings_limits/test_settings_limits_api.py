import pytest

from app.db.postgres.models.workspace import Project
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_settings_limits_for_organization_and_project(client, db_session):
    tenant, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    project = Project(
        organization_id=tenant.id,
        name="Limits Project",
        slug="limits-project",
        description="Limits",
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()

    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    initial_org = await client.get("/api/settings/limits/organization", headers=headers)
    assert initial_org.status_code == 200
    assert initial_org.json()["monthly_token_limit"] is None

    org_patch = await client.patch(
        "/api/settings/limits/organization",
        headers=headers,
        json={"monthly_token_limit": 1000},
    )
    assert org_patch.status_code == 200
    assert org_patch.json()["effective_monthly_token_limit"] == 1000

    project_patch = await client.patch(
        "/api/settings/limits/projects/limits-project",
        headers=headers,
        json={"monthly_token_limit": 400},
    )
    assert project_patch.status_code == 200
    assert project_patch.json()["monthly_token_limit"] == 400
    assert project_patch.json()["inherited_monthly_token_limit"] == 1000
