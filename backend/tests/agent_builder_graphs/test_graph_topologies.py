import pytest

from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.db.postgres.models.agents import AgentRun, RunStatus

from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    execute_agent_via_service,
    graph_def,
    node_def,
    edge_def,
    minimal_config_for,
)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_diamond_graph_exec(db_session, test_tenant_id, test_user_id, run_prefix):
    if_else_config = {"conditions": [{"name": "yes", "expression": "contains(input, \"yes\")"}]}
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("route", "if_else", if_else_config),
            node_def("left", "transform", minimal_config_for("transform")),
            node_def("right", "transform", minimal_config_for("transform")),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "route"),
            edge_def("e2", "route", "left", source_handle="yes"),
            edge_def("e3", "route", "right", source_handle="else"),
            edge_def("e4", "left", "end"),
            edge_def("e5", "right", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-diamond", f"{run_prefix}-diamond", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="yes")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_loop_graph_exec(db_session, test_tenant_id, test_user_id, run_prefix):
    while_config = {"condition": "!has(loop_counters, \"while_node\")", "max_iterations": 3}
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("while_node", "while", while_config),
            node_def("transform", "transform", minimal_config_for("transform")),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "while_node"),
            edge_def("e2", "while_node", "transform", source_handle="loop"),
            edge_def("e3", "transform", "while_node"),
            edge_def("e4", "while_node", "end", source_handle="exit"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-loopg", f"{run_prefix}-loopg", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
        assert "loop_counters" in run.output_result
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_parallel_fanout_exec(db_session, test_tenant_id, test_user_id, run_prefix):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("parallel", "parallel"),
            node_def("branch1", "set_state", minimal_config_for("set_state")),
            node_def("branch2", "set_state", minimal_config_for("set_state")),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "parallel"),
            edge_def("e2", "parallel", "branch1"),
            edge_def("e3", "parallel", "branch2"),
            edge_def("e4", "branch1", "end"),
            edge_def("e5", "branch2", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-parallelg", f"{run_prefix}-parallelg", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_disconnected_graph_fails(db_session, test_tenant_id):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("end", "end", minimal_config_for("end")),
            node_def("orphan", "transform", minimal_config_for("transform")),
        ],
        [
            edge_def("e1", "start", "end"),
        ],
    )

    compiler = AgentCompiler(db=db_session, tenant_id=test_tenant_id)
    errors = await compiler.validate(AgentGraph(**graph))
    critical = [e for e in errors if e.severity == "error"]
    assert critical
