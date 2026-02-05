import pytest

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    graph_def,
    node_def,
    edge_def,
    minimal_config_for,
)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_node_events_emitted_for_start_human_end(
    db_session,
    test_tenant_id,
    test_user_id,
    run_prefix,
):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("human", "human_input"),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "human"),
            edge_def("e2", "human", "end"),
        ],
    )

    agent = await create_agent(
        db_session,
        test_tenant_id,
        test_user_id,
        f"{run_prefix}-events",
        f"{run_prefix}-events",
        graph,
    )

    try:
        executor = AgentExecutorService(db=db_session)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params={"input": "hello"},
            background=False,
            mode=ExecutionMode.DEBUG,
        )

        events = []
        async for event in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
            if event.event in {"node_start", "node_end"}:
                events.append((event.event, event.span_id))

        for node_id in ("start", "human", "end"):
            assert ("node_start", node_id) in events
            assert ("node_end", node_id) in events
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)
