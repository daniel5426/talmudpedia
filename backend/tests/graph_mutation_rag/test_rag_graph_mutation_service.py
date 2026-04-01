from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.graph_mutation_service import GraphMutationError, apply_graph_operations
from app.services.rag_graph_mutation_service import RagGraphMutationService


def _pipeline_graph() -> dict:
    return {
        "nodes": [
            {"id": "input_1", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "lookup_1",
                "category": "retrieval",
                "operator": "knowledge_store_lookup",
                "position": {"x": 220, "y": 0},
                "config": {"knowledge_store_id": "ks-a", "top_k": 5},
            },
        ],
        "edges": [{"id": "e1", "source": "input_1", "target": "lookup_1"}],
    }


def _service() -> RagGraphMutationService:
    service = RagGraphMutationService.__new__(RagGraphMutationService)
    service.tenant_id = uuid4()
    service.registry = SimpleNamespace(
        get=lambda _operator, tenant_id=None: SimpleNamespace(
            required_config=[],
            optional_config=[SimpleNamespace(name="knowledge_store_id"), SimpleNamespace(name="top_k")],
        )
    )
    return service


def test_rag_graph_mutation_operations_preserve_edges_and_patch_config():
    service = _service()

    mutation = apply_graph_operations(
        _pipeline_graph(),
        [{"op": "set_node_config_value", "node_id": "lookup_1", "path": "top_k", "value": 8}],
        validate_node_config_path=service._validate_node_config_path,
    )

    lookup = next(node for node in mutation.graph["nodes"] if node["id"] == "lookup_1")
    assert lookup["config"]["top_k"] == 8
    assert mutation.graph["edges"] == _pipeline_graph()["edges"]
    assert mutation.changed_node_ids == ["lookup_1"]


def test_rag_graph_mutation_rejects_unknown_config_field():
    service = _service()

    with pytest.raises(GraphMutationError) as exc_info:
        apply_graph_operations(
            _pipeline_graph(),
            [{"op": "set_node_config_value", "node_id": "lookup_1", "path": "temperature", "value": 0.3}],
            validate_node_config_path=service._validate_node_config_path,
        )

    assert exc_info.value.errors[0]["code"] == "GRAPH_MUTATION_UNKNOWN_CONFIG_FIELD"


@pytest.mark.asyncio
async def test_rag_apply_patch_persists_incomplete_graph_and_returns_advisory_diagnostics():
    pipeline_id = uuid4()
    service = _service()
    calls = {"committed": False}

    pipeline = SimpleNamespace(
        id=pipeline_id,
        tenant_id=service.tenant_id,
        org_unit_id=None,
        name="FAQ Pipeline",
        description="desc",
        nodes=_pipeline_graph()["nodes"],
        edges=_pipeline_graph()["edges"],
        pipeline_type="retrieval",
        version=1,
        is_published=False,
        updated_at=None,
    )

    async def _get_pipeline(_pipeline_id):
        return pipeline

    async def _commit():
        calls["committed"] = True

    async def _refresh(_pipeline):
        return None

    service._get_pipeline = _get_pipeline
    service._compile_preview = lambda _pipeline, _graph: SimpleNamespace(success=False, errors=[{"code": "VALIDATION_ERROR", "message": "bad graph"}], warnings=[])
    service.db = SimpleNamespace(commit=_commit, refresh=_refresh)

    result = await service.apply_patch(
        pipeline_id,
        [{"op": "set_node_config_value", "node_id": "lookup_1", "path": "top_k", "value": 9}],
    )

    assert calls["committed"] is True
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"][0]["code"] == "VALIDATION_ERROR"
