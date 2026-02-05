from __future__ import annotations

from typing import Any, Dict, List, Optional

from .pipeline import Agent
from .nodes import Node


class AgentGraphBuilder:
    """
    Convenience builder for agent graphs with routing helpers.
    """

    def __init__(self, name: str, description: str = ""):
        self.agent = Agent(name, description)

    def add(self, *nodes: Node) -> "AgentGraphBuilder":
        self.agent.add(*nodes)
        return self

    def connect(
        self,
        source: Node,
        target: Node,
        source_handle: Optional[str] = None,
        target_handle: Optional[str] = None,
    ) -> "AgentGraphBuilder":
        self.agent.connect(source, target, source_handle=source_handle, target_handle=target_handle)
        return self

    def connect_condition(self, source: Node, branch_name: str, target: Node) -> "AgentGraphBuilder":
        return self.connect(source, target, source_handle=branch_name)

    def connect_router_all(self, source: Node, target: Node) -> "AgentGraphBuilder":
        for handle in self._handles_for(source):
            self.connect(source, target, source_handle=handle)
        return self

    def connect_while(self, source: Node, loop_target: Node, exit_target: Node) -> "AgentGraphBuilder":
        self.connect(source, loop_target, source_handle="loop")
        self.connect(source, exit_target, source_handle="exit")
        return self

    def connect_user_approval(self, source: Node, approve_target: Node, reject_target: Node) -> "AgentGraphBuilder":
        self.connect(source, approve_target, source_handle="approve")
        self.connect(source, reject_target, source_handle="reject")
        return self

    def connect_conditional(self, source: Node, true_target: Node, false_target: Node) -> "AgentGraphBuilder":
        self.connect(source, true_target, source_handle="true")
        self.connect(source, false_target, source_handle="false")
        return self

    def to_payload(self) -> Dict[str, Any]:
        return self.agent.to_payload()

    def to_graphspec(self, spec_version: str = "1.0") -> Dict[str, Any]:
        payload = self.agent.to_payload()
        payload["spec_version"] = spec_version
        return payload

    def create(self, client, slug: str) -> str:
        return self.agent.create(client, slug=slug)

    def execute(
        self,
        client,
        agent_id: str = None,
        input_text: str = None,
        messages: List[Dict[str, Any]] = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        return self.agent.execute(
            client,
            agent_id=agent_id,
            input_text=input_text,
            messages=messages,
            context=context,
        )

    def _handles_for(self, node: Node) -> List[str]:
        node_type = getattr(node, "node_type", node.node_type if hasattr(node, "node_type") else None) or node.node_type
        config = node.config or {}
        if node_type == "if_else":
            conditions = config.get("conditions", [])
            handles = [c.get("name") or f"condition_{i}" for i, c in enumerate(conditions)]
            handles.append("else")
            return handles
        if node_type == "classify":
            categories = config.get("categories", [])
            return [c.get("name") or f"category_{i}" for i, c in enumerate(categories)]
        if node_type == "while":
            return ["loop", "exit"]
        if node_type == "user_approval":
            return ["approve", "reject"]
        if node_type == "conditional":
            return ["true", "false"]
        return []
