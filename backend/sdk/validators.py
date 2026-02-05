from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import jsonschema


class GraphSpecValidator:
    """
    Validate agent graph nodes against catalog-provided config_schema.
    """

    def __init__(self, catalog: Iterable[Dict[str, Any]]):
        self._specs = {}
        for spec in catalog:
            node_type = spec.get("type")
            if node_type:
                self._specs[node_type] = spec

    def validate_graph(self, graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Validate all nodes in a graph.

        Returns a list of error dicts: {node_id, node_type, message}
        """
        errors: List[Dict[str, Any]] = []
        nodes = graph.get("nodes", [])
        for node in nodes:
            errors.extend(self.validate_node(node))
        return errors

    def validate_node(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        errors: List[Dict[str, Any]] = []
        node_type = self._normalize_type(node.get("type", ""))
        spec = self._specs.get(node_type)
        if not spec:
            return [{
                "node_id": node.get("id"),
                "node_type": node.get("type"),
                "message": f"Unknown node type: {node.get('type')}",
            }]

        schema = spec.get("config_schema") or {}
        if not schema:
            return []

        try:
            jsonschema.validate(instance=node.get("config", {}) or {}, schema=schema)
        except jsonschema.ValidationError as exc:
            errors.append({
                "node_id": node.get("id"),
                "node_type": node.get("type"),
                "message": f"Config error: {exc.message}",
            })
        return errors

    def _normalize_type(self, node_type: str) -> str:
        mapping = {
            "input": "start",
            "start": "start",
            "output": "end",
            "end": "end",
            "llm_call": "llm",
            "llm": "llm",
            "tool_call": "tool",
            "rag_retrieval": "rag",
        }
        return mapping.get(str(node_type), str(node_type))
