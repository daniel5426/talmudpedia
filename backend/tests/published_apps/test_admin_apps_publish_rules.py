import pytest
from sqlalchemy import select
from uuid import UUID

from app.db.postgres.models.agents import AgentStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision, PublishedAppRevisionBuildStatus
from ._helpers import admin_headers, seed_admin_tenant_and_agent, start_publish_and_wait


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
    _, publish_status = await start_publish_and_wait(client, app_id=app_id, headers=headers)
    assert publish_status["status"] == "succeeded"
    assert publish_status["published_revision_id"]

    app_resp = await client.get(f"/admin/apps/{app_id}", headers=headers)
    assert app_resp.status_code == 200
    app_payload = app_resp.json()
    assert app_payload["status"] == "published"
    assert app_payload["published_url"] == "https://runtime-app.apps.localhost"

    preview_resp = await client.get(f"/admin/apps/{app_id}/runtime-preview", headers=headers)
    assert preview_resp.status_code == 200
    assert preview_resp.json()["runtime_url"] == "https://runtime-app.apps.localhost"

    unpublish_resp = await client.post(f"/admin/apps/{app_id}/unpublish", headers=headers)
    assert unpublish_resp.status_code == 200
    assert unpublish_resp.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_publish_no_longer_gates_on_draft_build_status(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Build Guard App",
            "slug": "build-guard-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    draft_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert draft_row is not None
    draft_row.build_status = PublishedAppRevisionBuildStatus.failed
    draft_row.build_error = "npm run build exited with code 1"
    await db_session.commit()

    _, publish_status = await start_publish_and_wait(client, app_id=app_id, headers=headers)
    assert publish_status["status"] == "succeeded"
    assert publish_status["published_revision_id"]


@pytest.mark.asyncio
async def test_publish_failure_keeps_current_published_revision(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Artifact Promotion App",
            "slug": "artifact-promotion-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    _, first_status = await start_publish_and_wait(client, app_id=app_id, headers=headers)
    assert first_status["status"] == "succeeded"
    published_revision_id = first_status["published_revision_id"]

    monkeypatch.setenv("APPS_PUBLISH_MOCK_MODE", "0")

    async def _failing_subprocess(*_args, **_kwargs):
        return 1, "", "mock publish failure"

    monkeypatch.setattr("app.workers.tasks._run_subprocess", _failing_subprocess)

    _, failed_status = await start_publish_and_wait(client, app_id=app_id, headers=headers)
    assert failed_status["status"] == "failed"
    assert "mock publish failure" in (failed_status.get("error") or "")

    refreshed_app = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert refreshed_app is not None
    assert str(refreshed_app.current_published_revision_id) == published_revision_id
