from __future__ import annotations

import pytest

from app.api.routers.agents import NodeSchemaRequest, get_node_schemas
from app.api.routers.rag_operator_contracts import _operator_schema_payload, _pipeline_create_contract
from app.agent.executors.standard import register_standard_operators
from app.rag.pipeline.registry import (
    ConfigFieldSpec,
    ConfigFieldType,
    DataType,
    OperatorCategory,
    OperatorSpec,
)


def test_rag_operator_schema_payload_exposes_visual_node_and_create_contract_details():
    spec = OperatorSpec(
        operator_id="model_embedder",
        display_name="Model Embedder",
        category=OperatorCategory.EMBEDDING,
        description="Generate embeddings",
        input_type=DataType.CHUNKS,
        output_type=DataType.EMBEDDINGS,
        required_config=[
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                required=True,
                runtime=True,
                description="Embedding model",
            )
        ],
        optional_config=[
            ConfigFieldSpec(
                name="batch_size",
                field_type=ConfigFieldType.INTEGER,
                required=False,
                runtime=False,
                default=32,
                min_value=1,
            )
        ],
    )

    payload = _operator_schema_payload(spec)
    model_schema = payload["config_schema"]["properties"]["model_id"]

    assert payload["required_config_fields"] == ["model_id"]
    assert payload["optional_config_fields"] == ["batch_size"]
    assert payload["visual_node_contract"]["required_fields"] == ["id", "category", "operator", "position"]
    assert payload["visual_node_contract"]["field_shapes"]["operator"]["const"] == "model_embedder"
    assert payload["visual_node_contract"]["example_node"]["operator"] == "model_embedder"
    assert model_schema["anyOf"][0]["type"] == "string"
    assert model_schema["anyOf"][1]["required"] == ["runtime"]

    create_contract = _pipeline_create_contract()
    assert create_contract["required_fields"] == ["name", "nodes", "edges"]
    assert create_contract["edge_contract"]["required_fields"] == ["id", "source", "target"]


@pytest.mark.asyncio
async def test_agents_nodes_schema_exposes_graph_create_contract_details():
    register_standard_operators()

    response = await get_node_schemas(
        NodeSchemaRequest(node_types=["agent"]),
        _={},
        context={},
        db=None,
    )

    agent_schema = response["schemas"]["agent"]
    graph_node_contract = agent_schema["graph_node_contract"]

    assert response["graph_create_contract"]["required_fields"] == ["nodes", "edges"]
    assert response["graph_create_contract"]["edge_required_fields"] == ["id", "source", "target"]
    assert graph_node_contract["required_fields"] == ["id", "type", "position"]
    assert graph_node_contract["field_shapes"]["type"]["const"] == "agent"
    assert graph_node_contract["example_node"]["type"] == "agent"
