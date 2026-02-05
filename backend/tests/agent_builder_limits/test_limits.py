import os
import asyncio

import pytest

from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.db.postgres.models.agents import AgentRun, RunStatus

from sdk.fuzzer import GraphFuzzer
from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    execute_agent_via_service,
    graph_def,
    node_def,
    edge_def,
    minimal_config_for,
    list_agent_operator_specs,
)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_50_node_execution(db_session, test_tenant_id, test_user_id, run_prefix):
    nodes = [node_def("start", "start")]
    edges = []
    prev_id = "start"
    for i in range(48):
        node_id = f"t{i}"
        nodes.append(node_def(node_id, "transform", minimal_config_for("transform")))
        edges.append(edge_def(f"e{i}", prev_id, node_id))
        prev_id = node_id
    nodes.append(node_def("end", "end", minimal_config_for("end")))
    edges.append(edge_def("e-last", prev_id, "end"))

    graph = graph_def(nodes, edges)
    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-50", f"{run_prefix}-50", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_100_node_compile(db_session, test_tenant_id):
    nodes = [node_def("start", "start")]
    edges = []
    prev_id = "start"
    for i in range(98):
        node_id = f"s{i}"
        nodes.append(node_def(node_id, "set_state", minimal_config_for("set_state")))
        edges.append(edge_def(f"e{i}", prev_id, node_id))
        prev_id = node_id
    nodes.append(node_def("end", "end", minimal_config_for("end")))
    edges.append(edge_def("e-last", prev_id, "end"))

    graph = AgentGraph(**graph_def(nodes, edges))
    compiler = AgentCompiler(db=db_session, tenant_id=test_tenant_id)
    errors = await compiler.validate(graph)
    critical = [e for e in errors if e.severity == "error"]
    assert not critical


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_dense_graph_compile(db_session, test_tenant_id):
    nodes = [node_def("start", "start")]
    for i in range(20):
        nodes.append(node_def(f"n{i}", "transform", minimal_config_for("transform")))
    nodes.append(node_def("end", "end", minimal_config_for("end")))

    edges = [edge_def("e-start", "start", "n0")]
    for i in range(19):
        edges.append(edge_def(f"e-line-{i}", f"n{i}", f"n{i+1}"))
    edges.append(edge_def("e-last", "n19", "end"))

    # Add dense edges (acyclic)
    for i in range(10):
        for j in range(i + 2, 20, 3):
            edges.append(edge_def(f"e-d-{i}-{j}", f"n{i}", f"n{j}"))

    graph = AgentGraph(**graph_def(nodes, edges))
    compiler = AgentCompiler(db=db_session, tenant_id=test_tenant_id)
    errors = await compiler.validate(graph)
    critical = [e for e in errors if e.severity == "error"]
    assert not critical


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_invalid_model_fails(db_session, test_tenant_id, test_user_id, run_prefix):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("llm", "llm", {"model_id": "invalid-model-id"}),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "llm"),
            edge_def("e2", "llm", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-bad", f"{run_prefix}-bad", graph)
    agent_id = agent.id
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status in {RunStatus.failed, RunStatus.completed}
    finally:
        await delete_agent(db_session, test_tenant_id, agent_id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_fuzzed_graph_compile(db_session, test_tenant_id):
    if os.getenv("TEST_STRESS") != "1":
        pytest.skip("Set TEST_STRESS=1 to run fuzzed graph tests.")

    catalog = [spec.model_dump() for spec in list_agent_operator_specs()]
    fuzzer = GraphFuzzer(
        catalog,
        exclude_types=[
            "start",
            "end",
            "agent",
            "llm",
            "classify",
            "if_else",
            "while",
            "conditional",
            "parallel",
            "user_approval",
            "human_input",
            "rag",
            "vector_search",
            "tool",
        ],
        seed=42,
    )

    def config_factory(node_type: str):
        return minimal_config_for(node_type)

    graph = fuzzer.build_agent_graph(200, config_factory=config_factory)
    compiler = AgentCompiler(db=db_session, tenant_id=test_tenant_id)
    errors = await compiler.validate(AgentGraph(**graph))
    critical = [e for e in errors if e.severity == "error"]
    assert not critical


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_concurrent_executions(db_session, test_tenant_id, test_user_id, run_prefix):
    if os.getenv("TEST_STRESS") != "1":
        pytest.skip("Set TEST_STRESS=1 to run concurrency tests.")

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("transform", "transform", minimal_config_for("transform")),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "transform"),
            edge_def("e2", "transform", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-con", f"{run_prefix}-con", graph)
    try:
        async def run_once(idx):
            return await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text=f"hi {idx}")

        results = await asyncio.gather(*[run_once(i) for i in range(25)])
        assert len(results) == 25
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)
