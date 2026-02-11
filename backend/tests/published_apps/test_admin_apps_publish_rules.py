import pytest
from sqlalchemy import select
from uuid import UUID

from app.db.postgres.models.agents import AgentStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision, PublishedAppRevisionBuildStatus
from app.services.published_app_bundle_storage import PublishedAppBundleStorageError
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


@pytest.mark.asyncio
async def test_publish_guard_enforces_build_pending_and_failed_contracts(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_BUILDER_PUBLISH_BUILD_GUARD_ENABLED", "1")
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

    publish_pending_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_pending_resp.status_code == 409
    pending_payload = publish_pending_resp.json()["detail"]
    assert pending_payload["code"] == "BUILD_PENDING"
    assert pending_payload["build_status"] == "queued"

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    draft_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert draft_row is not None
    draft_row.build_status = PublishedAppRevisionBuildStatus.failed
    draft_row.build_error = "npm run build exited with code 1"
    await db_session.commit()

    publish_failed_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_failed_resp.status_code == 422
    failed_payload = publish_failed_resp.json()["detail"]
    assert failed_payload["code"] == "BUILD_FAILED"
    assert failed_payload["build_status"] == "failed"
    assert any("exited with code 1" in item["message"] for item in failed_payload["diagnostics"])

    draft_row.build_status = PublishedAppRevisionBuildStatus.succeeded
    draft_row.build_error = None
    await db_session.commit()

    publish_ok_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_ok_resp.status_code == 200
    assert publish_ok_resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_publish_returns_copy_failed_when_artifact_promotion_errors(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_BUILDER_PUBLISH_BUILD_GUARD_ENABLED", "1")
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

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    draft_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert draft_row is not None
    draft_row.build_status = PublishedAppRevisionBuildStatus.succeeded
    draft_row.build_error = None
    draft_row.dist_storage_prefix = "apps/t/a/revisions/draft-revision/dist"
    await db_session.commit()

    class _FailingStorage:
        def copy_prefix(self, *, source_prefix: str, destination_prefix: str) -> int:
            raise PublishedAppBundleStorageError("copy failed for test")

    monkeypatch.setattr(
        "app.api.routers.published_apps_admin.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _FailingStorage()),
    )

    publish_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_resp.status_code == 500
    detail = publish_resp.json()["detail"]
    assert detail["code"] == "BUILD_ARTIFACT_COPY_FAILED"

    refreshed_app = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert refreshed_app is not None
    refreshed_status = refreshed_app.status.value if hasattr(refreshed_app.status, "value") else str(refreshed_app.status)
    assert refreshed_status == "draft"
    assert refreshed_app.current_published_revision_id is None
