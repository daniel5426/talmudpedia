from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessageChunk

from app.agent.executors.standard import ReasoningNodeExecutor
from app.agent.executors.tool import ToolNodeExecutor
from app.agent.execution.emitter import active_emitter
from app.agent.execution.run_task_registry import mark_run_cancel_requested
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadStatus
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)
from app.services.model_resolver import ModelResolver


class FakeToolChildRunEmitter:
    def __init__(self) -> None:
        self.internal_events: list[tuple[str, dict[str, object], str | None, str | None]] = []

    def emit_tool_start(self, *args, **kwargs) -> None:
        return None

    def emit_tool_end(self, *args, **kwargs) -> None:
        return None

    def emit_tool_failed(self, *args, **kwargs) -> None:
        return None

    def emit_error(self, *args, **kwargs) -> None:
        return None

    def emit_internal_event(self, event_name, data, *, node_id=None, category=None, visibility=None) -> None:
        self.internal_events.append((str(event_name), dict(data or {}), node_id, category))


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"owner-{suffix}@example.com", role="user")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _create_agent(
    db_session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    slug: str,
    status: AgentStatus,
    graph_definition: dict | None = None,
) -> Agent:
    agent = Agent(
        tenant_id=tenant_id,
        name=f"Agent {slug}",
        slug=slug,
        description="agent_call target",
        graph_definition=graph_definition or {"spec_version": "1.0", "nodes": [], "edges": []},
        status=status,
        created_by=user_id,
        is_active=True,
    )
    if status == AgentStatus.published:
        agent.published_at = datetime.now(timezone.utc)
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _create_agent_call_tool(
    db_session,
    *,
    tenant_id: UUID,
    target_agent_slug: str | None = None,
    target_agent_id: UUID | None = None,
    timeout_s: int | None = None,
) -> ToolRegistry:
    implementation: dict[str, object] = {"type": "agent_call"}
    if target_agent_slug:
        implementation["target_agent_slug"] = target_agent_slug
    if target_agent_id:
        implementation["target_agent_id"] = str(target_agent_id)

    config_schema: dict[str, object] = {"implementation": implementation}
    if timeout_s is not None:
        config_schema["execution"] = {"timeout_s": timeout_s}

    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=f"Agent Call {uuid4().hex[:6]}",
        slug=f"agent-call-{uuid4().hex[:8]}",
        description="call another agent",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema=config_schema,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.AGENT_CALL,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_agent_call_tool_success_uses_fresh_child_session_and_returns_compact_output(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    original_start_run = AgentExecutorService.start_run
    start_session_ids: set[int] = set()
    stream_session_ids: set[int] = set()

    async def wrapped_start_run(self, *args, **kwargs):
        assert self.db is not db_session
        start_session_ids.add(id(self.db))
        return await original_start_run(self, *args, **kwargs)

    async def fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        assert db is not db_session
        stream_session_ids.add(id(db))
        run = await db.get(AgentRun, run_id)
        run.status = RunStatus.completed
        run.output_result = {
            "state": {"last_agent_output": {"answer": "child-ok"}},
            "context": {"source": "child"},
        }
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "start_run", wrapped_start_run)
    monkeypatch.setattr(AgentExecutorService, "run_and_stream", fake_run_and_stream)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    result = await executor.execute(
        state={"context": {"input": "hello child"}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node", "mode": "debug"},
    )

    payload = result["context"]
    assert payload["mode"] == "sync"
    assert payload["status"] == "completed"
    assert payload["target_agent_slug"] == target.slug
    assert payload["output"] == {"answer": "child-ok"}
    assert payload["context"] == {"source": "child"}
    assert UUID(payload["run_id"])
    assert start_session_ids
    assert stream_session_ids
    assert stream_session_ids.issubset(start_session_ids)


@pytest.mark.asyncio
async def test_agent_call_tool_emits_hidden_child_run_started_with_target_agent_name(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"named-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    emitter = FakeToolChildRunEmitter()

    async def fake_execute_sync_with_new_session(*args, **kwargs):
        on_run_created = kwargs.get("on_run_created")
        child_run_id = uuid4()
        if callable(on_run_created):
            on_run_created(child_run_id)
        return SimpleNamespace(
            run_id=child_run_id,
            status="completed",
            output_result={"state": {"last_agent_output": {"answer": "ok"}}},
            error_message=None,
        )

    monkeypatch.setattr(AgentExecutorService, "execute_sync_with_new_session", fake_execute_sync_with_new_session)

    token = active_emitter.set(emitter)
    try:
        executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
        await executor.execute(
            state={"context": {"input": "hello child"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "agent_1", "mode": "debug"},
        )
    finally:
        active_emitter.reset(token)

    matching = [item for item in emitter.internal_events if item[0] == "tool.child_run_started"]
    assert matching
    event_name, data, node_id, category = matching[0]
    assert event_name == "tool.child_run_started"
    assert data["agent_id"] == str(target.id)
    assert data["agent_name"] == target.name
    assert data["source_node_id"] == "agent_1"
    assert node_id == "agent_1"
    assert category == "tool_execution"


@pytest.mark.asyncio
async def test_agent_call_tool_rejects_unpublished_target(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"draft-child-{uuid4().hex[:8]}",
        status=AgentStatus.draft,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    with pytest.raises(PermissionError, match="published"):
        await executor.execute(
            state={"context": {"input": "hello"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug"},
        )


@pytest.mark.asyncio
async def test_agent_call_tool_timeout_returns_failed_payload(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"slow-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(
        db_session,
        tenant_id=tenant.id,
        target_agent_slug=target.slug,
        timeout_s=1,
    )

    async def slow_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        await asyncio.sleep(1.2)
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", slow_run_and_stream)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    result = await executor.execute(
        state={"context": {"input": "slow call"}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node", "mode": "debug"},
    )

    payload = result["context"]
    assert payload["status"] == "failed"
    assert "timed out" in payload["error"]

    run = await db_session.get(AgentRun, UUID(payload["run_id"]))
    assert run is not None
    assert run.status == RunStatus.failed


@pytest.mark.asyncio
async def test_agent_call_tool_rejects_cancelled_parent_run(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"cancelled-parent-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    parent_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=target.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.cancelled,
        input_params={"messages": []},
        depth=0,
    )
    db_session.add(parent_run)
    await db_session.commit()
    await db_session.refresh(parent_run)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    with pytest.raises(RuntimeError, match="cancelled"):
        await executor.execute(
            state={"context": {"input": "should not execute"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug", "run_id": str(parent_run.id)},
        )


@pytest.mark.asyncio
async def test_start_run_rechecks_parent_status_from_db_when_session_is_stale(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"stale-parent-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )

    parent_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=target.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={"messages": []},
        depth=0,
    )
    db_session.add(parent_run)
    await db_session.commit()
    await db_session.refresh(parent_run)

    stale_parent = await db_session.get(AgentRun, parent_run.id)
    assert stale_parent is not None
    assert stale_parent.status == RunStatus.running

    async with sessionmaker() as other_session:
        fresh_parent = await other_session.get(AgentRun, parent_run.id)
        assert fresh_parent is not None
        fresh_parent.status = RunStatus.cancelled
        await other_session.commit()

    executor = AgentExecutorService(db_session)
    with pytest.raises(RuntimeError, match="cancelled"):
        await executor.start_run(
            agent_id=target.id,
            input_params={"input": "should not spawn", "context": {}},
            user_id=user.id,
            background=False,
            parent_run_id=parent_run.id,
        )


@pytest.mark.asyncio
async def test_reasoning_node_stops_after_tool_if_run_was_cancelled(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"reasoning-cancel-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    current_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=target.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={"messages": []},
        depth=0,
    )
    db_session.add(current_run)
    await db_session.commit()
    await db_session.refresh(current_run)

    class _FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def stream(self, _messages, _system_prompt=None, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"id": "call-1", "name": tool.slug, "args": '{"input":"ask child"}'}],
                )
                return
            yield AIMessageChunk(content="parent final output should not happen")

    provider = _FakeProvider()

    async def fake_resolve_for_execution(_self, _model_id, policy_override=None, policy_snapshot=None):
        return SimpleNamespace(
            provider_instance=provider,
            resolved_provider="unit",
            binding=SimpleNamespace(id="binding-1", provider_model_id="unit-provider-model"),
            logical_model=SimpleNamespace(id="unit-model"),
        )

    async def fake_tool_execute(self, state, config, context=None):
        async with sessionmaker() as other_session:
            run = await other_session.get(AgentRun, current_run.id)
            assert run is not None
            run.status = RunStatus.cancelled
            run.completed_at = datetime.now(timezone.utc)
            await other_session.commit()
        return {
            "context": {
                "mode": "sync",
                "target_agent_slug": target.slug,
                "status": "completed",
                "output": "child final output",
            }
        }

    monkeypatch.setattr(ModelResolver, "resolve_for_execution", fake_resolve_for_execution)
    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_tool_execute)

    executor = ReasoningNodeExecutor(tenant_id=tenant.id, db=db_session)
    state_update = await executor.execute(
        state={"messages": [{"role": "user", "content": "call child"}], "state": {}},
        config={
            "model_id": "unit-model",
            "name": "Agent",
            "tools": [str(tool.id)],
            "max_tool_iterations": 2,
            "tool_execution_mode": "sequential",
            "output_format": "text",
        },
        context={"node_id": "agent_node_1", "run_id": str(current_run.id)},
    )

    await db_session.refresh(current_run)
    assert current_run.status == RunStatus.cancelled
    contents = [str(getattr(message, "content", "") or "") for message in state_update["messages"]]
    assert "parent final output should not happen" not in " ".join(contents)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_agent_call_tool_rechecks_current_run_before_spawning_child(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"tool-gate-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    current_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=target.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={"messages": []},
        depth=1,
    )
    db_session.add(current_run)
    await db_session.commit()
    await db_session.refresh(current_run)

    original_resolve_target = ToolNodeExecutor._resolve_agent_target
    child_spawn_attempted = False

    async def wrapped_resolve_target(self, *args, **kwargs):
        async with sessionmaker() as other_session:
            run = await other_session.get(AgentRun, current_run.id)
            assert run is not None
            run.status = RunStatus.cancelled
            run.completed_at = datetime.now(timezone.utc)
            await other_session.commit()
        return await original_resolve_target(self, *args, **kwargs)

    async def fail_if_called(*args, **kwargs):
        nonlocal child_spawn_attempted
        child_spawn_attempted = True
        raise AssertionError("child execution should not start for a cancelled run")

    monkeypatch.setattr(ToolNodeExecutor, "_resolve_agent_target", wrapped_resolve_target)
    monkeypatch.setattr(AgentExecutorService, "execute_sync_with_new_session", fail_if_called)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    with pytest.raises(RuntimeError, match="cancelled"):
        await executor.execute(
            state={"context": {"input": "call child"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug", "run_id": str(current_run.id)},
        )

    assert child_spawn_attempted is False


@pytest.mark.asyncio
async def test_agent_call_tool_blocks_descendant_spawn_when_root_cancel_requested(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"root-cancel-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    root_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=target.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={"messages": []},
        depth=0,
    )
    db_session.add(root_run)
    await db_session.flush()
    child_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=target.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={"messages": []},
        root_run_id=root_run.id,
        parent_run_id=root_run.id,
        depth=1,
    )
    db_session.add(child_run)
    await db_session.commit()
    await db_session.refresh(root_run)
    await db_session.refresh(child_run)

    original_resolve_target = ToolNodeExecutor._resolve_agent_target
    child_spawn_attempted = False

    async def wrapped_resolve_target(self, *args, **kwargs):
        mark_run_cancel_requested([root_run.id])
        return await original_resolve_target(self, *args, **kwargs)

    async def fail_if_called(*args, **kwargs):
        nonlocal child_spawn_attempted
        child_spawn_attempted = True
        raise AssertionError("child execution should not start under a cancelled root")

    monkeypatch.setattr(ToolNodeExecutor, "_resolve_agent_target", wrapped_resolve_target)
    monkeypatch.setattr(AgentExecutorService, "execute_sync_with_new_session", fail_if_called)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    with pytest.raises(RuntimeError, match="cancelled"):
        await executor.execute(
            state={"context": {"input": "call child"}},
            config={"tool_id": str(tool.id)},
            context={
                "node_id": "tool-node",
                "mode": "debug",
                "run_id": str(child_run.id),
                "root_run_id": str(root_run.id),
                "parent_run_id": str(root_run.id),
            },
        )

    assert child_spawn_attempted is False


@pytest.mark.asyncio
async def test_agent_call_tool_concurrent_runs_use_distinct_child_sessions(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"parallel-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    active_session_ids: set[int] = set()

    async def fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        assert db is not db_session
        active_session_ids.add(id(db))
        run = await db.get(AgentRun, run_id)
        run.status = RunStatus.completed
        run.output_result = {
            "state": {"last_agent_output": {"run_id": str(run_id)}},
            "context": {"source": "parallel"},
        }
        run.completed_at = datetime.now(timezone.utc)
        await asyncio.sleep(0.05)
        await db.commit()
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", fake_run_and_stream)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    results = await asyncio.gather(
        executor.execute(
            state={"context": {"input": "hello child 1"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug"},
        ),
        executor.execute(
            state={"context": {"input": "hello child 2"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug"},
        ),
    )

    assert len(active_session_ids) == 2
    assert all(item["context"]["status"] == "completed" for item in results)


@pytest.mark.asyncio
async def test_execute_sync_with_new_session_cleans_up_child_task_on_cancellation(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"cancel-cleanup-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )

    started = asyncio.Event()
    settled = asyncio.Event()

    async def hanging_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        started.set()
        try:
            while True:
                await asyncio.sleep(1)
                if False:
                    yield None
        finally:
            settled.set()

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", hanging_run_and_stream)

    task = asyncio.create_task(
        AgentExecutorService.execute_sync_with_new_session(
            agent_id=target.id,
            input_params={"input": "cancel me", "context": {}},
            user_id=user.id,
            mode=ExecutionMode.DEBUG,
        )
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(settled.wait(), timeout=2.0)
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_agent_call_tool_derives_child_lineage_from_current_run(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"lineage-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    captured: dict[str, object] = {}
    original_start_run = AgentExecutorService.start_run

    async def wrapped_start_run(self, *args, **kwargs):
        captured["root_run_id"] = kwargs.get("root_run_id")
        captured["parent_run_id"] = kwargs.get("parent_run_id")
        captured["parent_node_id"] = kwargs.get("parent_node_id")
        captured["depth"] = kwargs.get("depth")
        return await original_start_run(self, *args, **kwargs)

    async def fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        run = await db.get(AgentRun, run_id)
        run.status = RunStatus.completed
        run.output_result = {"state": {"last_agent_output": {"ok": True}}}
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "start_run", wrapped_start_run)
    monkeypatch.setattr(AgentExecutorService, "run_and_stream", fake_run_and_stream)

    current_root_run_id = uuid4()
    current_run_id = uuid4()
    shared_thread = AgentThread(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=target.id,
        published_app_id=None,
        surface=AgentThreadSurface.internal,
        status=AgentThreadStatus.active,
        title="Lineage Thread",
        last_activity_at=datetime.now(timezone.utc),
    )
    db_session.add(shared_thread)
    await db_session.flush()
    db_session.add(
        AgentRun(
            id=current_root_run_id,
            agent_id=target.id,
            tenant_id=tenant.id,
            user_id=user.id,
            thread_id=shared_thread.id,
            status=RunStatus.running,
            input_params={},
            root_run_id=current_root_run_id,
            parent_run_id=None,
            parent_node_id=None,
            depth=0,
        )
    )
    db_session.add(
        AgentRun(
            id=current_run_id,
            agent_id=target.id,
            tenant_id=tenant.id,
            user_id=user.id,
            thread_id=shared_thread.id,
            status=RunStatus.running,
            input_params={},
            root_run_id=current_root_run_id,
            parent_run_id=current_root_run_id,
            parent_node_id=None,
            depth=2,
        )
    )
    await db_session.commit()

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    await executor.execute(
        state={"context": {"input": "hello child"}},
        config={"tool_id": str(tool.id)},
        context={
            "node_id": "agent_node_1",
            "mode": "debug",
            "run_id": str(current_run_id),
            "root_run_id": str(current_root_run_id),
            "parent_run_id": str(uuid4()),
            "depth": 2,
        },
    )

    assert captured["root_run_id"] == current_root_run_id
    assert captured["parent_run_id"] == current_run_id
    assert captured["parent_node_id"] == "agent_node_1"
    assert captured["depth"] == 3


@pytest.mark.asyncio
async def test_agent_call_tool_emits_hidden_child_run_started_event_for_overlay(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"agent-call-overlay-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    async def fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        run = await db.get(AgentRun, run_id)
        run.status = RunStatus.completed
        run.output_result = {"state": {"last_agent_output": {"ok": True}}}
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", fake_run_and_stream)

    fake_emitter = FakeToolChildRunEmitter()
    token = active_emitter.set(fake_emitter)
    try:
        executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
        await executor.execute(
            state={"context": {"input": "hello child"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "agent_node_overlay", "mode": "debug"},
        )
    finally:
        active_emitter.reset(token)

    started = next(event for event in fake_emitter.internal_events if event[0] == "tool.child_run_started")
    assert started[1]["status"] == "running"
    assert started[1]["source_node_id"] == "agent_node_overlay"
    assert UUID(str(started[1]["child_run_id"]))
    assert started[2] == "agent_node_overlay"
    assert started[3] == "tool_execution"


@pytest.mark.asyncio
async def test_agent_call_tool_denies_cross_tenant_target(db_session):
    tenant_a, user_a = await _seed_tenant_and_user(db_session)
    tenant_b, user_b = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant_b.id,
        user_id=user_b.id,
        slug=f"other-tenant-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(
        db_session,
        tenant_id=tenant_a.id,
        target_agent_id=target.id,
    )

    executor = ToolNodeExecutor(tenant_id=tenant_a.id, db=db_session)
    with pytest.raises(ValueError, match="tenant scope"):
        await executor.execute(
            state={"context": {"input": "hello"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug"},
        )


@pytest.mark.asyncio
async def test_agent_call_tool_maps_payload_into_child_state_and_modalities(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"structured-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={
                "workflow_contract": {
                    "inputs": [
                        {"key": "text", "type": "string", "semantic_type": "text"},
                        {"key": "files", "type": "list", "semantic_type": "files"},
                    ],
                },
            "state_contract": {
                "variables": [
                    {"key": "customer_id", "type": "string"},
                    {"key": "flag", "type": "boolean", "default_value": False},
                ],
            },
            "nodes": [],
            "edges": [],
        },
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    input_params = executor._map_agent_contract_input(
        target=target,
        input_data={
            "text": "hello child",
            "files": [{"id": "att-1"}],
            "customer_id": "cust-123",
            "flag": True,
            "context": {"source": "parent"},
        },
    )

    assert tool is not None
    assert input_params["input"] == "hello child"
    assert input_params["workflow_input"]["files"] == [{"id": "att-1"}]
    assert input_params["state"]["customer_id"] == "cust-123"
    assert input_params["state"]["flag"] is True
    assert input_params["context"] == {"source": "parent"}
