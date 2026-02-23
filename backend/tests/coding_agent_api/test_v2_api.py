from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedAppCodingPromptQueue, PublishedAppCodingPromptQueueStatus
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor
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
async def test_v2_submit_prompt_started_then_queued(client, db_session, monkeypatch):
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
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["submission_status"] == "queued"
    assert second_payload["active_run_id"] == run_payload["run_id"]
    assert second_payload["queue_item"]["chat_session_id"] == chat_session_id


@pytest.mark.asyncio
async def test_v2_monitor_dispatches_next_queued_without_stream(client, db_session, monkeypatch):
    _install_fake_create_run(monkeypatch)

    started = asyncio.Event()
    release_terminal = asyncio.Event()
    terminal_run_id: str | None = None

    async def _fake_stream_run_events(self, *, app, run, resume_payload=None):
        _ = app, resume_payload
        nonlocal terminal_run_id
        if terminal_run_id is None:
            terminal_run_id = str(run.id)
            started.set()
            yield {
                "event": "run.accepted",
                "stage": "run",
                "payload": {"status": "queued"},
                "diagnostics": [],
            }
            await release_terminal.wait()
            run.status = RunStatus.completed
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            yield {
                "event": "run.completed",
                "stage": "run",
                "payload": self.serialize_run(run),
                "diagnostics": [],
            }
            return

        run.status = RunStatus.completed
        run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        yield {
            "event": "run.completed",
            "stage": "run",
            "payload": self.serialize_run(run),
            "diagnostics": [],
        }

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "stream_run_events", _fake_stream_run_events)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    first_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "Run one"},
    )
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    assert first_payload["submission_status"] == "started"
    chat_session_id = first_payload["run"]["chat_session_id"]
    assert chat_session_id

    await asyncio.wait_for(started.wait(), timeout=2.0)

    queued_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "Run two", "chat_session_id": chat_session_id},
    )
    assert queued_resp.status_code == 200
    queued_payload = queued_resp.json()
    assert queued_payload["submission_status"] == "queued"

    release_terminal.set()

    for _ in range(40):
        await asyncio.sleep(0.05)
        runs = (
            await db_session.execute(
                select(AgentRun)
                .where(AgentRun.published_app_id == UUID(app_id), AgentRun.surface == CODING_AGENT_SURFACE)
                .order_by(AgentRun.created_at.asc())
            )
        ).scalars().all()
        if len(runs) >= 2:
            break
    else:
        raise AssertionError("Expected queued prompt dispatch to start a second run")

    queue_items = (
        await db_session.execute(
            select(PublishedAppCodingPromptQueue).where(PublishedAppCodingPromptQueue.chat_session_id == UUID(chat_session_id))
        )
    ).scalars().all()
    assert queue_items
    assert any(item.status == PublishedAppCodingPromptQueueStatus.completed for item in queue_items)


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


@pytest.mark.asyncio
async def test_v2_cancel_marks_cancelled_and_dispatches_next(client, db_session, monkeypatch):
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

    queued_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "Queued follow-up", "chat_session_id": chat_session_id},
    )
    assert queued_resp.status_code == 200
    assert queued_resp.json()["submission_status"] == "queued"

    cancel_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/runs/{run_id}/cancel",
        headers=headers,
        json={},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    for _ in range(40):
        await asyncio.sleep(0.05)
        runs = (
            await db_session.execute(
                select(AgentRun)
                .where(AgentRun.published_app_id == UUID(app_id), AgentRun.surface == CODING_AGENT_SURFACE)
                .order_by(AgentRun.created_at.asc())
            )
        ).scalars().all()
        if len(runs) >= 2:
            break
    else:
        raise AssertionError("Expected queued prompt to start after cancel")
