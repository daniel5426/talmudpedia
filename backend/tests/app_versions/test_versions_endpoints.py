from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_templates import build_template_files, get_template
from app.services.published_app_versioning import create_app_version
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


def _template_files(*, app_id: UUID, public_id: str, agent_id: UUID, template_key: str = "classic-chat") -> tuple[str, dict[str, str]]:
    template = get_template(template_key)
    files = build_template_files(
        template_key,
        runtime_context={
            "app_id": str(app_id),
            "app_slug": public_id,
            "agent_id": str(agent_id),
        },
    )
    return template.entry_file, files


def _install_app_create_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _create_initial_revision(
        db,
        *,
        app,
        kind,
        template_key,
        entry_file,
        files,
        created_by,
        source_revision_id,
        origin_kind,
        **kwargs,
    ):
        _ = db, kind, template_key, entry_file, files, source_revision_id, kwargs
        _, files = _template_files(
            app_id=app.id,
            public_id=app.public_id,
            agent_id=app.agent_id,
            template_key=app.template_key,
        )
        revision = await create_app_version(
            db,
            app=app,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=entry_file,
            files=files,
            created_by=created_by,
            source_revision_id=source_revision_id,
            origin_kind=origin_kind,
            build_status=PublishedAppRevisionBuildStatus.succeeded,
            build_seq=1,
            dist_storage_prefix=f"apps/{app.id}/revisions/{uuid4()}/dist",
            dist_manifest={"entry_html": "index.html", "assets": [], "source_fingerprint": f"fp-{app.id}"},
            template_runtime="vite_static",
        )
        app.current_draft_revision_id = revision.id
        return revision

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_apps.create_app_version", _create_initial_revision)


async def _create_app(
    client,
    headers: dict[str, str],
    *,
    name: str,
    agent_id: str,
) -> str:
    resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": name,
            "agent_id": agent_id,
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert resp.status_code == 200
    return str(resp.json()["id"])


@pytest.mark.asyncio
async def test_removed_legacy_endpoints_return_410_with_migration_codes(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Legacy Cut App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    revision_id = state_resp.json()["current_draft_revision"]["id"]

    create_revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={"base_revision_id": revision_id, "files": {"src/App.tsx": "export default function App(){return <div/>;}"}},
    )
    assert create_revision_resp.status_code == 410
    assert create_revision_resp.json()["detail"]["code"] == "BUILDER_REVISIONS_ENDPOINT_REMOVED"

    versions_draft_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={},
    )
    assert versions_draft_resp.status_code == 410
    assert versions_draft_resp.json()["detail"]["code"] == "VERSIONS_DRAFT_ENDPOINT_REMOVED"

    old_publish_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers, json={})
    assert old_publish_resp.status_code == 410
    assert old_publish_resp.json()["detail"]["code"] == "PUBLISH_ENDPOINT_REMOVED"


@pytest.mark.asyncio
async def test_versions_list_get_restore_and_cross_app_guard(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    app_id = await _create_app(client, headers, name="Version List App", agent_id=str(agent.id))
    app_two_id = await _create_app(client, headers, name="Version Guard App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = UUID(state_resp.json()["current_draft_revision"]["id"])

    app = await db_session.get(PublishedApp, UUID(app_id))
    initial_revision = await db_session.get(PublishedAppRevision, initial_revision_id)
    assert app is not None
    assert initial_revision is not None

    restored_files = dict(initial_revision.files or {})
    restored_files["src/App.tsx"] = "export default function App() { return <main>restore-target</main>; }"
    restore_target = await create_app_version(
        db_session,
        app=app,
        kind=initial_revision.kind,
        template_key=initial_revision.template_key,
        entry_file=initial_revision.entry_file,
        files=restored_files,
        created_by=user.id,
        source_revision_id=initial_revision.id,
        origin_kind="test_seed",
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        build_seq=int(initial_revision.build_seq or 0) + 1,
        dist_storage_prefix=f"apps/{app.id}/revisions/{uuid4()}/dist",
        dist_manifest={"entry_html": "index.html", "assets": [], "source_fingerprint": f"restore-{uuid4()}"},
        template_runtime="vite_static",
    )
    await db_session.commit()

    async def _sync_session(self, *, app, revision, user_id, files, entry_file):
        _ = self, app, revision, user_id, files, entry_file
        return SimpleNamespace(id=uuid4(), revision_id=revision.id, backend_metadata={}, sandbox_id="sandbox-1")

    async def _bind_session(self, *, app_id, user_id, revision):
        _ = self, app_id, user_id, revision
        return None

    async def _restore_materialize(self, *, app, entry_file, source_revision_id, created_by, origin_kind, restored_from_revision_id=None, **kwargs):
        _ = kwargs
        source_revision = await self.db.get(PublishedAppRevision, restored_from_revision_id)
        assert source_revision is not None
        revision = await create_app_version(
            self.db,
            app=app,
            kind=source_revision.kind,
            template_key=source_revision.template_key,
            entry_file=entry_file,
            files=dict(source_revision.files or {}),
            created_by=created_by,
            source_revision_id=source_revision_id,
            origin_kind=origin_kind,
            restored_from_revision_id=restored_from_revision_id,
            build_status=PublishedAppRevisionBuildStatus.succeeded,
            build_seq=int(source_revision.build_seq or 0) + 1,
            workspace_build_id=source_revision.workspace_build_id,
            dist_storage_prefix=source_revision.dist_storage_prefix,
            dist_manifest=dict(source_revision.dist_manifest or {}),
            template_runtime=source_revision.template_runtime or "vite_static",
        )
        app.current_draft_revision_id = revision.id
        return SimpleNamespace(
            revision=revision,
            reused=True,
            source_fingerprint=str((revision.dist_manifest or {}).get("source_fingerprint") or ""),
            workspace_revision_token=None,
        )

    monkeypatch.setattr(
        "app.services.published_app_draft_dev_runtime.PublishedAppDraftDevRuntimeService.sync_session",
        _sync_session,
    )
    monkeypatch.setattr(
        "app.services.published_app_draft_dev_runtime.PublishedAppDraftDevRuntimeService.bind_session_to_revision_without_sync",
        _bind_session,
    )
    monkeypatch.setattr(
        "app.services.published_app_draft_revision_materializer.PublishedAppDraftRevisionMaterializerService.materialize_live_workspace",
        _restore_materialize,
    )

    versions_resp = await client.get(f"/admin/apps/{app_id}/versions?limit=25", headers=headers)
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) >= 2
    assert versions[0]["files"] == {}

    get_initial_resp = await client.get(f"/admin/apps/{app_id}/versions/{initial_revision_id}", headers=headers)
    assert get_initial_resp.status_code == 200
    initial_payload = get_initial_resp.json()
    assert initial_payload["id"] == str(initial_revision_id)
    assert isinstance(initial_payload["files"], dict)

    restore_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{restore_target.id}/restore",
        headers=headers,
        json={},
    )
    assert restore_resp.status_code == 200
    restored = restore_resp.json()
    assert restored["restored_from_revision_id"] == str(restore_target.id)
    assert restored["id"] != str(restore_target.id)

    cross_app_resp = await client.get(
        f"/admin/apps/{app_two_id}/versions/{restored['id']}",
        headers=headers,
    )
    assert cross_app_resp.status_code == 404


@pytest.mark.asyncio
async def test_publish_selected_materialized_version_succeeds_immediately(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Publish Version App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    selected_version_id = state_resp.json()["current_draft_revision"]["id"]

    publish_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{selected_version_id}/publish",
        headers=headers,
        json={},
    )
    assert publish_resp.status_code == 200
    payload = publish_resp.json()
    assert payload["status"] == "succeeded"
    assert payload["source_revision_id"] == selected_version_id
    assert payload["published_revision_id"] == selected_version_id

    status_resp = await client.get(
        f"/admin/apps/{app_id}/publish/jobs/{payload['job_id']}",
        headers=headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "succeeded"

    app_row = await db_session.get(PublishedApp, UUID(app_id))
    assert app_row is not None
    assert str(app_row.current_published_revision_id) == selected_version_id


@pytest.mark.asyncio
async def test_publish_non_materialized_version_returns_revision_not_materialized(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Publish Missing Dist App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = UUID(state_resp.json()["current_draft_revision"]["id"])

    app = await db_session.get(PublishedApp, UUID(app_id))
    current = await db_session.get(PublishedAppRevision, initial_revision_id)
    assert app is not None
    assert current is not None

    missing_dist_revision = await create_app_version(
        db_session,
        app=app,
        kind=current.kind,
        template_key=current.template_key,
        entry_file=current.entry_file,
        files=dict(current.files or {}),
        created_by=user.id,
        source_revision_id=current.id,
        origin_kind="test_seed",
        build_status=PublishedAppRevisionBuildStatus.failed,
        build_seq=int(current.build_seq or 0) + 1,
        build_error="watcher output missing",
        template_runtime=current.template_runtime or "vite_static",
    )
    await db_session.commit()

    publish_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{missing_dist_revision.id}/publish",
        headers=headers,
        json={},
    )
    assert publish_resp.status_code == 409
    detail = publish_resp.json()["detail"]
    assert detail["code"] == "REVISION_NOT_MATERIALIZED"
    assert detail["version_id"] == str(missing_dist_revision.id)


@pytest.mark.asyncio
async def test_get_active_publish_job_expires_stale_job(db_session, monkeypatch):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = PublishedApp(
        organization_id=tenant.id,
        agent_id=agent.id,
        name="Publish Stale Timeout App",
        public_id=f"publish-stale-timeout-app-{uuid4().hex[:8]}",
    )
    db_session.add(app)
    await db_session.flush()

    stale_at = datetime.now(timezone.utc) - timedelta(hours=2)
    stale_job = PublishedAppPublishJob(
        published_app_id=app.id,
        organization_id=tenant.id,
        requested_by=user.id,
        status=PublishedAppPublishJobStatus.running,
        stage="waiting_for_build",
        error=None,
        diagnostics=[],
        created_at=stale_at,
        started_at=stale_at,
        last_heartbeat_at=stale_at,
        finished_at=None,
    )
    db_session.add(stale_job)
    await db_session.commit()

    monkeypatch.setenv("APPS_PUBLISH_ACTIVE_JOB_STALE_TIMEOUT_SECONDS", "60")

    from app.api.routers.published_apps_admin_access import _get_active_publish_job_for_app

    active_job = await _get_active_publish_job_for_app(db_session, app_id=app.id)
    assert active_job is None

    refreshed_stale_job = await db_session.get(PublishedAppPublishJob, stale_job.id)
    assert refreshed_stale_job is not None
    assert refreshed_stale_job.status == PublishedAppPublishJobStatus.failed
    assert refreshed_stale_job.stage == "timed_out"
    assert "timed out" in str(refreshed_stale_job.error or "").lower()


@pytest.mark.asyncio
async def test_version_preview_runtime_requires_durable_dist(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Version Runtime App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = UUID(state_resp.json()["current_draft_revision"]["id"])

    app = await db_session.get(PublishedApp, UUID(app_id))
    current = await db_session.get(PublishedAppRevision, initial_revision_id)
    assert app is not None
    assert current is not None

    missing_dist_revision = await create_app_version(
        db_session,
        app=app,
        kind=current.kind,
        template_key=current.template_key,
        entry_file=current.entry_file,
        files=dict(current.files or {}),
        created_by=user.id,
        source_revision_id=current.id,
        origin_kind="test_seed",
        build_status=PublishedAppRevisionBuildStatus.failed,
        build_seq=int(current.build_seq or 0) + 1,
        build_error="not materialized",
        template_runtime=current.template_runtime or "vite_static",
    )
    await db_session.commit()

    runtime_resp = await client.get(
        f"/admin/apps/{app_id}/versions/{missing_dist_revision.id}/preview-runtime",
        headers=headers,
    )
    assert runtime_resp.status_code == 409
    detail = runtime_resp.json()["detail"]
    assert detail["code"] == "VERSION_BUILD_NOT_READY"
    assert detail["version_id"] == str(missing_dist_revision.id)
