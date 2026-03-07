from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppStatus,
)
from app.api.routers.published_apps_admin_access import _get_active_publish_job_for_app
from app.workers.tasks import publish_version_pointer_after_build_task
from tests.published_apps._helpers import (
    admin_headers,
    seed_admin_tenant_and_agent,
    start_publish_version_and_wait,
)


async def _create_app(client, headers: dict[str, str], *, name: str, agent_id: str) -> str:
    resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": name,
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert resp.status_code == 200
    return str(resp.json()["id"])


@pytest.mark.asyncio
async def test_removed_legacy_endpoints_return_410_with_migration_codes(client, db_session):
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

    preview_token_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions/{revision_id}/preview-token",
        headers=headers,
        json={},
    )
    assert preview_token_resp.status_code == 410
    assert preview_token_resp.json()["detail"]["code"] == "BUILDER_REVISIONS_ENDPOINT_REMOVED"

    build_status_resp = await client.get(
        f"/admin/apps/{app_id}/builder/revisions/{revision_id}/build",
        headers=headers,
    )
    assert build_status_resp.status_code == 410
    assert build_status_resp.json()["detail"]["code"] == "BUILDER_REVISIONS_ENDPOINT_REMOVED"

    build_retry_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry",
        headers=headers,
        json={},
    )
    assert build_retry_resp.status_code == 410
    assert build_retry_resp.json()["detail"]["code"] == "BUILDER_REVISIONS_ENDPOINT_REMOVED"

    checkpoints_resp = await client.get(f"/admin/apps/{app_id}/coding-agent/v2/checkpoints", headers=headers)
    assert checkpoints_resp.status_code == 410
    assert checkpoints_resp.json()["detail"]["code"] == "CODING_AGENT_CHECKPOINTS_ENDPOINT_REMOVED"

    restore_checkpoint_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/checkpoints/{revision_id}/restore",
        headers=headers,
        json={},
    )
    assert restore_checkpoint_resp.status_code == 410
    assert restore_checkpoint_resp.json()["detail"]["code"] == "CODING_AGENT_CHECKPOINTS_ENDPOINT_REMOVED"

    old_publish_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers, json={})
    assert old_publish_resp.status_code == 410
    assert old_publish_resp.json()["detail"]["code"] == "PUBLISH_ENDPOINT_REMOVED"


@pytest.mark.asyncio
async def test_versions_list_get_create_restore_and_cross_app_guard(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    app_id = await _create_app(client, headers, name="Version List App", agent_id=str(agent.id))
    app_two_id = await _create_app(client, headers, name="Version Guard App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = state_resp.json()["current_draft_revision"]["id"]

    versions_resp = await client.get(f"/admin/apps/{app_id}/versions?limit=25", headers=headers)
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) >= 1
    assert versions[0]["files"] == {}

    get_initial_resp = await client.get(f"/admin/apps/{app_id}/versions/{initial_revision_id}", headers=headers)
    assert get_initial_resp.status_code == 200
    initial_payload = get_initial_resp.json()
    assert initial_payload["id"] == initial_revision_id
    assert isinstance(initial_payload["files"], dict)

    create_draft_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "files": {
                **initial_payload["files"],
                "src/App.tsx": "export default function App() { return <main>v2</main>; }",
            },
            "entry_file": initial_payload["entry_file"],
        },
    )
    assert create_draft_resp.status_code == 200
    draft_v2 = create_draft_resp.json()
    assert draft_v2["origin_kind"] == "manual_save"
    assert draft_v2["source_revision_id"] == initial_revision_id

    restore_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{initial_revision_id}/restore",
        headers=headers,
        json={},
    )
    assert restore_resp.status_code == 200
    restored = restore_resp.json()
    assert restored["restored_from_revision_id"] == initial_revision_id

    cross_app_resp = await client.get(
        f"/admin/apps/{app_two_id}/versions/{restored['id']}",
        headers=headers,
    )
    assert cross_app_resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_save_enqueues_build_but_restore_does_not(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Version Build Queue App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = state_resp.json()["current_draft_revision"]["id"]

    enqueue_calls: list[tuple[str, str]] = []

    def _enqueue_stub(*, revision, app, build_kind):
        _ = app
        enqueue_calls.append((str(revision.id), str(build_kind)))
        return None

    monkeypatch.setattr(
        "app.api.routers.published_apps_admin_routes_versions.enqueue_revision_build",
        _enqueue_stub,
    )

    create_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export default function App() { return <main>manual-save</main>; }",
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    created_revision_id = create_resp.json()["id"]
    assert enqueue_calls == [(created_revision_id, "manual_save")]

    restore_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{initial_revision_id}/restore",
        headers=headers,
        json={},
    )
    assert restore_resp.status_code == 200
    assert enqueue_calls == [(created_revision_id, "manual_save")]


@pytest.mark.asyncio
async def test_restore_falls_back_to_inline_files_when_manifest_materialization_fails(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Restore Fallback App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = state_resp.json()["current_draft_revision"]["id"]

    create_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export default function App() { return <main>restore-fallback</main>; }",
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    target_version_id = create_resp.json()["id"]

    target_row = await db_session.get(PublishedAppRevision, UUID(target_version_id))
    assert target_row is not None
    target_row.manifest_json = {"src/App.tsx": "missing-blob-hash"}
    await db_session.commit()

    restore_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{target_version_id}/restore",
        headers=headers,
        json={},
    )
    assert restore_resp.status_code == 200
    restored = restore_resp.json()
    assert restored["restored_from_revision_id"] == target_version_id
    assert "restore-fallback" in restored["files"].get("src/App.tsx", "")


@pytest.mark.asyncio
async def test_restore_returns_409_when_version_source_is_unrecoverable(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Restore Unrecoverable App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = state_resp.json()["current_draft_revision"]["id"]

    create_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export default function App() { return <main>unrecoverable</main>; }",
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    target_version_id = create_resp.json()["id"]

    target_row = await db_session.get(PublishedAppRevision, UUID(target_version_id))
    assert target_row is not None
    target_row.manifest_json = {"src/App.tsx": "missing-blob-hash"}
    target_row.files = {}
    await db_session.commit()

    restore_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{target_version_id}/restore",
        headers=headers,
        json={},
    )
    assert restore_resp.status_code == 409
    detail = restore_resp.json()["detail"]
    assert detail["code"] == "VERSION_SOURCE_UNAVAILABLE"
    assert detail["version_id"] == target_version_id


@pytest.mark.asyncio
async def test_publish_selected_version_rebuilds_from_version_snapshot(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Publish By Version App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = state_resp.json()["current_draft_revision"]["id"]

    # Create an explicit selected version and publish by that exact version id.
    create_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export default function App() { return <main>publish-by-version</main>; }",
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    selected_version_id = create_resp.json()["id"]
    selected_row = await db_session.get(PublishedAppRevision, UUID(selected_version_id))
    assert selected_row is not None
    selected_row.dist_storage_prefix = f"published-apps/test/{selected_version_id}/dist"
    selected_row.dist_manifest = {"assets": {"index.js": {"file": "assets/index.js"}}}
    await db_session.commit()

    revisions_before_count = int(
        (
            await db_session.execute(
                select(func.count(PublishedAppRevision.id)).where(PublishedAppRevision.published_app_id == UUID(app_id))
            )
        ).scalar_one()
    )

    _, publish_status = await start_publish_version_and_wait(
        client,
        app_id=app_id,
        version_id=selected_version_id,
        headers=headers,
        attempts=20,
    )
    assert publish_status["source_revision_id"] == selected_version_id
    assert publish_status["status"] == "succeeded"
    assert publish_status["published_revision_id"] == selected_version_id

    app_row = await db_session.get(PublishedApp, UUID(app_id))
    assert app_row is not None
    assert str(app_row.current_published_revision_id) == selected_version_id

    revisions_after_count = int(
        (
            await db_session.execute(
                select(func.count(PublishedAppRevision.id)).where(PublishedAppRevision.published_app_id == UUID(app_id))
            )
        ).scalar_one()
    )
    assert revisions_after_count == revisions_before_count

    app_resp = await client.get(f"/admin/apps/{app_id}", headers=headers)
    assert app_resp.status_code == 200
    app_payload = app_resp.json()
    assert app_payload["current_published_revision_id"] == selected_version_id


@pytest.mark.asyncio
async def test_publish_selected_version_missing_dist_waits_for_build_and_then_succeeds(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Publish Missing Dist App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    selected_version_id = state_resp.json()["current_draft_revision"]["id"]

    queued_job_ids: list[str] = []

    def _delay_stub(*, job_id: str):
        queued_job_ids.append(str(job_id))
        return None

    monkeypatch.setattr(
        "app.workers.tasks.publish_version_pointer_after_build_task.delay",
        _delay_stub,
    )

    publish_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{selected_version_id}/publish",
        headers=headers,
        json={},
    )
    assert publish_resp.status_code == 200
    payload = publish_resp.json()
    assert payload["status"] == "queued"
    assert payload["source_revision_id"] == selected_version_id
    assert payload["published_revision_id"] is None
    assert len(queued_job_ids) == 1

    selected_row = await db_session.get(PublishedAppRevision, UUID(selected_version_id))
    assert selected_row is not None
    selected_row.build_status = PublishedAppRevisionBuildStatus.succeeded
    selected_row.dist_storage_prefix = f"published-apps/test/{selected_version_id}/dist"
    selected_row.dist_manifest = {"entry_html": "index.html", "assets": []}
    await db_session.commit()

    task_result = await asyncio.to_thread(
        publish_version_pointer_after_build_task.run,
        queued_job_ids[0],
    )
    assert task_result["status"] == "succeeded"

    status_resp = await client.get(
        f"/admin/apps/{app_id}/publish/jobs/{payload['job_id']}",
        headers=headers,
    )
    assert status_resp.status_code == 200
    status_payload = status_resp.json()
    assert status_payload["status"] == "succeeded"
    assert status_payload["published_revision_id"] == selected_version_id

    app_row = await db_session.get(PublishedApp, UUID(app_id))
    assert app_row is not None
    assert str(app_row.current_published_revision_id) == selected_version_id


@pytest.mark.asyncio
async def test_publish_selected_version_missing_dist_fails_and_keeps_previous_published(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Publish Wait Fail App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    initial_revision_id = state_resp.json()["current_draft_revision"]["id"]

    create_resp = await client.post(
        f"/admin/apps/{app_id}/versions/draft",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export default function App() { return <main>publish-fail</main>; }",
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    selected_version_id = create_resp.json()["id"]

    previous_published = await db_session.get(PublishedAppRevision, UUID(initial_revision_id))
    assert previous_published is not None
    previous_published.dist_storage_prefix = f"published-apps/test/{initial_revision_id}/dist"
    previous_published.dist_manifest = {"entry_html": "index.html", "assets": []}
    app_row = await db_session.get(PublishedApp, UUID(app_id))
    assert app_row is not None
    app_row.current_published_revision_id = previous_published.id
    app_row.status = PublishedAppStatus.published
    await db_session.commit()

    queued_job_ids: list[str] = []

    def _delay_stub(*, job_id: str):
        queued_job_ids.append(str(job_id))
        return None

    monkeypatch.setattr(
        "app.workers.tasks.publish_version_pointer_after_build_task.delay",
        _delay_stub,
    )

    publish_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{selected_version_id}/publish",
        headers=headers,
        json={},
    )
    assert publish_resp.status_code == 200
    payload = publish_resp.json()
    assert payload["status"] == "queued"
    assert len(queued_job_ids) == 1

    selected_row = await db_session.get(PublishedAppRevision, UUID(selected_version_id))
    assert selected_row is not None
    selected_row.build_status = PublishedAppRevisionBuildStatus.failed
    selected_row.build_error = "npm run build failed"
    selected_row.dist_storage_prefix = None
    selected_row.dist_manifest = None
    await db_session.commit()

    task_result = await asyncio.to_thread(
        publish_version_pointer_after_build_task.run,
        queued_job_ids[0],
    )
    assert task_result["status"] == "failed"

    status_resp = await client.get(
        f"/admin/apps/{app_id}/publish/jobs/{payload['job_id']}",
        headers=headers,
    )
    assert status_resp.status_code == 200
    status_payload = status_resp.json()
    assert status_payload["status"] == "failed"
    assert status_payload["published_revision_id"] is None
    diagnostics = status_payload.get("diagnostics") or []
    assert diagnostics
    assert any(str(item.get("kind")) == "publish_wait_build" for item in diagnostics if isinstance(item, dict))
    assert any(str(item.get("kind")) == "auto_fix_submission" for item in diagnostics if isinstance(item, dict))

    refreshed_app = await db_session.get(PublishedApp, UUID(app_id))
    assert refreshed_app is not None
    assert str(refreshed_app.current_published_revision_id) == initial_revision_id


@pytest.mark.asyncio
async def test_get_active_publish_job_expires_stale_job(db_session, monkeypatch):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = PublishedApp(
        tenant_id=tenant.id,
        agent_id=agent.id,
        name="Publish Stale Timeout App",
        slug="publish-stale-timeout-app",
    )
    db_session.add(app)
    await db_session.flush()

    stale_at = datetime.now(timezone.utc) - timedelta(hours=2)
    stale_job = PublishedAppPublishJob(
        published_app_id=app.id,
        tenant_id=tenant.id,
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

    active_job = await _get_active_publish_job_for_app(db_session, app_id=app.id)
    assert active_job is None

    refreshed_stale_job = await db_session.get(PublishedAppPublishJob, stale_job.id)
    assert refreshed_stale_job is not None
    assert refreshed_stale_job.status == PublishedAppPublishJobStatus.failed
    assert refreshed_stale_job.stage == "timed_out"
    assert "timed out" in str(refreshed_stale_job.error or "").lower()

    diagnostics = list(refreshed_stale_job.diagnostics or [])
    assert any(str(item.get("kind")) == "publish_job_timeout" for item in diagnostics if isinstance(item, dict))


@pytest.mark.asyncio
async def test_version_preview_runtime_returns_tokenized_url(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app(client, headers, name="Version Runtime App", agent_id=str(agent.id))

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    selected_version_id = state_resp.json()["current_draft_revision"]["id"]

    runtime_resp = await client.get(
        f"/admin/apps/{app_id}/versions/{selected_version_id}/preview-runtime",
        headers=headers,
    )
    assert runtime_resp.status_code == 409
    detail = runtime_resp.json()["detail"]
    assert detail["code"] == "VERSION_BUILD_NOT_READY"
    assert detail["version_id"] == selected_version_id
