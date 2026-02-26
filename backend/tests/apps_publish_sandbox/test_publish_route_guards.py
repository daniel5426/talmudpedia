from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
)
from ..published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app(client, headers: dict[str, str], agent_id: str, *, slug: str) -> str:
    resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": f"App {slug}",
            "slug": slug,
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_publish_requires_active_draft_dev_session_in_sandbox_mode(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_PUBLISH_USE_SANDBOX_BUILD", "1")

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, str(agent.id), slug="sandbox-publish-no-session")

    resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers, json={})
    assert resp.status_code == 409
    payload = resp.json()["detail"]
    assert payload["code"] == "DRAFT_DEV_SESSION_REQUIRED_FOR_PUBLISH"


@pytest.mark.asyncio
async def test_publish_rejects_concurrent_active_publish_job(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_PUBLISH_USE_SANDBOX_BUILD", "1")

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, str(agent.id), slug="sandbox-publish-mutex")

    app_row = await db_session.get(PublishedApp, UUID(app_id))
    assert app_row is not None

    draft_session = PublishedAppDraftDevSession(
        published_app_id=app_row.id,
        user_id=user.id,
        revision_id=app_row.current_draft_revision_id,
        status=PublishedAppDraftDevSessionStatus.running,
        sandbox_id="sandbox-test-1",
        preview_url="http://127.0.0.1:5173/sandbox/sandbox-test-1",
        idle_timeout_seconds=180,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        last_activity_at=datetime.now(timezone.utc),
        dependency_hash="test",
    )
    db_session.add(draft_session)
    db_session.add(
        PublishedAppPublishJob(
            published_app_id=app_row.id,
            tenant_id=tenant.id,
            requested_by=user.id,
            status=PublishedAppPublishJobStatus.running,
            stage="build",
            diagnostics=[],
            started_at=datetime.now(timezone.utc),
            last_heartbeat_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers, json={})
    assert resp.status_code == 409
    payload = resp.json()["detail"]
    assert payload["code"] == "PUBLISH_JOB_ACTIVE"
    assert payload["active_publish_job_id"]
