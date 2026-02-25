from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_coding_batch_finalizer import PublishedAppCodingBatchFinalizer
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[UUID, UUID]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": f"Batch Finalizer App {uuid4().hex[:6]}",
            "agent_id": agent_id,
            "template_key": "chat-classic",
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
    completed_at: datetime | None = None,
) -> AgentRun:
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
        completed_at=completed_at,
    )


@pytest.mark.asyncio
async def test_batch_finalizer_assigns_owner_revision_to_latest_completed(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    now = datetime.now(timezone.utc)
    run_a = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.completed,
        completed_at=now - timedelta(minutes=2),
    )
    run_b = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.completed,
        completed_at=now - timedelta(minutes=1),
    )
    run_c = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.failed,
        completed_at=now,
    )
    db_session.add_all([run_a, run_b, run_c])
    await db_session.commit()
    await db_session.refresh(run_a)
    await db_session.refresh(run_b)
    await db_session.refresh(run_c)

    revision_id = uuid4()

    async def _fake_promote(self, *, app_id, actor_id, owner_run):
        _ = app_id, actor_id
        assert str(owner_run.id) == str(run_b.id)
        return revision_id

    monkeypatch.setattr(
        PublishedAppCodingBatchFinalizer,
        "_promote_shared_stage_and_create_revision",
        _fake_promote,
    )

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=run_c.id)
    assert result["status"] == "finalized"
    assert result["owner_run_id"] == str(run_b.id)
    assert result["revision_id"] == str(revision_id)

    refreshed_a = await db_session.get(AgentRun, run_a.id)
    refreshed_b = await db_session.get(AgentRun, run_b.id)
    refreshed_c = await db_session.get(AgentRun, run_c.id)
    assert refreshed_a is not None
    assert refreshed_b is not None
    assert refreshed_c is not None

    assert refreshed_a.batch_finalized_at is not None
    assert refreshed_a.batch_owner is False
    assert refreshed_a.result_revision_id is None
    assert refreshed_a.checkpoint_revision_id is None

    assert refreshed_b.batch_finalized_at is not None
    assert refreshed_b.batch_owner is True
    assert str(refreshed_b.result_revision_id) == str(revision_id)
    assert str(refreshed_b.checkpoint_revision_id) == str(revision_id)

    assert refreshed_c.batch_finalized_at is None
    assert refreshed_c.batch_owner is False


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
        completed_at=datetime.now(timezone.utc),
    )
    running = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.running,
    )
    db_session.add_all([completed, running])
    await db_session.commit()
    await db_session.refresh(completed)

    async def _unexpected_promote(self, *, app_id, actor_id, owner_run):
        _ = app_id, actor_id, owner_run
        raise AssertionError("Promotion should not run while active runs remain")

    monkeypatch.setattr(
        PublishedAppCodingBatchFinalizer,
        "_promote_shared_stage_and_create_revision",
        _unexpected_promote,
    )

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=completed.id)
    assert result["status"] == "active_runs_remaining"
    assert result["active_count"] >= 1

    refreshed = await db_session.get(AgentRun, completed.id)
    assert refreshed is not None
    assert refreshed.batch_finalized_at is None


@pytest.mark.asyncio
async def test_batch_finalizer_marks_batch_finalized_without_revision_on_no_diff(client, db_session, monkeypatch):
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
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(completed)
    await db_session.commit()
    await db_session.refresh(completed)

    async def _no_revision(self, *, app_id, actor_id, owner_run):
        _ = app_id, actor_id, owner_run
        return None

    monkeypatch.setattr(
        PublishedAppCodingBatchFinalizer,
        "_promote_shared_stage_and_create_revision",
        _no_revision,
    )

    service = PublishedAppCodingBatchFinalizer(db_session)
    result = await service.finalize_for_terminal_run(run_id=completed.id)
    assert result["status"] == "finalized"
    assert result["revision_id"] is None

    refreshed = await db_session.get(AgentRun, completed.id)
    assert refreshed is not None
    assert refreshed.batch_finalized_at is not None
    assert refreshed.batch_owner is True
    assert refreshed.result_revision_id is None
    assert refreshed.checkpoint_revision_id is None


@pytest.mark.asyncio
async def test_stage_prepare_uses_shared_reset_for_first_run_then_no_reset_for_parallel_run(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    service = PublishedAppCodingAgentRuntimeService(db_session)

    run_a = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    db_session.add(run_a)
    await db_session.commit()
    await db_session.refresh(run_a)

    calls: list[bool] = []

    class _FakeClient:
        async def prepare_stage_workspace(self, *, sandbox_id: str, reset: bool):
            _ = sandbox_id
            calls.append(bool(reset))
            return {
                "live_workspace_path": "/workspace/live",
                "stage_workspace_path": "/workspace/.talmudpedia/stage/shared/workspace",
            }

        async def resolve_local_workspace_path(self, *, sandbox_id: str):
            _ = sandbox_id
            return "/workspace/live"

    runtime = SimpleNamespace(client=_FakeClient())
    stage_context_a, stage_error_a = await service._prepare_run_stage_workspace_context(
        run=run_a,
        runtime_service=runtime,
        sandbox_id="sandbox-1",
    )
    assert stage_error_a is None
    assert stage_context_a is not None
    assert stage_context_a["opencode_workspace_path"].endswith("/stage/shared/workspace")

    run_b = _new_scope_run(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.running,
    )
    db_session.add(run_b)
    await db_session.commit()
    await db_session.refresh(run_b)

    stage_context_b, stage_error_b = await service._prepare_run_stage_workspace_context(
        run=run_b,
        runtime_service=runtime,
        sandbox_id="sandbox-1",
    )
    assert stage_error_b is None
    assert stage_context_b is not None
    assert calls == [True, False]
