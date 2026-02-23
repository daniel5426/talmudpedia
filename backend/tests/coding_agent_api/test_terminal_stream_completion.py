import asyncio
from uuid import UUID

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_agent_engines.base import EngineStreamEvent
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent Terminal Stream Test App",
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
        input_params={
            "input": "test terminal stream completion",
            "context": {
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
                "preview_workspace_stage_path": "/workspace",
            },
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
        execution_engine="native",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


class _TerminalThenHungEngine:
    def __init__(self, *, terminal_event: str, error_message: str | None = None) -> None:
        self._terminal_event = terminal_event
        self._error_message = error_message

    async def stream(self, ctx):
        yield EngineStreamEvent(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "Done.\n"},
            diagnostics=None,
        )
        if self._terminal_event == "run.failed":
            yield EngineStreamEvent(
                event="run.failed",
                stage="run",
                payload={"error": self._error_message or "synthetic terminal failure"},
                diagnostics=[{"message": self._error_message or "synthetic terminal failure"}],
            )
        else:
            yield EngineStreamEvent(
                event="run.completed",
                stage="run",
                payload={"status": "completed"},
                diagnostics=None,
            )

        while True:
            await asyncio.sleep(60)


class _NonTerminalThenStopsEngine:
    async def stream(self, ctx):
        yield EngineStreamEvent(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "partial output"},
            diagnostics=None,
        )
        return


class _DelayedTerminalEngine:
    async def stream(self, ctx):
        await asyncio.sleep(2.2)
        yield EngineStreamEvent(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "Delayed output"},
            diagnostics=None,
        )
        yield EngineStreamEvent(
            event="run.completed",
            stage="run",
            payload={"status": "completed"},
            diagnostics=None,
        )


class _BurstAssistantDeltaEngine:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def stream(self, ctx):
        for chunk in self._chunks:
            yield EngineStreamEvent(
                event="assistant.delta",
                stage="assistant",
                payload={"content": chunk},
                diagnostics=None,
            )
        yield EngineStreamEvent(
            event="run.completed",
            stage="run",
            payload={"status": "completed"},
            diagnostics=None,
        )


async def _collect_stream_events(service: PublishedAppCodingAgentRuntimeService, app: PublishedApp, run: AgentRun):
    return [event async for event in service.stream_run_events(app=app, run=run)]


def test_execution_engine_normalization_accepts_enum_like_opencode_value():
    normalized = PublishedAppCodingAgentRuntimeService._normalize_execution_engine("ExecutionEngine.OPENCODE")
    assert normalized == "opencode"


@pytest.mark.asyncio
async def test_runtime_stream_completes_after_engine_terminal_event_even_if_engine_hangs(client, db_session, monkeypatch):
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
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    engine = _TerminalThenHungEngine(terminal_event="run.completed")
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_engine_for_run", lambda self, run: engine)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = await asyncio.wait_for(_collect_stream_events(service, app, run), timeout=2.0)

    assert events[-1]["event"] == "run.completed"
    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.completed


@pytest.mark.asyncio
async def test_runtime_stream_fails_after_engine_failed_event_even_if_engine_hangs(client, db_session, monkeypatch):
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
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    error_message = "synthetic terminal failure"
    engine = _TerminalThenHungEngine(terminal_event="run.failed", error_message=error_message)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_engine_for_run", lambda self, run: engine)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = await asyncio.wait_for(_collect_stream_events(service, app, run), timeout=2.0)

    assert events[-1]["event"] == "run.failed"
    assert error_message in str(events[-1].get("diagnostics", [{}])[0].get("message", ""))
    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.failed
    assert error_message in str(persisted.error_message)


@pytest.mark.asyncio
async def test_runtime_stream_fail_closes_and_persists_failed_status_when_engine_ends_without_terminal_event(
    client, db_session, monkeypatch
):
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
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    engine = _NonTerminalThenStopsEngine()
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_engine_for_run", lambda self, run: engine)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = await asyncio.wait_for(_collect_stream_events(service, app, run), timeout=2.0)

    assert events[-1]["event"] == "run.failed"
    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.failed
    assert str(persisted.error_message or "").strip() != ""
    assert persisted.completed_at is not None


@pytest.mark.asyncio
async def test_runtime_stream_polling_does_not_cancel_slow_provider_iteration(client, db_session, monkeypatch):
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
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    engine = _DelayedTerminalEngine()
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_engine_for_run", lambda self, run: engine)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = await asyncio.wait_for(_collect_stream_events(service, app, run), timeout=8.0)

    assert events[-1]["event"] == "run.completed"
    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.completed


@pytest.mark.asyncio
async def test_runtime_stream_coalesces_assistant_delta_bursts(client, db_session, monkeypatch):
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
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    monkeypatch.setenv("APPS_CODING_AGENT_STREAM_ASSISTANT_DELTA_FLUSH_CHARS", "3")
    monkeypatch.setenv("APPS_CODING_AGENT_STREAM_ASSISTANT_DELTA_FLUSH_MS", "2000")
    engine = _BurstAssistantDeltaEngine(["A", "B", "C", "D", "E", "F", "G"])
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_engine_for_run", lambda self, run: engine)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = await asyncio.wait_for(_collect_stream_events(service, app, run), timeout=4.0)

    assistant_chunks = [str(item.get("payload", {}).get("content") or "") for item in events if item.get("event") == "assistant.delta"]
    assert "".join(assistant_chunks) == "ABCDEFG"
    assert len(assistant_chunks) <= 3
    assert events[-1]["event"] == "run.completed"
