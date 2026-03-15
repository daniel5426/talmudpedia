from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
)
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_coding_batch_finalizer import PublishedAppCodingBatchFinalizer
from app.services.published_app_versioning import create_app_version
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[UUID, UUID]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": f"Batch Finalizer App {uuid4().hex[:6]}",
            "agent_id": agent_id,
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = UUID(create_resp.json()["id"])

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = UUID(state_resp.json()["current_draft_revision"]["id"])
    return app_id, draft_revision_id


def _new_scope_run(
    *,
    tenant_id: UUID,
    agent_id: UUID,
    user_id: UUID,
    app_id: UUID,
    base_revision_id: UUID,
    status: RunStatus,
) -> AgentRun:
    now = datetime.now(timezone.utc)
    return AgentRun(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=status,
        surface=CODING_AGENT_SURFACE,
        published_app_id=app_id,
        base_revision_id=base_revision_id,
        input_params={"context": {"chat_session_id": f"chat-{uuid4()}"}},
        execution_engine="opencode",
        completed_at=now if status == RunStatus.completed else None,
    )


@pytest.mark.asyncio
async def test_batch_finalizer_diff_only_creates_one_shared_revision_per_app_batch(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    app = await db_session.get(PublishedApp, app_id)
    draft = await db_session.get(PublishedAppRevision, draft_revision_id)
    assert app is not None
    assert draft is not None

    live_files = dict(draft.files or {})
    live_files["src/App.tsx"] = "export default function App() { return <div>changed</div>; }"

    same_as_live_base = await create_app_version(
        db_session,
        app=app,
        kind=draft.kind,
        template_key=draft.template_key,
        entry_file=draft.entry_file,
        files=live_files,
        created_by=user.id,
        source_revision_id=draft.id,
        origin_kind="test_seed",
        build_status=draft.build_status,
        build_seq=int(draft.build_seq or 0) + 1,
        template_runtime=draft.template_runtime or "vite_static",
    )

    run_no_diff = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=same_as_live_base.id,
        status=RunStatus.completed,
    )
    run_with_diff = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        app_id=app_id,
        base_revision_id=draft.id,
        status=RunStatus.completed,
    )
    db_session.add_all([run_no_diff, run_with_diff])
    await db_session.commit()
    await db_session.refresh(run_no_diff)
    await db_session.refresh(run_with_diff)

    async def _fake_prepare(self, *, app_id, sample_run):
        _ = sample_run
        loaded_app = await self.db.get(PublishedApp, app_id)
        loaded_current = await self.db.get(PublishedAppRevision, draft.id)
        assert loaded_app is not None
        assert loaded_current is not None
        return loaded_app, loaded_current, dict(live_files)

    monkeypatch.setattr(PublishedAppCodingBatchFinalizer, "_prepare_finalized_live_snapshot", _fake_prepare)

    enqueue_calls: list[str] = []

    def _enqueue_stub(*, revision, app, build_kind):
        _ = app
        enqueue_calls.append(f"{revision.id}:{build_kind}")
        return None

    monkeypatch.setattr(
        "app.services.published_app_coding_batch_finalizer.enqueue_revision_build",
        _enqueue_stub,
    )

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=run_with_diff.id)
    assert result["status"] == "finalized"
    assert result["candidate_count"] == 2
    assert str(run_no_diff.id) in result["revision_ids_by_run"]
    assert str(run_with_diff.id) in result["revision_ids_by_run"]
    assert result["revision_ids_by_run"][str(run_no_diff.id)] == result["revision_ids_by_run"][str(run_with_diff.id)]

    refreshed_no_diff = await db_session.get(AgentRun, run_no_diff.id)
    refreshed_with_diff = await db_session.get(AgentRun, run_with_diff.id)
    assert refreshed_no_diff is not None
    assert refreshed_with_diff is not None

    assert refreshed_no_diff.batch_finalized_at is not None
    assert refreshed_no_diff.result_revision_id is not None

    assert refreshed_with_diff.batch_finalized_at is not None
    assert refreshed_with_diff.result_revision_id is not None
    assert refreshed_no_diff.result_revision_id == refreshed_with_diff.result_revision_id
    assert enqueue_calls
    assert enqueue_calls[0].endswith(":coding_run")


@pytest.mark.asyncio
async def test_batch_finalizer_marks_revision_failed_when_build_enqueue_fails(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    app = await db_session.get(PublishedApp, app_id)
    draft = await db_session.get(PublishedAppRevision, draft_revision_id)
    assert app is not None
    assert draft is not None

    live_files = dict(draft.files or {})
    live_files["src/App.tsx"] = "export default function App() { return <div>enqueue-fail</div>; }"

    run_with_diff = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft.id,
        status=RunStatus.completed,
    )
    db_session.add(run_with_diff)
    await db_session.commit()
    await db_session.refresh(run_with_diff)

    async def _fake_prepare(self, *, app_id, sample_run):
        _ = sample_run
        loaded_app = await self.db.get(PublishedApp, app_id)
        loaded_current = await self.db.get(PublishedAppRevision, draft.id)
        assert loaded_app is not None
        assert loaded_current is not None
        return loaded_app, loaded_current, dict(live_files)

    monkeypatch.setattr(PublishedAppCodingBatchFinalizer, "_prepare_finalized_live_snapshot", _fake_prepare)

    def _enqueue_fail(*, revision, app, build_kind):
        _ = revision, app, build_kind
        return "enqueue exploded"

    monkeypatch.setattr(
        "app.services.published_app_coding_batch_finalizer.enqueue_revision_build",
        _enqueue_fail,
    )

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=run_with_diff.id)
    assert result["status"] == "finalized"
    created_revision_id = result["revision_ids_by_run"][str(run_with_diff.id)]
    created_revision = await db_session.get(PublishedAppRevision, UUID(created_revision_id))
    assert created_revision is not None
    assert created_revision.build_status == PublishedAppRevisionBuildStatus.failed
    assert "enqueue exploded" in str(created_revision.build_error or "")


@pytest.mark.asyncio
async def test_batch_finalizer_skips_when_active_runs_remain(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    completed = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.completed,
    )
    running = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.running,
    )
    db_session.add_all([completed, running])
    await db_session.commit()
    await db_session.refresh(completed)

    async def _unexpected_prepare(self, *, app_id, sample_run):
        _ = app_id, sample_run
        raise AssertionError("finalizer should not prepare snapshots while active runs remain")

    monkeypatch.setattr(PublishedAppCodingBatchFinalizer, "_prepare_finalized_live_snapshot", _unexpected_prepare)

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=completed.id)
    assert result["status"] == "active_runs_remaining"
    assert result["active_count"] >= 1

    refreshed = await db_session.get(AgentRun, completed.id)
    assert refreshed is not None
    assert refreshed.batch_finalized_at is None
