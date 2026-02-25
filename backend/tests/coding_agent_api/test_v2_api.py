from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor, _MonitorState
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_monitor_tasks():
    yield
    async with PublishedAppCodingRunMonitor._monitors_lock:
        states = list(PublishedAppCodingRunMonitor._monitors.values())
        PublishedAppCodingRunMonitor._monitors.clear()
    for state in states:
        task = getattr(state, "task", None)
        if task is None or task.done():
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": f"Coding Agent V2 App {uuid4().hex[:6]}",
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


def _install_fake_create_run(monkeypatch):
    async def _fake_create_run(
        self,
        *,
        app,
        base_revision,
        actor_id,
        user_prompt,
        messages=None,
        requested_scopes=None,
        requested_model_id=None,
        execution_engine=None,
        chat_session_id=None,
    ):
        _ = messages, requested_scopes, requested_model_id, execution_engine
        run = AgentRun(
            tenant_id=app.tenant_id,
            agent_id=app.agent_id,
            user_id=actor_id,
            initiator_user_id=actor_id,
            status=RunStatus.queued,
            input_params={
                "input": user_prompt,
                "context": {
                    "chat_session_id": str(chat_session_id) if chat_session_id else None,
                    "preview_sandbox_id": "sandbox-test",
                    "preview_sandbox_status": "running",
                    "preview_workspace_stage_path": "/workspace",
                },
            },
            surface=CODING_AGENT_SURFACE,
            published_app_id=app.id,
            base_revision_id=base_revision.id,
            execution_engine="opencode",
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "create_run", _fake_create_run)


@pytest.mark.asyncio
async def test_v2_submit_prompt_started_then_run_active(client, db_session, monkeypatch):
    _install_fake_create_run(monkeypatch)

    async def _no_monitor(self, *, app_id, run_id):
        _ = self, app_id, run_id
        return SimpleNamespace(task=None)

    monkeypatch.setattr(PublishedAppCodingRunMonitor, "ensure_monitor", _no_monitor)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    first_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "Add a header"},
    )
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    assert first_payload["submission_status"] == "started"
    run_payload = first_payload["run"]
    assert run_payload["execution_engine"] == "opencode"
    chat_session_id = run_payload["chat_session_id"]
    assert chat_session_id

    second_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={
            "input": "Now add a footer",
            "chat_session_id": chat_session_id,
        },
    )
    assert second_resp.status_code == 409
    second_payload = second_resp.json().get("detail") or {}
    assert second_payload["code"] == "CODING_AGENT_RUN_ACTIVE"
    assert second_payload["active_run_id"] == run_payload["run_id"]
    assert second_payload["chat_session_id"] == chat_session_id


@pytest.mark.asyncio
async def test_v2_stream_emits_assistant_delta_per_chunk_and_old_route_is_404(client, db_session, monkeypatch):
    class _FakeEngine:
        async def stream(self, ctx):
            _ = ctx
            yield SimpleNamespace(event="assistant.delta", stage="assistant", payload={"content": "A"}, diagnostics=[])
            yield SimpleNamespace(event="assistant.delta", stage="assistant", payload={"content": "B"}, diagnostics=[])
            yield SimpleNamespace(event="run.completed", stage="run", payload={"status": "completed"}, diagnostics=[])

        async def cancel(self, run):
            _ = run
            return SimpleNamespace(confirmed=True, diagnostics=[])

    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_resolve_engine_for_run",
        lambda self, run: _FakeEngine(),
    )

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
            "input": "Stream now",
            "context": {
                "chat_session_id": str(uuid4()),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
                "preview_workspace_stage_path": "/workspace",
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

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=SimpleNamespace(id=UUID(app_id)), run=run)]
    assistant_chunks = [event for event in events if event.get("event") == "assistant.delta"]
    assert len(assistant_chunks) == 2
    assert assistant_chunks[0]["payload"]["content"] == "A"
    assert assistant_chunks[1]["payload"]["content"] == "B"

    old_route_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={"input": "legacy route"},
    )
    assert old_route_resp.status_code == 404

    removed_queue_list = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{uuid4()}/queue",
        headers=headers,
    )
    assert removed_queue_list.status_code == 404
    removed_queue_delete = await client.delete(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{uuid4()}/queue/{uuid4()}",
        headers=headers,
    )
    assert removed_queue_delete.status_code == 404


@pytest.mark.asyncio
async def test_v2_stream_missing_terminal_does_not_force_fail_by_default(db_session, monkeypatch):
    class _FakeEngine:
        async def stream(self, ctx):
            _ = ctx
            yield SimpleNamespace(event="assistant.delta", stage="assistant", payload={"content": "A"}, diagnostics=[])

        async def cancel(self, run):
            _ = run
            return SimpleNamespace(confirmed=True, diagnostics=[])

    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_resolve_engine_for_run",
        lambda self, run: _FakeEngine(),
    )

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    _ = org_unit
    app = SimpleNamespace(id=uuid4(), tenant_id=tenant.id)
    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={
            "input": "Stream now",
            "context": {
                "chat_session_id": str(uuid4()),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
                "preview_workspace_stage_path": "/workspace",
            },
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=uuid4(),
        base_revision_id=uuid4(),
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]
    assert any(event.get("event") == "assistant.delta" for event in events)
    assert not any(event.get("event") == "run.failed" for event in events)

    refreshed = await db_session.get(AgentRun, run.id)
    assert refreshed is not None
    refreshed_status = refreshed.status.value if hasattr(refreshed.status, "value") else str(refreshed.status)
    assert refreshed_status != RunStatus.failed.value


@pytest.mark.asyncio
async def test_v2_answer_question_endpoint(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={
            "input": "Need answer",
            "context": {
                "chat_session_id": str(uuid4()),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
            },
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(draft_revision_id),
        execution_engine="opencode",
        engine_run_ref="ses_test_1",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    async def _fake_answer_question(self, *, run, question_id, answers):
        _ = self
        assert str(run.id) == str(run_id)
        assert question_id == "que_1"
        assert answers == [["A"]]
        return run

    run_id = run.id
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "answer_question", _fake_answer_question)
    monkeypatch.setattr(
        PublishedAppCodingRunMonitor,
        "ensure_monitor",
        lambda self, *, app_id, run_id: asyncio.sleep(0, result=SimpleNamespace(task=None)),
    )

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run_id}/answer-question",
        headers=headers,
        json={"question_id": "que_1", "answers": [["A"]]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == str(run_id)
    assert payload["status"] == "running"


@pytest.mark.asyncio
async def test_v2_cancel_marks_cancelled(client, db_session, monkeypatch):
    _install_fake_create_run(monkeypatch)

    async def _hanging_stream(self, *, app, run, resume_payload=None):
        _ = app, resume_payload
        while True:
            await asyncio.sleep(0.05)
            refreshed = await self.db.get(AgentRun, run.id)
            if refreshed is not None:
                status = refreshed.status.value if hasattr(refreshed.status, "value") else str(refreshed.status)
                if status == RunStatus.cancelled.value:
                    yield {
                        "event": "run.cancelled",
                        "stage": "run",
                        "payload": self.serialize_run(refreshed),
                        "diagnostics": [],
                    }
                    return
            yield {
                "event": "plan.updated",
                "stage": "plan",
                "payload": {"summary": "working"},
                "diagnostics": [],
            }

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "stream_run_events", _hanging_stream)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    first_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "Long run"},
    )
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    run_id = first_payload["run"]["run_id"]
    chat_session_id = first_payload["run"]["chat_session_id"]

    cancel_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run_id}/cancel",
        headers=headers,
        json={},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    runs = (
        await db_session.execute(
            select(AgentRun)
            .where(AgentRun.published_app_id == UUID(app_id), AgentRun.surface == CODING_AGENT_SURFACE)
            .order_by(AgentRun.created_at.asc())
        )
    ).scalars().all()
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_v2_cancel_closes_stream_when_runtime_keeps_non_terminal_events(client, db_session, monkeypatch):
    _install_fake_create_run(monkeypatch)

    async def _non_terminal_stream(self, *, app, run, resume_payload=None):
        _ = app, run, resume_payload
        while True:
            await asyncio.sleep(0.05)
            yield {
                "event": "plan.updated",
                "stage": "plan",
                "payload": {"summary": "still working"},
                "diagnostics": [],
            }

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "stream_run_events", _non_terminal_stream)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    first_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "Long run"},
    )
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    run_id = UUID(first_payload["run"]["run_id"])

    monitor = PublishedAppCodingRunMonitor(db_session)
    observed_events: list[str] = []

    async def _consume_stream() -> None:
        async for envelope in monitor.stream_events(app_id=UUID(app_id), run_id=run_id):
            observed_events.append(str(envelope.get("event") or ""))
            if observed_events[-1] in {"run.completed", "run.failed", "run.cancelled", "run.paused"}:
                break

    consumer_task = asyncio.create_task(_consume_stream())
    await asyncio.sleep(0.15)

    cancel_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run_id}/cancel",
        headers=headers,
        json={},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    await asyncio.wait_for(consumer_task, timeout=3.0)
    assert "run.cancelled" in observed_events


@pytest.mark.asyncio
async def test_v2_stream_replays_only_unseen_events_from_from_seq(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={
            "input": "Replay stream",
            "context": {
                "chat_session_id": str(uuid4()),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
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

    idle_task = asyncio.create_task(asyncio.Event().wait())
    state = _MonitorState(run_id=str(run.id), task=idle_task)
    state.event_backlog.extend(
        [
            {
                "event": "run.accepted",
                "run_id": str(run.id),
                "app_id": app_id,
                "seq": 1,
                "ts": "2026-02-25T19:00:00Z",
                "stage": "run",
                "payload": {"status": "queued"},
                "diagnostics": [],
            },
            {
                "event": "assistant.delta",
                "run_id": str(run.id),
                "app_id": app_id,
                "seq": 2,
                "ts": "2026-02-25T19:00:01Z",
                "stage": "assistant",
                "payload": {"content": "hello"},
                "diagnostics": [],
            },
            {
                "event": "assistant.delta",
                "run_id": str(run.id),
                "app_id": app_id,
                "seq": 3,
                "ts": "2026-02-25T19:00:02Z",
                "stage": "assistant",
                "payload": {"content": " world"},
                "diagnostics": [],
            },
            {
                "event": "run.completed",
                "run_id": str(run.id),
                "app_id": app_id,
                "seq": 4,
                "ts": "2026-02-25T19:00:03Z",
                "stage": "run",
                "payload": {"status": "completed"},
                "diagnostics": [],
            },
        ]
    )
    async with PublishedAppCodingRunMonitor._monitors_lock:
        PublishedAppCodingRunMonitor._monitors[str(run.id)] = state

    response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run.id}/stream?from_seq=2",
        headers=headers,
    )
    assert response.status_code == 200
    events: list[dict[str, object]] = []
    for frame in response.text.split("\n\n"):
        raw = frame.strip()
        if not raw.startswith("data: "):
            continue
        events.append(json.loads(raw[6:]))
    seqs = [int(event.get("seq") or 0) for event in events]
    assert seqs == [3, 4]


@pytest.mark.asyncio
async def test_v2_stream_replay_gap_returns_409_with_next_seq(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={
            "input": "Replay gap",
            "context": {
                "chat_session_id": str(uuid4()),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
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

    idle_task = asyncio.create_task(asyncio.Event().wait())
    state = _MonitorState(run_id=str(run.id), task=idle_task)
    state.event_backlog.extend(
        [
            {
                "event": "assistant.delta",
                "run_id": str(run.id),
                "app_id": app_id,
                "seq": 10,
                "ts": "2026-02-25T19:00:10Z",
                "stage": "assistant",
                "payload": {"content": "recent"},
                "diagnostics": [],
            },
        ]
    )
    async with PublishedAppCodingRunMonitor._monitors_lock:
        PublishedAppCodingRunMonitor._monitors[str(run.id)] = state

    response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run.id}/stream?from_seq=2",
        headers=headers,
    )
    assert response.status_code == 409
    payload = response.json()
    detail = payload.get("detail") or {}
    assert detail.get("code") == "CODING_AGENT_STREAM_REPLAY_GAP"
    assert int(detail.get("next_replay_seq") or 0) == 10
