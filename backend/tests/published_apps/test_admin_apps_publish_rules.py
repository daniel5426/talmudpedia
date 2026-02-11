import pytest

from app.db.postgres.models.agents import AgentStatus
from ._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_publish_requires_published_agent(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    agent.status = AgentStatus.draft
    await db_session.commit()

    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Draft Linked App",
            "slug": "draft-linked-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 400
    assert "published agents" in create_resp.json()["detail"]


@pytest.mark.asyncio
async def test_publish_unpublish_and_runtime_preview(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Runtime App",
            "slug": "runtime-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    publish_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_resp.status_code == 200
    assert publish_resp.json()["status"] == "published"
    assert publish_resp.json()["published_url"] == "https://runtime-app.apps.localhost"

    preview_resp = await client.get(f"/admin/apps/{app_id}/runtime-preview", headers=headers)
    assert preview_resp.status_code == 200
    assert preview_resp.json()["runtime_url"] == "https://runtime-app.apps.localhost"

    unpublish_resp = await client.post(f"/admin/apps/{app_id}/unpublish", headers=headers)
    assert unpublish_resp.status_code == 200
    assert unpublish_resp.json()["status"] == "draft"
