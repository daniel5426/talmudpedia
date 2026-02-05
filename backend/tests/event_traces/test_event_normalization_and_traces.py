import asyncio

import pytest
from sqlalchemy import select

from app.agent.execution.emitter import EventEmitter
from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import Agent, AgentRun, AgentTrace, RunStatus


def _graph_definition():
    return {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
            {
                "id": "transform",
                "type": "transform",
                "position": {"x": 120, "y": 0},
                "config": {
                    "mode": "object",
                    "mappings": [{"key": "trace", "value": "ok"}],
                },
            },
            {"id": "end", "type": "end", "position": {"x": 240, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "transform"},
            {"id": "e2", "source": "transform", "target": "end"},
        ],
    }


@pytest.mark.asyncio
async def test_event_emitter_enqueues_events():
    queue: asyncio.Queue = asyncio.Queue()
    emitter = EventEmitter(queue, run_id="run-1", mode="debug")

    emitter.emit_node_start("node-1", "Node 1", "start", {"input": "x"})

    event = await queue.get()
    assert event.event == "node_start"
    assert event.run_id == "run-1"
    assert event.name == "Node 1"
    assert event.data["type"] == "start"


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_trace_persistence_filters_and_deduplicates(db_session, test_tenant_id, test_user_id, run_prefix):
    agent = Agent(
        tenant_id=test_tenant_id,
        name=f"{run_prefix}-trace",
        slug=f"{run_prefix}-trace",
        graph_definition=_graph_definition(),
        created_by=test_user_id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    run = AgentRun(
        tenant_id=test_tenant_id,
        agent_id=agent.id,
        user_id=test_user_id,
        status=RunStatus.queued,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = AgentExecutorService(db=db_session)

    await service._save_trace_event(run.id, db_session, {"event": "token", "run_id": "span-1"})
    result = await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run.id))
    assert result.scalars().all() == []

    start_event = {
        "event": "node_start",
        "run_id": "span-1",
        "name": "Node 1",
        "data": {"input": {"foo": "bar"}},
        "metadata": {},
        "parent_ids": [],
    }
    await service._save_trace_event(run.id, db_session, start_event)
    await service._save_trace_event(run.id, db_session, start_event)

    result = await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run.id))
    traces = result.scalars().all()
    assert len(traces) == 1


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_trace_persistence_updates_end_event(db_session, test_tenant_id, test_user_id, run_prefix):
    agent = Agent(
        tenant_id=test_tenant_id,
        name=f"{run_prefix}-trace-end",
        slug=f"{run_prefix}-trace-end",
        graph_definition=_graph_definition(),
        created_by=test_user_id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    run = AgentRun(
        tenant_id=test_tenant_id,
        agent_id=agent.id,
        user_id=test_user_id,
        status=RunStatus.queued,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    service = AgentExecutorService(db=db_session)

    start_event = {
        "event": "node_start",
        "run_id": "span-2",
        "name": "Node 2",
        "data": {"input": {"value": 1}},
        "metadata": {},
        "parent_ids": [],
    }
    end_event = {
        "event": "node_end",
        "run_id": "span-2",
        "name": "Node 2",
        "data": {"output": {"value": 2}},
        "metadata": {},
        "parent_ids": [],
    }

    await service._save_trace_event(run.id, db_session, start_event)
    await service._save_trace_event(run.id, db_session, end_event)

    result = await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run.id))
    trace = result.scalars().first()
    assert trace is not None
    assert trace.end_time is not None
    assert trace.outputs == {"value": 2}
