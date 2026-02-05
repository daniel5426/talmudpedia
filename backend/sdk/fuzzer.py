from __future__ import annotations

import random
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional


class GraphFuzzer:
    """
    Generate randomized agent graphs for limit testing.
    """

    def __init__(
        self,
        catalog: Iterable[Dict[str, Any]],
        exclude_types: Optional[Iterable[str]] = None,
        seed: Optional[int] = None,
    ):
        self._rng = random.Random(seed)
        self._exclude = set(exclude_types or [])
        self._specs_by_type = {}
        self._types: List[str] = []
        for spec in catalog:
            node_type = spec.get("type")
            if not node_type:
                continue
            if node_type in self._exclude or str(node_type).startswith("artifact:"):
                continue
            self._specs_by_type[node_type] = spec
            self._types.append(node_type)

    def build_linear_graph(
        self,
        size: int,
        config_factory: Optional[Callable[[str], Dict[str, Any]]] = None,
        spec_version: str = "1.0",
    ) -> Dict[str, Any]:
        if size < 2:
            raise ValueError("size must be >= 2")
        node_types = self._pick_node_types(size)
        nodes = [self._node_dict(node_types[i], f"n{i}", config_factory) for i in range(size)]
        edges = []
        for i in range(size - 1):
            edges.append(self._edge_dict(f"e{i}", nodes[i]["id"], nodes[i + 1]["id"]))
        return {"spec_version": spec_version, "nodes": nodes, "edges": edges}

    def build_random_graph(
        self,
        size: int,
        max_edges_per_node: int = 3,
        allow_cycles: bool = False,
        config_factory: Optional[Callable[[str], Dict[str, Any]]] = None,
        spec_version: str = "1.0",
    ) -> Dict[str, Any]:
        if size < 2:
            raise ValueError("size must be >= 2")
        node_types = self._pick_node_types(size)
        nodes = [self._node_dict(node_types[i], f"n{i}", config_factory) for i in range(size)]

        edges: List[Dict[str, Any]] = []
        for i in range(size - 1):
            edges.append(self._edge_dict(f"e{i}", nodes[i]["id"], nodes[i + 1]["id"]))

        edge_id = size - 1
        for i in range(size):
            for _ in range(self._rng.randint(0, max_edges_per_node)):
                src_idx = i
                tgt_idx = self._rng.randint(0, size - 1)
                if not allow_cycles and tgt_idx <= src_idx:
                    continue
                if src_idx == tgt_idx:
                    continue
                edges.append(self._edge_dict(f"e{edge_id}", nodes[src_idx]["id"], nodes[tgt_idx]["id"]))
                edge_id += 1

        return {"spec_version": spec_version, "nodes": nodes, "edges": edges}

    def build_agent_graph(
        self,
        size: int,
        config_factory: Optional[Callable[[str], Dict[str, Any]]] = None,
        spec_version: str = "1.0",
    ) -> Dict[str, Any]:
        """
        Build a graph with an explicit start and end node.
        """
        if size < 2:
            raise ValueError("size must be >= 2")
        middle_count = max(0, size - 2)
        middle_types = self._pick_node_types(middle_count)
        node_types = ["start"] + middle_types + ["end"]
        nodes = [self._node_dict(node_types[i], f"n{i}", config_factory) for i in range(size)]
        edges = []
        for i in range(size - 1):
            edges.append(self._edge_dict(f"e{i}", nodes[i]["id"], nodes[i + 1]["id"]))
        return {"spec_version": spec_version, "nodes": nodes, "edges": edges}

    def _pick_node_types(self, size: int) -> List[str]:
        if not self._types:
            raise ValueError("No node types available to fuzz.")
        return [self._rng.choice(self._types) for _ in range(size)]

    def _node_dict(
        self,
        node_type: str,
        node_id: Optional[str] = None,
        config_factory: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        config = config_factory(node_type) if config_factory else {}
        node_id = node_id or str(uuid.uuid4())
        return {
            "id": node_id,
            "type": node_type,
            "position": {"x": 0, "y": 0},
            "config": config or {},
        }

    def _edge_dict(self, edge_id: str, source: str, target: str) -> Dict[str, Any]:
        return {
            "id": edge_id,
            "source": source,
            "target": target,
        }

    def required_fields_for(self, node_type: str) -> List[str]:
        spec = self._specs_by_type.get(node_type, {})
        schema = spec.get("config_schema") or {}
        return schema.get("required", []) if isinstance(schema, dict) else []
