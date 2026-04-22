from __future__ import annotations

import pytest

from app.api.routers.agents import NodeSchemaRequest, get_node_schemas
from app.graph_authoring import rag_instance_contract, rag_node_spec
from app.agent.executors.standard import register_standard_operators
from app.rag.pipeline.registry import (
    ConfigFieldSpec,
    ConfigFieldType,
    DataType,
    OperatorCategory,
    OperatorSpec,
)


def test_rag_operator_schema_payload_exposes_canonical_authoring_contract():
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

    payload = rag_node_spec(spec).model_dump(mode="json", exclude_none=True)
    model_schema = payload["config_schema"]["properties"]["model_id"]

    assert payload["type"] == "model_embedder"
    assert payload["title"] == "Model Embedder"
    assert payload["input_type"] == "chunks"
    assert payload["output_type"] == "embeddings"
    assert payload["config_schema"]["required"] == ["model_id"]
    assert payload["config_schema"]["x-ui"]["order"] == ["model_id", "batch_size"]
    assert model_schema["x-ui"]["widget"] == "model"
    assert rag_instance_contract()["required_fields"] == ["name", "nodes", "edges"]


@pytest.mark.asyncio
async def test_agents_nodes_schema_exposes_canonical_instance_contract(monkeypatch):
    register_standard_operators()

    async def _empty_artifacts(self, ctx):
        return {}

    monkeypatch.setattr(
        "app.services.control_plane.agents_admin_service.AgentAdminService._artifact_specs_with_catalog",
        _empty_artifacts,
    )

    response = await get_node_schemas(
        NodeSchemaRequest(node_types=["agent"]),
        _={},
        context={
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "project_id": None,
            "user": None,
            "auth_token": None,
            "scopes": [],
            "is_service": False,
        },
        db=None,
    )

    agent_schema = response["specs"]["agent"]

    assert response["instance_contract"]["required_fields"] == ["nodes", "edges"]
    assert response["instance_contract"]["edge_required_fields"] == ["id", "source", "target"]
    assert agent_schema["type"] == "agent"
    assert agent_schema["title"] == "Agent"
    assert agent_schema["graph_hints"]["editor"] == "generic"
    assert "model_id" in agent_schema["config_schema"]["required"]
