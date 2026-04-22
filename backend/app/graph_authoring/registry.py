from __future__ import annotations

from typing import Optional

from app.agent.executors.standard import register_standard_operators
from app.agent.registry import AgentOperatorRegistry
from app.graph_authoring.agent_specs import agent_node_spec
from app.graph_authoring.rag_specs import rag_node_spec
from app.graph_authoring.types import NodeAuthoringSpec
from app.rag.pipeline.registry import OperatorRegistry


AGENT_NODE_TYPE_ALIASES = {
    "input": "start",
    "start": "start",
    "output": "end",
    "end": "end",
    "tool_call": "tool",
    "tool": "tool",
    "rag_retrieval": "rag",
    "rag_pipeline": "rag",
    "rag": "rag",
}


def normalize_agent_node_type(node_type: object) -> str:
    return AGENT_NODE_TYPE_ALIASES.get(str(node_type or "").strip(), str(node_type or "").strip())


def get_agent_authoring_spec(node_type: object) -> Optional[NodeAuthoringSpec]:
    normalized = normalize_agent_node_type(node_type)
    if not normalized or normalized.startswith("artifact:"):
        return None
    register_standard_operators()
    spec = AgentOperatorRegistry.get(normalized)
    if spec is None:
        return None
    return agent_node_spec(spec)


def get_rag_authoring_spec(
    operator_id: object,
    *,
    organization_id: str | None = None,
    registry: OperatorRegistry | None = None,
) -> Optional[NodeAuthoringSpec]:
    normalized = str(operator_id or "").strip()
    if not normalized:
        return None
    resolved_registry = registry or OperatorRegistry.get_instance()
    spec = resolved_registry.get(normalized, organization_id=organization_id)
    if spec is None:
        return None
    return rag_node_spec(spec)
