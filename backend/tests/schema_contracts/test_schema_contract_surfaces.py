from __future__ import annotations

import pytest

from app.graph_authoring import artifact_node_spec
from app.api.routers.agents import NodeSchemaRequest, get_node_schemas
from app.graph_authoring import rag_catalog_item, rag_instance_contract, rag_node_spec
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
    assert payload["input_schema"]["type"] == "array"
    assert payload["config_schema"]["required"] == ["model_id"]
    assert payload["config_schema"]["x-ui"]["order"] == ["model_id", "batch_size"]
    assert model_schema["x-ui"]["widget"] == "model"
    assert model_schema["x-ui"]["runtime"] is True
    assert payload["node_template"] == {
        "id": "node_id",
        "operator": "model_embedder",
        "category": "embedding",
        "position": {"x": 0, "y": 0},
        "config": {"batch_size": 32},
    }
    assert payload["normalization_defaults"] == {"batch_size": 32}
    assert rag_catalog_item(spec).required_config_fields == []
    assert rag_instance_contract()["required_fields"] == ["name", "nodes", "edges"]
    assert rag_instance_contract()["optional_fields"] == ["description", "pipeline_type"]
    assert "org_unit_id" not in rag_instance_contract()["top_level_schema"]["properties"]
    assert rag_instance_contract()["top_level_schema"]["required"] == ["name", "nodes", "edges"]
    assert rag_instance_contract()["node_required_fields"] == ["id", "operator", "position", "category"]


def test_rag_operator_schema_preserves_numeric_and_json_field_constraints():
    spec = OperatorSpec(
        operator_id="custom_lookup",
        display_name="Custom Lookup",
        category=OperatorCategory.RETRIEVAL,
        description="Lookup data",
        input_type=DataType.QUERY,
        output_type=DataType.SEARCH_RESULTS,
        required_config=[
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                required=True,
                default=10,
                min_value=1,
                max_value=50,
            ),
            ConfigFieldSpec(
                name="filters",
                field_type=ConfigFieldType.JSON,
                required=False,
                json_schema={
                    "type": "object",
                    "properties": {"kind": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
        ],
        is_custom=True,
        artifact_id="artifact-1",
        artifact_revision_id="rev-1",
    )

    payload = rag_node_spec(spec).model_dump(mode="json", exclude_none=True)
    top_k = payload["config_schema"]["properties"]["top_k"]
    filters = payload["config_schema"]["properties"]["filters"]

    assert top_k["minimum"] == 1
    assert top_k["maximum"] == 50
    assert top_k["default"] == 10
    assert filters["type"] == "object"
    assert filters["properties"]["kind"]["type"] == "string"
    assert filters["additionalProperties"] is False
    assert payload["node_template"]["operator"] == "custom_lookup"
    assert payload["node_template"]["config"] == {"top_k": 10}
    assert payload["normalization_defaults"] == {"top_k": 10}


def test_rag_operator_schema_exposes_union_shape_for_web_crawler_start_urls():
    from app.rag.pipeline.registry import OperatorRegistry

    spec = OperatorRegistry.get_instance().get("web_crawler")
    payload = rag_node_spec(spec).model_dump(mode="json", exclude_none=True)
    start_urls = payload["config_schema"]["properties"]["start_urls"]

    assert "oneOf" in start_urls
    assert start_urls["oneOf"] == [
        {"type": "string"},
        {"type": "array", "items": {"type": "string"}},
    ]


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
    assert response["instance_contract"]["top_level_schema"]["required"] == ["nodes", "edges"]
    assert response["instance_contract"]["edge_required_fields"] == ["id", "source", "target"]
    assert response["instance_contract"]["node_required_fields"] == ["id", "type", "position"]
    assert agent_schema["type"] == "agent"
    assert agent_schema["title"] == "Agent"
    assert agent_schema["graph_hints"]["editor"] == "generic"
    assert "model_id" in agent_schema["config_schema"]["required"]
    assert agent_schema["node_template"]["type"] == "agent"
    assert agent_schema["node_template"]["position"] == {"x": 0, "y": 0}
    assert agent_schema["node_template"]["config"]["include_chat_history"] is True
    assert agent_schema["normalization_defaults"]["reasoning_effort"] == "medium"
    assert "input_schema" not in agent_schema


@pytest.mark.asyncio
async def test_agents_nodes_schema_preserves_canonical_route_table_field(monkeypatch):
    register_standard_operators()

    async def _empty_artifacts(self, ctx):
        return {}

    monkeypatch.setattr(
        "app.services.control_plane.agents_admin_service.AgentAdminService._artifact_specs_with_catalog",
        _empty_artifacts,
    )

    response = await get_node_schemas(
        NodeSchemaRequest(node_types=["router"]),
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

    router_schema = response["specs"]["router"]["config_schema"]

    assert "route_table" in router_schema["properties"]
    assert "routes" not in router_schema["properties"]


def test_artifact_backed_agent_node_schema_uses_enriched_shape():
    spec, _ = artifact_node_spec(
        artifact_id="artifact-1",
        artifact_revision_id="rev-1",
        display_name="Artifact Node",
        description="Artifact-backed node",
        config_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["draft", "published"], "default": "draft"},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        node_ui={"inputType": "any", "outputType": "context"},
    )

    payload = spec.model_dump(mode="json", exclude_none=True)

    assert payload["input_schema"]["properties"]["query"]["type"] == "string"
    assert payload["node_template"] == {
        "id": "node_id",
        "type": "artifact:artifact-1",
        "position": {"x": 0, "y": 0},
        "config": {"mode": "draft"},
    }
    assert payload["normalization_defaults"] == {"mode": "draft"}
