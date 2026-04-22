from __future__ import annotations

from typing import Any

from app.graph_authoring.normalizers.base import apply_schema_defaults
from app.graph_authoring.registry import get_rag_authoring_spec
from app.rag.pipeline.compiler import PipelineEdge, PipelineNode
from app.rag.pipeline.registry import OperatorRegistry


def normalize_rag_graph_definition(
    graph_definition: dict[str, Any],
    *,
    organization_id: str | None = None,
    registry: OperatorRegistry | None = None,
) -> dict[str, Any]:
    resolved_registry = registry or OperatorRegistry.get_instance()
    normalized_nodes = [
        _normalize_pipeline_node(node, organization_id=organization_id, registry=resolved_registry)
        for node in list(graph_definition.get("nodes") or [])
    ]
    normalized_edges = [
        PipelineEdge(**edge).model_dump()
        for edge in list(graph_definition.get("edges") or [])
    ]
    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }


def _normalize_pipeline_node(
    raw_node: dict[str, Any],
    *,
    organization_id: str | None,
    registry: OperatorRegistry,
) -> dict[str, Any]:
    node = dict(raw_node or {})
    operator_id = str(node.get("operator") or "").strip()
    raw_spec = registry.get(operator_id, organization_id=organization_id)
    spec = (
        get_rag_authoring_spec(operator_id, organization_id=organization_id, registry=registry)
        if raw_spec is not None and hasattr(raw_spec, "operator_id")
        else None
    )
    config = node.get("config") if isinstance(node.get("config"), dict) else {}
    node["config"] = apply_schema_defaults(spec.config_schema if spec else None, config)
    if spec is not None:
        node["category"] = spec.category
    return PipelineNode(**node).model_dump()
