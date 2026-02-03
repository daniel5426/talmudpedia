from typing import List, Dict, Any, Union
import uuid
import requests

from .nodes import Node

class Pipeline:
    """
    Builder for RAG Pipelines.
    """
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.nodes: List[Node] = []
        self.edges: List[Dict[str, Any]] = []
        self._node_map = {}

    def add(self, *nodes: Node):
        """Add nodes to the pipeline."""
        for node in nodes:
            if not node.id:
                node.id = str(uuid.uuid4())
            self.nodes.append(node)
            self._node_map[node.id] = node
        return self

    def connect(self, source: Node, target: Node, source_handle: str = None, target_handle: str = None):
        """Connect two nodes."""
        if source.id not in self._node_map:
            self.add(source)
        if target.id not in self._node_map:
            self.add(target)
            
        edge = {
            "id": f"e-{source.id}-{target.id}",
            "source": source.id,
            "target": target.id,
            "source_handle": source_handle,
            "target_handle": target_handle
        }
        self.edges.append(edge)
        return self

    def to_payload(self) -> Dict[str, Any]:
        """Generate API payload."""
        return {
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges,
            "pipeline_type": "ingestion" # Default
        }

    def create(self, client, pipeline_type: str = "ingestion") -> str:
        """Submit pipeline to backend."""
        payload = self.to_payload()
        payload["pipeline_type"] = pipeline_type
        
        # Router mounted at /admin/pipelines, endpoint is /visual-pipelines
        resp = requests.post(
            f"{client.base_url}/admin/pipelines/visual-pipelines",
            json=payload,
            headers=client.headers
        )
        resp.raise_for_status()
        return resp.json()["id"]


class Agent(Pipeline):
    """
    Builder for Agents (extends Pipeline as logic is similar).
    """
    def to_payload(self) -> Dict[str, Any]:
        # Agent API expects "graph_definition": { nodes, edges } wrapped in request
        # Agents API is weird: 
        # POST /api/agents expects `name`, `slug`, `graph_definition`...
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges
        }

    def create(self, client, slug: str) -> str:
        """Submit agent to backend."""
        payload = {
            "name": self.name,
            "slug": slug,
            "description": self.description,
            "graph_definition": self.to_payload(),
            "memory_config": {},
            "execution_constraints": {}
        }
        
        resp = requests.post(
            f"{client.base_url}/api/agents",
            json=payload,
            headers=client.headers
        )
        resp.raise_for_status()
        return resp.json()["id"]
