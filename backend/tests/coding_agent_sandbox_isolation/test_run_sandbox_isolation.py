from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_agent_engines.base import EngineStreamEvent
from app.services.published_app_coding_agent_engines.opencode_engine import OpenCodePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Sandbox Isolation App",
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
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]
    return app_id, draft_revision_id


@pytest.mark.asyncio
async def test_stream_fails_closed_when_run_has_no_preview_sandbox_context(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={"input": "test"},
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=None,
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    async def _fake_recover(self, *, run, app):
        return None, "Preview sandbox session is required before execution."

    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_recover_or_bootstrap_run_sandbox_context",
        _fake_recover,
    )

    async with client.stream(
        "GET",
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run.id}/stream",
        headers=headers,
    ) as stream_resp:
        assert stream_resp.status_code == 200
        body = (await stream_resp.aread()).decode("utf-8")
        assert "CODING_AGENT_SANDBOX_REQUIRED" in body

    # Monitor terminalization happens in a detached DB session; allow a short settle window.
    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    for _ in range(20):
        await db_session.refresh(persisted)
        if persisted.status == RunStatus.failed:
            break
        await asyncio.sleep(0.05)
    assert persisted.status == RunStatus.failed


@pytest.mark.asyncio
async def test_stream_reuses_existing_preview_sandbox_without_stage_bootstrap(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={
            "input": "test",
            "context": {
                "preview_sandbox_id": "preview-sandbox-1",
                "preview_workspace_stage_path": "/workspace/.talmudpedia/stage/run/workspace",
            },
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(draft_revision_id),
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    async def _fail_stage_prepare(self, *, run, runtime_service, sandbox_id):
        raise AssertionError("stream should not prepare a stage workspace when one is already present in run context")

    async def _fake_stream(self, ctx):
        yield EngineStreamEvent(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "Warm sandbox response"},
            diagnostics=[],
        )
        yield EngineStreamEvent(
            event="run.completed",
            stage="run",
            payload={},
            diagnostics=[],
        )

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_prepare_run_stage_workspace_context", _fail_stage_prepare)
    monkeypatch.setattr(OpenCodePublishedAppCodingAgentEngine, "stream", _fake_stream)

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]
    assert events[-1]["event"] == "run.completed"
    run_context = service._run_context(run)
    assert run_context.get("opencode_workspace_path") == "/workspace/.talmudpedia/stage/run/workspace"


@pytest.mark.asyncio
async def test_completed_run_does_not_emit_checkpoint_events(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={
            "input": "test",
            "context": {
                "preview_sandbox_id": "preview-sandbox-2",
                "preview_workspace_stage_path": "/workspace/.talmudpedia/stage/run/workspace",
            },
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(draft_revision_id),
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    async def _fake_stream(self, ctx):
        yield EngineStreamEvent(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "done"},
            diagnostics=[],
        )
        # No tool.started/tool.completed write hints, only terminal completion.
        yield EngineStreamEvent(
            event="run.completed",
            stage="run",
            payload={},
            diagnostics=[],
        )

    monkeypatch.setattr(OpenCodePublishedAppCodingAgentEngine, "stream", _fake_stream)

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]
    event_names = [event.get("event") for event in events]
    assert "checkpoint.created" not in event_names
    assert event_names[-1] == "run.completed"
