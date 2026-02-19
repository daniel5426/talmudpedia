from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_sandbox_service import PublishedAppCodingRunSandboxService
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
async def test_opencode_run_rejected_when_sandbox_required_without_controller(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    monkeypatch.setenv("APPS_CODING_AGENT_SANDBOX_REQUIRED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("APPS_DRAFT_DEV_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, uuid4()

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use OpenCode",
            "base_revision_id": draft_revision_id,
            "engine": "opencode",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CODING_AGENT_SANDBOX_REQUIRED"
    assert detail["field"] == "engine"


@pytest.mark.asyncio
async def test_stream_fails_closed_when_run_has_no_sandbox_context(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

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
        return None, "Run sandbox session is required before execution."

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
async def test_run_sandbox_session_uses_controller_workspace_path(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    app = await db_session.get(PublishedApp, UUID(app_id))
    revision = await db_session.get(PublishedAppRevision, UUID(draft_revision_id))
    assert app is not None
    assert revision is not None

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={"input": "test"},
        surface=CODING_AGENT_SURFACE,
        published_app_id=app.id,
        base_revision_id=revision.id,
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = PublishedAppCodingRunSandboxService(db_session)
    workspace_root = "/tmp/talmudpedia-draft-dev/sandbox-run-123"

    async def _fake_start_session(**kwargs):
        return {
            "sandbox_id": "sandbox-run-123",
            "preview_url": "http://127.0.0.1:5173/sandbox/sandbox-run-123",
            "status": "running",
            "workspace_path": workspace_root,
        }

    async def _fake_resolve_local_workspace_path(*, sandbox_id: str):
        return None

    monkeypatch.setattr(service.client, "start_session", _fake_start_session)
    monkeypatch.setattr(service.client, "resolve_local_workspace_path", _fake_resolve_local_workspace_path)

    session = await service.ensure_session(
        run=run,
        app=app,
        revision=revision,
        actor_id=user.id,
    )

    assert session.sandbox_id == "sandbox-run-123"
    assert session.workspace_path == workspace_root
