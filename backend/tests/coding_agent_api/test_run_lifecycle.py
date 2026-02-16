from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent API App",
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


async def _insert_coding_agent_run(
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
        input_params={"input": "test"},
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_coding_agent_create_run_list_and_get(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    async def _fake_create_run(self, *, app, base_revision, actor_id, user_prompt, requested_scopes=None):
        run = AgentRun(
            tenant_id=app.tenant_id,
            agent_id=app.agent_id,
            user_id=actor_id,
            initiator_user_id=actor_id,
            status=RunStatus.queued,
            input_params={"input": user_prompt},
            surface=CODING_AGENT_SURFACE,
            published_app_id=app.id,
            base_revision_id=base_revision.id,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "create_run", _fake_create_run)

    create_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={"input": "Update the hero title", "base_revision_id": draft_revision_id},
    )
    assert create_resp.status_code == 200
    create_payload = create_resp.json()
    assert create_payload["status"] == "queued"
    assert create_payload["published_app_id"] == app_id
    assert create_payload["base_revision_id"] == draft_revision_id

    run_id = create_payload["run_id"]
    list_resp = await client.get(f"/admin/apps/{app_id}/coding-agent/runs?limit=10", headers=headers)
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert any(item["run_id"] == run_id for item in list_payload)

    get_resp = await client.get(f"/admin/apps/{app_id}/coding-agent/runs/{run_id}", headers=headers)
    assert get_resp.status_code == 200
    get_payload = get_resp.json()
    assert get_payload["run_id"] == run_id
    assert get_payload["surface"] == CODING_AGENT_SURFACE


@pytest.mark.asyncio
async def test_coding_agent_create_run_detects_stale_revision(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    conflict_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={"input": "Any update", "base_revision_id": str(uuid4())},
    )
    assert conflict_resp.status_code == 409
    detail = conflict_resp.json()["detail"]
    assert detail["code"] == "REVISION_CONFLICT"
    assert detail["latest_revision_id"]


@pytest.mark.asyncio
async def test_coding_agent_stream_returns_sse_envelopes(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    stream_called = False

    async def _fake_stream(self, *, app, run, resume_payload=None):
        nonlocal stream_called
        stream_called = True
        now = datetime.now(timezone.utc).isoformat()
        yield {
            "event": "run.accepted",
            "run_id": str(run.id),
            "app_id": str(app.id),
            "seq": 1,
            "ts": now,
            "stage": "run",
            "payload": {"status": "queued"},
            "diagnostics": [],
        }
        yield {
            "event": "run.completed",
            "run_id": str(run.id),
            "app_id": str(app.id),
            "seq": 2,
            "ts": now,
            "stage": "run",
            "payload": {"status": "completed"},
            "diagnostics": [],
        }

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "stream_run_events", _fake_stream)

    async with client.stream(
        "GET",
        f"/admin/apps/{app_id}/coding-agent/runs/{run.id}/stream",
        headers=headers,
    ) as stream_resp:
        assert stream_resp.status_code == 200
        assert stream_resp.headers["content-type"].startswith("text/event-stream")
        await stream_resp.aread()

    assert stream_called is True


@pytest.mark.asyncio
async def test_coding_agent_resume_and_cancel(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    paused_run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.paused,
    )
    running_run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.running,
    )

    resume_calls: list[tuple[str, dict, bool]] = []

    async def _fake_resume(self, run_id, payload, background=False):
        resume_calls.append((str(run_id), payload, background))

    monkeypatch.setattr(AgentExecutorService, "resume_run", _fake_resume)

    resume_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{paused_run.id}/resume",
        headers=headers,
        json={"payload": {"decision": "continue"}},
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["run_id"] == str(paused_run.id)
    assert resume_calls == [(str(paused_run.id), {"decision": "continue"}, False)]

    bad_resume_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{running_run.id}/resume",
        headers=headers,
        json={"payload": {}},
    )
    assert bad_resume_resp.status_code == 409

    cancel_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{running_run.id}/cancel",
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    cancel_payload = cancel_resp.json()
    assert cancel_payload["run_id"] == str(running_run.id)
    assert cancel_payload["status"] == "cancelled"
