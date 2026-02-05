import itertools

import pytest

from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph

from tests.agent_builder_helpers import (
    list_agent_operator_types,
    minimal_config_for,
    routing_handles,
    graph_def,
    node_def,
    edge_def,
    get_chat_model_slug,
    create_retrieval_setup,
    cleanup_retrieval_setup,
)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_pairwise_connections_compile(db_session, test_tenant_id, test_user_id, run_prefix):
    chat_model = await get_chat_model_slug(db_session, test_tenant_id)
    if not chat_model:
        pytest.skip("No chat model available for pairwise tests.")

    pipeline_id = None
    store_id = None
    collection_name = None
    try:
        pipeline_id, store_id, collection_name = await create_retrieval_setup(
            db_session, test_tenant_id, test_user_id, run_prefix
        )
    except pytest.skip.Exception:
        pass

    node_types = [t for t in list_agent_operator_types() if t not in {"start", "end"}]
    if pipeline_id is None:
        node_types = [t for t in node_types if t != "rag"]
    if store_id is None:
        node_types = [t for t in node_types if t != "vector_search"]

    compiler = AgentCompiler(db=db_session, tenant_id=test_tenant_id)

    try:
        for idx, (a_type, b_type) in enumerate(itertools.product(node_types, node_types)):
            a_config = minimal_config_for(
                a_type,
                chat_model_id=chat_model,
                pipeline_id=pipeline_id,
                knowledge_store_id=store_id,
            )
            b_config = minimal_config_for(
                b_type,
                chat_model_id=chat_model,
                pipeline_id=pipeline_id,
                knowledge_store_id=store_id,
            )

            nodes = [
                node_def("start", "start"),
                node_def("node_a", a_type, a_config),
                node_def("node_b", b_type, b_config),
                node_def("end", "end", minimal_config_for("end")),
            ]

            edges = [edge_def(f"e{idx}-s", "start", "node_a")]

            a_handles = routing_handles(a_type, a_config)
            if a_handles:
                for handle in a_handles:
                    edges.append(edge_def(f"e{idx}-a-{handle}", "node_a", "node_b", source_handle=handle))
            else:
                edges.append(edge_def(f"e{idx}-a", "node_a", "node_b"))

            b_handles = routing_handles(b_type, b_config)
            if b_handles:
                for handle in b_handles:
                    edges.append(edge_def(f"e{idx}-b-{handle}", "node_b", "end", source_handle=handle))
            else:
                edges.append(edge_def(f"e{idx}-b", "node_b", "end"))

            graph = AgentGraph(**graph_def(nodes, edges))
            errors = await compiler.validate(graph)
            critical = [e for e in errors if e.severity == "error"]
            assert not critical
    finally:
        if pipeline_id and store_id and collection_name:
            await cleanup_retrieval_setup(db_session, pipeline_id, store_id, collection_name)
