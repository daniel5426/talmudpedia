from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingChatSession,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent

pytestmark = pytest.mark.skip(
    reason="Legacy run-based coding-agent v2 API coverage was replaced by session-native chat-session tests on 2026-04-17."
)


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


async def _create_app_and_draft_revision(db_session, *, organization_id: UUID, user_id: UUID, agent_id: UUID) -> tuple[str, str]:
    app = PublishedApp(
        organization_id=organization_id,
        agent_id=agent_id,
        name=f"Coding Agent V2 App {uuid4().hex[:6]}",
        slug=f"coding-agent-v2-{uuid4().hex[:10]}",
        status=PublishedAppStatus.draft,
        visibility=PublishedAppVisibility.public,
        auth_enabled=True,
        auth_providers=["password"],
        auth_template_key="auth-classic",
        template_key="classic-chat",
        created_by=user_id,
    )
    db_session.add(app)
    await db_session.flush()

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key="classic-chat",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default function App() { return null; }\n"},
        manifest_json={},
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        origin_kind="app_init",
        created_by=user_id,
    )
    db_session.add(revision)
    await db_session.flush()

    app.current_draft_revision_id = revision.id
    await db_session.commit()
    return str(app.id), str(revision.id)


async def _create_chat_session(db_session, *, app_id: UUID, user_id: UUID, title: str = "Test Session") -> PublishedAppCodingChatSession:
    session = PublishedAppCodingChatSession(
        published_app_id=app_id,
        user_id=user_id,
        title=title,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


def test_opencode_runs_skip_model_registry_resolution_for_context_only_model_refs():
    assert AgentExecutorService._should_skip_model_registry_resolution(
        {"execution_engine": "opencode", "requested_model_id": "opencode/gpt-5"}
    )


def test_non_opencode_runs_keep_model_registry_resolution_enabled():
    assert not AgentExecutorService._should_skip_model_registry_resolution(
        {"execution_engine": "langgraph", "requested_model_id": "opencode/gpt-5"}
    )


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
            organization_id=app.organization_id,
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
    app_id, _ = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )

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
async def test_create_run_persists_opencode_session_on_first_chat_turn(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_INCLUDE_AGENT_CONTRACT", "0")
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    app = await db_session.get(PublishedApp, UUID(app_id))
    draft_revision = await db_session.get(PublishedAppRevision, UUID(draft_revision_id))
    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=user.id,
        title="Test Session",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    service = PublishedAppCodingAgentRuntimeService(db_session)

    async def _fake_start_run(profile_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None):
        _ = profile_id, background, mode, requested_scopes
        run = AgentRun(
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        return run.id

    async def _fake_profile(*, organization_id, actor_user_id):
        _ = organization_id, actor_user_id
        return SimpleNamespace(id=agent.id), True

    async def _fake_sandbox_context(*, run, app, base_revision, actor_id):
        _ = run, app, base_revision, actor_id
        return {
            "preview_sandbox_id": "sandbox-a",
            "opencode_sandbox_id": "sandbox-a",
            "opencode_workspace_path": "/workspace/live",
            "preview_workspace_live_path": "/workspace/live",
            "preview_sandbox_status": "running",
            "stage_prepare_ms": 0,
        }

    session_creates: list[str] = []

    async def _fake_create_session(*, run_id, app_id, sandbox_id, workspace_path, model_id, selected_agent_contract=None):
        _ = run_id, app_id, sandbox_id, workspace_path, model_id, selected_agent_contract
        session_creates.append("sess-1")
        return "sess-1"

    monkeypatch.setattr(service.executor, "start_run", _fake_start_run)
    monkeypatch.setattr(service, "_resolve_cached_coding_agent_profile", _fake_profile)
    monkeypatch.setattr(service, "_ensure_run_sandbox_context", _fake_sandbox_context)
    monkeypatch.setattr(service._opencode_client, "ensure_healthy", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(service._opencode_client, "create_session", _fake_create_session)

    run = await service.create_run(
        app=app,
        base_revision=draft_revision,
        actor_id=user.id,
        user_prompt="hello",
        messages=[{"role": "user", "content": "hello"}],
        chat_session_id=session.id,
    )

    await db_session.refresh(session)
    assert session.opencode_session_id == "sess-1"
    assert session.opencode_sandbox_id == "sandbox-a"
    assert session.opencode_workspace_path == "/workspace/live"
    assert run.engine_run_ref is None
    assert run.input_params["context"]["opencode_session_id"] == "sess-1"
    assert session_creates == ["sess-1"]


@pytest.mark.asyncio
async def test_create_run_reuses_persisted_opencode_session_for_followup_turn(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_INCLUDE_AGENT_CONTRACT", "0")
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    app = await db_session.get(PublishedApp, UUID(app_id))
    draft_revision = await db_session.get(PublishedAppRevision, UUID(draft_revision_id))
    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=user.id,
        title="Test Session",
        opencode_session_id="sess-persisted",
        opencode_sandbox_id="sandbox-a",
        opencode_workspace_path="/workspace/live",
        opencode_session_opened_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    service = PublishedAppCodingAgentRuntimeService(db_session)

    async def _fake_start_run(profile_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None):
        _ = profile_id, background, mode, requested_scopes
        run = AgentRun(
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        return run.id

    async def _fake_profile(*, organization_id, actor_user_id):
        _ = organization_id, actor_user_id
        return SimpleNamespace(id=agent.id), True

    async def _fake_sandbox_context(*, run, app, base_revision, actor_id):
        _ = run, app, base_revision, actor_id
        return {
            "preview_sandbox_id": "sandbox-a",
            "opencode_sandbox_id": "sandbox-a",
            "opencode_workspace_path": "/workspace/live",
            "preview_workspace_live_path": "/workspace/live",
            "preview_sandbox_status": "running",
            "stage_prepare_ms": 0,
        }

    create_calls: list[str] = []

    async def _fake_create_session(**kwargs):
        _ = kwargs
        create_calls.append("called")
        return "unexpected"

    monkeypatch.setattr(service.executor, "start_run", _fake_start_run)
    monkeypatch.setattr(service, "_resolve_cached_coding_agent_profile", _fake_profile)
    monkeypatch.setattr(service, "_ensure_run_sandbox_context", _fake_sandbox_context)
    monkeypatch.setattr(service._opencode_client, "ensure_healthy", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(service._opencode_client, "create_session", _fake_create_session)

    run = await service.create_run(
        app=app,
        base_revision=draft_revision,
        actor_id=user.id,
        user_prompt="follow up",
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "follow up"},
        ],
        chat_session_id=session.id,
    )

    await db_session.refresh(session)
    assert session.opencode_session_id == "sess-persisted"
    assert run.input_params["context"]["opencode_session_id"] == "sess-persisted"
    assert run.input_params["context"]["opencode_recovery_messages"] == []
    assert create_calls == []


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
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    chat_session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        title="Streaming Test",
    )
    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={
            "input": "Stream now",
            "context": {
                "chat_session_id": str(chat_session.id),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
                "preview_workspace_stage_path": "/workspace",
            },
        },
        context_window_json={
            "source": "estimated",
            "model_id": "opencode/gpt-5",
            "max_tokens": 256000,
            "max_tokens_source": "opencode_default",
            "input_tokens": 2048,
            "remaining_tokens": 253952,
            "usage_ratio": 0.008,
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
    accepted = next(event for event in events if event.get("event") == "run.accepted")
    assert accepted["payload"]["context_window"]["max_tokens"] == 256000
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
async def test_v2_stream_emits_live_context_status_after_tool_events(db_session, monkeypatch):
    class _FakeEngine:
        async def stream(self, ctx):
            _ = ctx
            yield SimpleNamespace(
                event="context_window.updated",
                stage="context",
                payload={
                    "context_window": {
                        "source": "estimated",
                        "model_id": "opencode/gpt-5",
                        "max_tokens": 256000,
                        "max_tokens_source": "opencode_default",
                        "input_tokens": 2080,
                        "remaining_tokens": 253920,
                        "usage_ratio": 2080 / 256000,
                    }
                },
                diagnostics=[],
            )
            yield SimpleNamespace(event="run.completed", stage="run", payload={"status": "completed"}, diagnostics=[])

        async def cancel(self, run):
            _ = run
            return SimpleNamespace(confirmed=True, diagnostics=[])

    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_resolve_engine_for_run",
        lambda self, run: _FakeEngine(),
    )

    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    chat_session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        title="Context Window Test",
    )
    app = SimpleNamespace(id=UUID(app_id), organization_id=tenant.id, agent_id=agent.id)
    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={
            "input": "Inspect files",
            "context": {
                "chat_session_id": str(chat_session.id),
                "preview_sandbox_id": "sandbox-test",
                "preview_sandbox_status": "running",
                "preview_workspace_stage_path": "/workspace",
            },
        },
        context_window_json={
            "source": "estimated",
            "model_id": "opencode/gpt-5",
            "max_tokens": 256000,
            "max_tokens_source": "opencode_default",
            "input_tokens": 2048,
            "remaining_tokens": 253952,
            "usage_ratio": 0.008,
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=app.id,
        base_revision_id=UUID(draft_revision_id),
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]
    context_event = next(event for event in events if event.get("event") == "context_window.updated")
    context_window = context_event["payload"]["context_window"]
    assert context_window["source"] == "estimated"
    assert context_window["input_tokens"] > 2048


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
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    chat_session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        title="Missing Terminal Test",
    )
    app = SimpleNamespace(id=UUID(app_id), organization_id=tenant.id)
    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.queued,
        input_params={
            "input": "Stream now",
            "context": {
                "chat_session_id": str(chat_session.id),
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
    events = [event async for event in service.stream_run_events(app=app, run=run)]
    assert any(event.get("event") == "assistant.delta" for event in events)
    assert not any(event.get("event") == "run.failed" for event in events)

    refreshed = await db_session.get(AgentRun, run.id)
    assert refreshed is not None
    refreshed_status = refreshed.status.value if hasattr(refreshed.status, "value") else str(refreshed.status)
    assert refreshed_status != RunStatus.failed.value


@pytest.mark.asyncio
async def test_v2_tool_event_history_append_preserves_external_updates(db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    _ = org_unit
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    chat_session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        title="Tool History Test",
    )

    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={
            "input": "Persist tool events",
            "context": {
                "chat_session_id": str(chat_session.id),
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
    await service._persist_tool_event_for_history(
        run=run,
        event="tool.started",
        stage="tool",
        payload={"tool": "read", "span_id": "span-1"},
        diagnostics=[],
    )

    from app.db.postgres.engine import sessionmaker as get_sessionmaker

    async with get_sessionmaker() as external_db:
        external_run = await external_db.get(AgentRun, run.id)
        assert external_run is not None
        external_output = dict(external_run.output_result) if isinstance(external_run.output_result, dict) else {}
        external_events = list(external_output.get("tool_events") or [])
        external_events.append(
            {
                "event": "tool.started",
                "stage": "tool",
                "payload": {"tool": "glob", "span_id": "span-2"},
                "diagnostics": [],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        external_output["tool_events"] = external_events
        external_run.output_result = external_output
        await external_db.commit()

    # Local db_session still has a stale identity-map copy; append must merge with
    # latest DB value, not overwrite it.
    await service._persist_tool_event_for_history(
        run=run,
        event="tool.completed",
        stage="tool",
        payload={"tool": "read", "span_id": "span-1"},
        diagnostics=[],
    )

    refreshed_row = await db_session.execute(
        select(AgentRun)
        .where(AgentRun.id == run.id)
        .execution_options(populate_existing=True)
    )
    refreshed = refreshed_row.scalar_one()
    tool_events = list((refreshed.output_result or {}).get("tool_events") or [])
    assert len(tool_events) == 3
    assert [event.get("payload", {}).get("span_id") for event in tool_events] == [
        "span-1",
        "span-2",
        "span-1",
    ]


@pytest.mark.asyncio
async def test_v2_answer_question_endpoint(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )

    run = AgentRun(
        organization_id=tenant.id,
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
    app_id, _ = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )

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
    app_id, _ = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )

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
