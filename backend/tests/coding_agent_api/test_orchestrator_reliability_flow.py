from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedAppCodingRunEvent,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
)
from app.api.routers.published_apps_admin_routes_coding_agent import _resolve_detached_async_bind
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_coding_run_orchestrator import PublishedAppCodingRunOrchestrator
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent Orchestrator Reliability App",
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    return app_id, state_resp.json()["current_draft_revision"]["id"]


async def _insert_run(
    db_session,
    *,
    tenant_id,
    agent_id,
    user_id,
    app_id: str,
    base_revision_id: str,
    status: RunStatus,
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=status,
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
        input_params={
            "input": "reliability flow",
            "context": {
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
                "preview_workspace_stage_path": "/workspace",
            },
        },
        execution_engine="native",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_runner_seq_conflict_reconciles_terminal_status_and_clears_lock(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    draft_session = PublishedAppDraftDevSession(
        published_app_id=UUID(app_id),
        user_id=user.id,
        revision_id=UUID(draft_revision_id),
        status=PublishedAppDraftDevSessionStatus.running,
        idle_timeout_seconds=180,
        sandbox_id="sandbox-test",
        last_activity_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        active_coding_run_id=run.id,
        active_coding_run_locked_at=datetime.now(timezone.utc),
    )
    db_session.add(draft_session)
    db_session.add_all(
        [
            PublishedAppCodingRunEvent(
                run_id=run.id,
                seq=1,
                event="run.accepted",
                stage="run",
                payload_json={"status": "queued"},
                diagnostics_json=[],
            ),
            PublishedAppCodingRunEvent(
                run_id=run.id,
                seq=2,
                event="plan.updated",
                stage="plan",
                payload_json={"summary": "started"},
                diagnostics_json=[],
            ),
            PublishedAppCodingRunEvent(
                run_id=run.id,
                seq=3,
                event="run.failed",
                stage="run",
                payload_json={"status": "failed", "error": "pre-existing terminal"},
                diagnostics_json=[{"message": "pre-existing terminal"}],
            ),
        ]
    )
    await db_session.commit()

    @asynccontextmanager
    async def _session_scope():
        yield db_session

    monkeypatch.setattr(PublishedAppCodingRunOrchestrator, "_session_factory", lambda: _session_scope())

    async def _fake_runtime_stream(self, *, app, run, resume_payload=None):
        yield {
            "event": "run.failed",
            "run_id": str(run.id),
            "app_id": str(app.id),
            "seq": 3,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": "run",
            "payload": {"status": "failed", "error": "runtime failed"},
            "diagnostics": [{"message": "runtime failed"}],
        }

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "stream_run_events", _fake_runtime_stream)

    original_next_seq = PublishedAppCodingRunOrchestrator._next_event_seq
    first_seq_forced = {"used": False}

    async def _force_conflicting_next_seq(*, db, run_id):
        if run_id == run.id and not first_seq_forced["used"]:
            first_seq_forced["used"] = True
            return 3
        return await original_next_seq(db=db, run_id=run_id)

    monkeypatch.setattr(PublishedAppCodingRunOrchestrator, "_next_event_seq", _force_conflicting_next_seq)

    await PublishedAppCodingRunOrchestrator._runner_main(
        app_id=UUID(app_id),
        run_id=run.id,
        owner_token="test-owner",
    )

    persisted_run = await db_session.get(AgentRun, run.id)
    assert persisted_run is not None
    assert persisted_run.status == RunStatus.failed
    assert str(persisted_run.error_message or "").strip() != ""

    persisted_session = await db_session.get(PublishedAppDraftDevSession, draft_session.id)
    assert persisted_session is not None
    assert persisted_session.active_coding_run_id is None
    assert persisted_session.active_coding_run_locked_at is None

    rows = (
        await db_session.execute(
            select(PublishedAppCodingRunEvent)
            .where(PublishedAppCodingRunEvent.run_id == run.id)
            .order_by(PublishedAppCodingRunEvent.seq.asc())
        )
    ).scalars().all()
    terminal_rows = [row for row in rows if str(row.event or "") in {"run.failed", "run.completed", "run.cancelled", "run.paused"}]
    assert len(terminal_rows) == 1
    assert int(terminal_rows[0].seq or 0) == 3


@pytest.mark.asyncio
async def test_stream_terminal_snapshot_reconciles_stale_preview_lock(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.completed,
    )
    run.completed_at = datetime.now(timezone.utc)

    draft_session = PublishedAppDraftDevSession(
        published_app_id=UUID(app_id),
        user_id=user.id,
        revision_id=UUID(draft_revision_id),
        status=PublishedAppDraftDevSessionStatus.running,
        idle_timeout_seconds=180,
        sandbox_id="sandbox-test",
        last_activity_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        active_coding_run_id=run.id,
        active_coding_run_locked_at=datetime.now(timezone.utc),
    )
    db_session.add(draft_session)
    await db_session.commit()

    async with client.stream(
        "GET",
        f"/admin/apps/{app_id}/coding-agent/runs/{run.id}/stream?from_seq=1&replay=true",
        headers=headers,
    ) as stream_resp:
        assert stream_resp.status_code == 200
        body = (await stream_resp.aread()).decode("utf-8")
        assert "\"event\": \"run.completed\"" in body

    await db_session.refresh(draft_session)
    assert draft_session.active_coding_run_id is None
    assert draft_session.active_coding_run_locked_at is None


@pytest.mark.asyncio
async def test_orchestrator_prefers_async_bind_for_detached_runner(db_session):
    bind = PublishedAppCodingRunOrchestrator._resolve_session_factory_bind(db_session)
    assert isinstance(bind, AsyncEngine)


@pytest.mark.asyncio
async def test_stream_route_prefers_async_bind_over_sync_get_bind(db_session):
    bind = _resolve_detached_async_bind(db_session)
    assert isinstance(bind, AsyncEngine)
