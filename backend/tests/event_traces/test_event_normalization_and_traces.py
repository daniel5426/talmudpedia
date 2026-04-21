import asyncio

import pytest
from sqlalchemy import select

from app.agent.execution.emitter import EventEmitter
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
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
async def test_trace_persistence_persists_point_events_in_sequence(db_session, test_tenant_id, test_user_id, run_prefix):
    agent = Agent(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-trace",
        slug=f"{run_prefix}-trace",
        graph_definition=_graph_definition(),
        created_by=test_user_id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    run = AgentRun(
        organization_id=test_tenant_id,
        agent_id=agent.id,
        user_id=test_user_id,
        status=RunStatus.queued,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)

    await recorder.save_event(
        run.id,
        db_session,
        {
            "event": "token",
            "run_id": str(run.id),
            "span_id": "span-1",
            "name": "Token",
            "data": {"content": "hi"},
            "metadata": {"category": "stream"},
            "sequence": 1,
        },
    )
    result = await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run.id))
    traces = result.scalars().all()
    assert len(traces) == 1
    assert traces[0].span_type == "token"
    assert traces[0].outputs == {"content": "hi"}
    assert traces[0].metadata_["sequence"] == 1

    start_event = {
        "event": "node_start",
        "run_id": str(run.id),
        "span_id": "span-1",
        "name": "Node 1",
        "data": {"input": {"foo": "bar"}},
        "metadata": {},
        "parent_ids": [],
        "sequence": 2,
    }
    await recorder.save_event(run.id, db_session, start_event)
    await recorder.save_event(run.id, db_session, start_event | {"sequence": 3})

    result = await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run.id))
    traces = result.scalars().all()
    assert len(traces) == 3
    sequences = sorted(int(trace.metadata_["sequence"]) for trace in traces)
    assert sequences == [1, 2, 3]


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_trace_persistence_lists_events_in_order(db_session, test_tenant_id, test_user_id, run_prefix):
    agent = Agent(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-trace-end",
        slug=f"{run_prefix}-trace-end",
        graph_definition=_graph_definition(),
        created_by=test_user_id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    run = AgentRun(
        organization_id=test_tenant_id,
        agent_id=agent.id,
        user_id=test_user_id,
        status=RunStatus.queued,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)

    start_event = {
        "event": "node_start",
        "run_id": str(run.id),
        "span_id": "span-2",
        "name": "Node 2",
        "data": {"input": {"value": 1}},
        "metadata": {},
        "parent_ids": [],
        "sequence": 1,
    }
    end_event = {
        "event": "node_end",
        "run_id": str(run.id),
        "span_id": "span-2",
        "name": "Node 2",
        "data": {"output": {"value": 2}},
        "metadata": {},
        "parent_ids": [],
        "sequence": 2,
    }

    await recorder.save_event(run.id, db_session, start_event)
    await recorder.save_event(run.id, db_session, end_event)

    events = await recorder.list_events(db_session, run.id)
    assert [event["event"] for event in events] == ["node_start", "node_end"]
    assert events[0]["sequence"] == 1
    assert events[0]["inputs"] == {"input": {"value": 1}}
    assert events[1]["sequence"] == 2
    assert events[1]["outputs"] == {"output": {"value": 2}}


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_scheduled_trace_persistence_preserves_sequence_order_in_listed_stream(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    agent = Agent(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-trace-ordered-queue",
        slug=f"{run_prefix}-trace-ordered-queue",
        graph_definition=_graph_definition(),
        created_by=test_user_id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    run = AgentRun(
        organization_id=test_tenant_id,
        agent_id=agent.id,
        user_id=test_user_id,
        status=RunStatus.running,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    recorder.schedule_persist(
        run.id,
        {
            "event": "orchestration.child_lifecycle",
            "run_id": str(run.id),
            "span_id": "spawn-node",
            "name": "orchestration.child_lifecycle",
            "data": {"child_run_id": "child-1", "status": "running"},
            "metadata": {"category": "orchestration"},
        },
        sequence=10,
    )
    recorder.schedule_persist(
        run.id,
        {
            "event": "node_end",
            "run_id": str(run.id),
            "span_id": "agent-node",
            "name": "Agent",
            "data": {"output": {"done": True}},
            "metadata": {"category": "node"},
        },
        sequence=11,
    )
    await recorder.drain()

    events = await recorder.list_events(db_session, run.id)
    assert [(event["sequence"], event["event"]) for event in events] == [
        (10, "orchestration.child_lifecycle"),
        (11, "node_end"),
    ]
