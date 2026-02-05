import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus

from tests.agent_builder_helpers import (
    create_agent,
    delete_agent,
    execute_agent_via_service,
    execute_agent_with_input_params,
    get_chat_model_slug,
    create_retrieval_setup,
    cleanup_retrieval_setup,
    graph_def,
    node_def,
    edge_def,
    minimal_config_for,
    full_config_for,
)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_control_and_data_nodes_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("transform", "transform", minimal_config_for("transform")),
            node_def("set_state", "set_state", minimal_config_for("set_state")),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "transform"),
            edge_def("e2", "transform", "set_state"),
            edge_def("e3", "set_state", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-ctrl", f"{run_prefix}-ctrl", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
        assert run.output_result.get("_node_outputs", {}).get("transform", {}).get("transform_output", {}).get("status") == "ok"
        assert run.output_result.get("_node_outputs", {}).get("end", {}).get("final_output") == "done"
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_agent_and_llm_nodes_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for LLM/Agent tests.")

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("agent", "agent", full_config_for("agent", chat_model_id=chat_model)),
            node_def("llm", "llm", full_config_for("llm", chat_model_id=chat_model)),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "agent"),
            edge_def("e2", "agent", "llm"),
            edge_def("e3", "llm", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-llm", f"{run_prefix}-llm", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
        assert "agent" in run.output_result.get("_node_outputs", {})
        assert "llm" in run.output_result.get("_node_outputs", {})
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_classify_and_if_else_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for classify tests.")

    classify_config = minimal_config_for("classify", chat_model_id=chat_model)
    if_else_config = {
        "conditions": [{"name": "yes", "expression": "contains(input, \"yes\")"}],
    }

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("classify", "classify", classify_config),
            node_def("if_else", "if_else", if_else_config),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "classify"),
            edge_def("e2", "classify", "if_else", source_handle="alpha"),
            edge_def("e3", "classify", "if_else", source_handle="else"),
            edge_def("e4", "if_else", "end", source_handle="yes"),
            edge_def("e5", "if_else", "end", source_handle="else"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-classify", f"{run_prefix}-classify", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="yes")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
        assert run.output_result.get("_node_outputs", {}).get("if_else", {}).get("branch_taken") in {"yes", "else"}
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_while_and_conditional_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    while_config = {
        "condition": "!has(loop_counters, \"while_node\")",
        "max_iterations": 3,
    }
    conditional_config = minimal_config_for("conditional")

    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("while_node", "while", while_config),
            node_def("transform", "transform", minimal_config_for("transform")),
            node_def("conditional", "conditional", conditional_config),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "while_node"),
            edge_def("e2", "while_node", "transform", source_handle="loop"),
            edge_def("e3", "transform", "while_node"),
            edge_def("e4", "while_node", "conditional", source_handle="exit"),
            edge_def("e5", "conditional", "end", source_handle="true"),
            edge_def("e6", "conditional", "end", source_handle="false"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-loop", f"{run_prefix}-loop", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="yes")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
        assert "loop_counters" in run.output_result
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_parallel_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("parallel", "parallel"),
            node_def("t1", "transform", minimal_config_for("transform")),
            node_def("t2", "transform", minimal_config_for("transform")),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "parallel"),
            edge_def("e2", "parallel", "t1"),
            edge_def("e3", "parallel", "t2"),
            edge_def("e4", "t1", "end"),
            edge_def("e5", "t2", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-parallel", f"{run_prefix}-parallel", graph)
    try:
        result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello")
        run = await db_session.get(AgentRun, result.run_id)
        assert run.status == RunStatus.completed
        outputs = run.output_result.get("_node_outputs", {})
        assert "t1" in outputs and "t2" in outputs
    finally:
        await delete_agent(db_session, test_tenant_id, agent.id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_user_approval_and_human_input_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    graph = graph_def(
        [
            node_def("start", "start"),
            node_def("approval", "user_approval"),
            node_def("human", "human_input"),
            node_def("end", "end", minimal_config_for("end")),
        ],
        [
            edge_def("e1", "start", "approval"),
            edge_def("e2", "approval", "human", source_handle="approve"),
            edge_def("e3", "approval", "human", source_handle="reject"),
            edge_def("e4", "human", "end"),
        ],
    )

    agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-hitl", f"{run_prefix}-hitl", graph)
    agent_id = agent.id
    try:
        run = await execute_agent_with_input_params(
            db_session,
            agent.id,
            {"approval": "approve", "input": "hello"},
        )
        assert run.status == RunStatus.completed
        assert run.output_result.get("_node_outputs", {}).get("approval", {}).get("approval_status") == "approved"
    finally:
        await delete_agent(db_session, test_tenant_id, agent_id)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_rag_and_vector_search_execute(db_session, test_tenant_id, test_user_id, run_prefix):
    pipeline_id, store_id, collection_name = await create_retrieval_setup(
        db_session, test_tenant_id, test_user_id, run_prefix
    )
    try:
        graph = graph_def(
            [
                node_def("start", "start"),
                node_def("rag", "rag", minimal_config_for("rag", pipeline_id=pipeline_id)),
                node_def("vector", "vector_search", minimal_config_for("vector_search", knowledge_store_id=store_id)),
                node_def("end", "end", minimal_config_for("end")),
            ],
            [
                edge_def("e1", "start", "rag"),
                edge_def("e2", "rag", "vector"),
                edge_def("e3", "vector", "end"),
            ],
        )
        agent = await create_agent(db_session, test_tenant_id, test_user_id, f"{run_prefix}-rag", f"{run_prefix}-rag", graph)
        try:
            result = await execute_agent_via_service(db_session, test_tenant_id, agent.id, test_user_id, input_text="hello retrieval")
            run = await db_session.get(AgentRun, result.run_id)
            assert run.status == RunStatus.completed
            outputs = run.output_result.get("_node_outputs", {})
            assert "rag" in outputs and "vector" in outputs
        finally:
            await delete_agent(db_session, test_tenant_id, agent.id)
    finally:
        await cleanup_retrieval_setup(db_session, pipeline_id, store_id, collection_name)
