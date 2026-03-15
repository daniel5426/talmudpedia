from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_coding_batch_finalizer import PublishedAppCodingBatchFinalizer
from app.services.published_app_versioning import create_app_version
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[UUID, UUID]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": f"Version Run Diff App {uuid4().hex[:6]}",
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
    return app_id, UUID(state_resp.json()["current_draft_revision"]["id"])


def _run(*, tenant_id: UUID, agent_id: UUID, user_id: UUID, app_id: UUID, base_revision_id: UUID) -> AgentRun:
    return AgentRun(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=RunStatus.completed,
        surface=CODING_AGENT_SURFACE,
        published_app_id=app_id,
        base_revision_id=base_revision_id,
        input_params={"context": {"chat_session_id": f"chat-{uuid4()}"}},
        execution_engine="opencode",
        completed_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_completed_runs_create_versions_only_when_live_differs_from_base(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    app = await db_session.get(PublishedApp, app_id)
    draft = await db_session.get(PublishedAppRevision, draft_revision_id)
    assert app is not None
    assert draft is not None

    live_files = dict(draft.files or {})
    live_files["src/App.tsx"] = "export default function App() { return <main>run-diff</main>; }"

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

    run_same = _run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=same_as_live_base.id,
    )
    run_diff = _run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=UUID("00000000-0000-0000-0000-000000000004"),
        app_id=app_id,
        base_revision_id=draft.id,
    )
    db_session.add_all([run_same, run_diff])
    await db_session.commit()

    async def _fake_prepare(self, *, app_id, sample_run):
        _ = sample_run
        loaded_app = await self.db.get(PublishedApp, app_id)
        loaded_current = await self.db.get(PublishedAppRevision, draft.id)
        assert loaded_app is not None
        assert loaded_current is not None
        return loaded_app, loaded_current, dict(live_files)

    monkeypatch.setattr(PublishedAppCodingBatchFinalizer, "_prepare_finalized_live_snapshot", _fake_prepare)

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=run_diff.id)
    assert result["status"] == "finalized"
    assert str(run_same.id) in result["revision_ids_by_run"]
    assert str(run_diff.id) in result["revision_ids_by_run"]
    assert result["revision_ids_by_run"][str(run_same.id)] == result["revision_ids_by_run"][str(run_diff.id)]

    refreshed_same = await db_session.get(AgentRun, run_same.id)
    refreshed_diff = await db_session.get(AgentRun, run_diff.id)
    assert refreshed_same is not None
    assert refreshed_diff is not None
    assert refreshed_same.result_revision_id is not None
    assert refreshed_diff.result_revision_id is not None
    assert refreshed_same.result_revision_id == refreshed_diff.result_revision_id
