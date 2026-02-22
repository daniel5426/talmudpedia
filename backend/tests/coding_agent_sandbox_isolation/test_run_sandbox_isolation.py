from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_agent_engines.base import EngineStreamEvent
from app.services.published_app_coding_agent_engines.native_engine import NativePublishedAppCodingAgentEngine
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
        execution_engine="native",
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
        f"/admin/apps/{app_id}/coding-agent/runs/{run.id}/stream",
        headers=headers,
    ) as stream_resp:
        assert stream_resp.status_code == 200
        body = (await stream_resp.aread()).decode("utf-8")
        assert "CODING_AGENT_SANDBOX_REQUIRED" in body

    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.failed


@pytest.mark.asyncio
async def test_stream_reuses_existing_preview_sandbox_without_bootstrap(client, db_session, monkeypatch):
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
        execution_engine="native",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    async def _fail_if_bootstrap(self, *, run, app):
        raise AssertionError("stream should not bootstrap a second sandbox when preview_sandbox_id already exists")

    async def _fake_stream(self, ctx):
        yield EngineStreamEvent(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "Warm sandbox response"},
            diagnostics=[],
        )
        ctx.run.status = RunStatus.completed
        ctx.run.output_result = {"state": {"last_agent_output": "Warm sandbox response"}}
        ctx.run.completed_at = datetime.now(timezone.utc)
        await self._executor.db.commit()
        if False:  # pragma: no cover
            yield

    async def _skip_auto_apply(self, run):
        return None

    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_recover_or_bootstrap_run_sandbox_context",
        _fail_if_bootstrap,
    )
    monkeypatch.setattr(NativePublishedAppCodingAgentEngine, "stream", _fake_stream)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "auto_apply_and_checkpoint", _skip_auto_apply)

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]
    assert events[-1]["event"] == "run.completed"
