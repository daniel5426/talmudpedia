import logging
from typing import Any, Optional, Union
from uuid import UUID
from pydantic import BaseModel

from .schema import AgentGraph, AgentNode, AgentEdge, NodeType, EdgeType
from .executable import ExecutableAgent

logger = logging.getLogger(__name__)

class ValidationError(BaseModel):
    """Validation error for agent graph."""
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    message: str
    severity: str = "error"


class AgentCompiler:
    """
    Compiles an AgentGraph definition into an ExecutableAgent.
    
    This handles validation, normalization, and conversion to LangGraph state machine.
    """
    
    async def validate(self, graph: AgentGraph) -> list[ValidationError]:
        """Validate the graph structure and configuration."""
        errors = []
        
        # 1. Check for exactly one input node
        input_nodes = graph.get_input_nodes()
        if not input_nodes:
            errors.append(ValidationError(message="Graph must have at least one input node"))
        elif len(input_nodes) > 1:
            errors.append(ValidationError(message="Graph cannot have more than one input node"))
            
        # 2. Check for at least one output node
        output_nodes = graph.get_output_nodes()
        if not output_nodes:
            errors.append(ValidationError(message="Graph must have at least one output node"))
            
        # 3. Check for disconnected nodes (except entry/exit)
        all_node_ids = {n.id for n in graph.nodes}
        connected_node_ids = set()
        for edge in graph.edges:
            connected_node_ids.add(edge.source)
            connected_node_ids.add(edge.target)
            
        disconnected = all_node_ids - connected_node_ids
        for node_id in disconnected:
            # Entry/exit can be single nodes if the graph is trivial, but usually they should be connected
            if len(all_node_ids) > 1:
                errors.append(ValidationError(node_id=node_id, message=f"Node '{node_id}' is not connected to any other node"))
                
        # 4. Check for cycles (non-loop nodes)
        # TODO: Implement cycle detection for non-loop constructs
        
        # 5. Type-specific validation
        for node in graph.nodes:
            if node.type == NodeType.LLM_CALL:
                if not node.config.get("model_id"):
                    errors.append(ValidationError(node_id=node.id, message="LLM Call node must have a model_id"))
            elif node.type == NodeType.TOOL_CALL:
                if not node.config.get("tool_id"):
                    errors.append(ValidationError(node_id=node.id, message="Tool Call node must have a tool_id"))
                    
        return errors

    async def compile(self, graph: AgentGraph, config: dict[str, Any]) -> ExecutableAgent:
        """
        Compiles the validated graph into an executable format.
        
        Currently, this creates an ExecutableAgent that will build a LangGraph at runtime.
        """
        # In a more advanced implementation, this would generate the actual StateGraph here
        # and perhaps even serialize it. For now, it's a wrapper that knows how to build it.
        
        return ExecutableAgent(graph_definition=graph, config=config)
