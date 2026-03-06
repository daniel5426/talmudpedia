from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.agent.executors.base import BaseNodeExecutor
from app.agent.graph.ir import GraphIRNode
from app.agent.graph.node_factory import build_node_fn
from app.agent.registry import AgentExecutorRegistry
from app.db.postgres.models.agent_threads import (
    AgentThread,
    AgentThreadStatus,
    AgentThreadSurface,
    AgentThreadTurn,
    AgentThreadTurnStatus,
)
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant


class _BoomExecutor(BaseNodeExecutor):
    async def execute(self, state, config, context=None):  # pragma: no cover - intentionally raises
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_node_factory_returns_recoverable_error_update_instead_of_reraising():
    node_type = f"unit_boom_{uuid4().hex[:8]}"
    previous = AgentExecutorRegistry._executors.get(node_type)
    AgentExecutorRegistry.register(node_type, _BoomExecutor)
    try:
        node = GraphIRNode(id="boom-node", type=node_type, config={})
        node_fn = build_node_fn(node=node, tenant_id=None, db=None)
        state = {"state": {"foo": "bar"}}

        update = await node_fn(state, config={"configurable": {}})

        assert isinstance(update, dict)
        assert "execution error" in str(update.get("messages", [None])[-1].content).lower()
        assert update.get("error") == "boom"
        assert isinstance(update.get("state"), dict)
        assert update["state"]["last_error"]["code"] == "NODE_EXECUTION_ERROR"
        assert update["state"]["last_error"]["node_id"] == "boom-node"
    finally:
        if previous is None:
            AgentExecutorRegistry._executors.pop(node_type, None)
        else:
            AgentExecutorRegistry._executors[node_type] = previous


@pytest.mark.asyncio
async def test_run_and_stream_setup_error_emits_error_event_and_persists_failed_turn(db_session, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    graph = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "end", "type": "end", "position": {"x": 1, "y": 0}, "config": {}},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }
    agent = Agent(
        tenant_id=tenant.id,
        name=f"agent-{suffix}",
        slug=f"agent-{suffix}",
        description="runtime recovery test",
        graph_definition=graph,
        status=AgentStatus.draft,
        is_active=True,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    thread = AgentThread(
        tenant_id=tenant.id,
        agent_id=agent.id,
        surface=AgentThreadSurface.internal,
        status=AgentThreadStatus.active,
        title="runtime recovery",
        last_activity_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        status=RunStatus.queued,
        input_params={
            "input": "hello",
            "messages": [{"role": "user", "content": "hello"}],
            "context": {},
        },
        thread_id=thread.id,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    run_id = run.id

    async def _boom_compile(*args, **kwargs):
        raise RuntimeError("compile exploded")

    monkeypatch.setattr("app.agent.execution.service.AgentCompiler.compile", _boom_compile)

    executor = AgentExecutorService(db=db_session)
    streamed_events = []
    async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
        streamed_events.append(event)

    assert streamed_events
    assert any(getattr(evt, "event", None) == "error" for evt in streamed_events)

    db_session.expire_all()
    refreshed_run = await db_session.get(AgentRun, run_id)
    assert refreshed_run is not None
    assert refreshed_run.status == RunStatus.failed
    assert isinstance(refreshed_run.output_result, dict)
    assert "Execution failed: compile exploded" in str(refreshed_run.output_result.get("messages", [{}])[-1].get("content", ""))

    turn = (
        await db_session.execute(
            select(AgentThreadTurn).where(AgentThreadTurn.run_id == run_id).limit(1)
        )
    ).scalar_one_or_none()
    assert turn is not None
    assert turn.status == AgentThreadTurnStatus.failed
    assert turn.user_input_text == "hello"
    assert "Execution failed: compile exploded" in (turn.assistant_output_text or "")
