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
    
    def __init__(self, tenant_id: Optional[UUID] = None, db: Any = None):
        self.tenant_id = tenant_id
        self.db = db

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
            if node.type in (NodeType.LLM_CALL, NodeType.LLM):
                if not node.config.get("model_id"):
                    errors.append(ValidationError(node_id=node.id, message="LLM Call node must have a model_id"))
            elif node.type == NodeType.TOOL_CALL:
                if not node.config.get("tool_id"):
                    errors.append(ValidationError(node_id=node.id, message="Tool Call node must have a tool_id"))
                    
        return errors

    async def compile(self, agent_id: UUID, version: int, graph: AgentGraph, memory_config: Any, execution_constraints: Any) -> ExecutableAgent:
        """
        Compiles the validated graph into an executable format.
        """
        from langgraph.graph import StateGraph, END
        from app.agent.core.state import AgentState
        
        # Initialize the StateGraph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        for node in graph.nodes:
            node_fn = self._build_node_fn(node)
            workflow.add_node(node.id, node_fn)
            
        # Add edges
        for edge in graph.edges:
            # TODO: Handle conditional edges if needed (EdgeType.CONTROL with condition)
            # For now assuming simple control flow based on source -> target
            workflow.add_edge(edge.source, edge.target)
            
        # Set entry point
        input_nodes = graph.get_input_nodes()
        if input_nodes:
            workflow.set_entry_point(input_nodes[0].id)
            
        # Determine exit points (nodes pointing to output)
        output_nodes = graph.get_output_nodes()
        
        # In our schema, we have explicit OUTPUT nodes.
        # We need to ensure clear paths to END.
        # For LangGraph, we usually edge `last_node -> END`. 
        # Here, "output" nodes are the end.
        for node in output_nodes:
             workflow.add_edge(node.id, END)

        # Build config object
        config = {
            "agent_id": str(agent_id),
            "version": version,
            "memory": memory_config,
            "constraints": execution_constraints
        }

        # Compile
        compiled_graph = workflow.compile()
        
        return ExecutableAgent(graph_definition=graph, compiled_graph=compiled_graph, config=config)

    def _build_node_fn(self, node: AgentNode):
        """Builds a callable (async) function for a graph node."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
        
        async def input_node(state: Any):
            # Pass-through or initial processing
            return state

        async def output_node(state: Any):
            return state

        async def llm_node(state: Any):
            # Resolve Model
            if not self.db or not self.tenant_id:
                # Fallback to mock if no dependencies provided (or raise error)
                logger.warning("AgentCompiler: Missing db/tenant_id, using mock LLM response.")
                return {
                    "steps": [f"Executed {node.id} (Mock)"],
                    "reasoning_steps_parsed": [{"type": "log", "content": f"Executed node {node.id} (Mock)"}],
                    "messages": [AIMessage(content=f"Processed by {node.id}: {state.get('query', 'no query')}")],
                }

            from app.services.model_resolver import ModelResolver
            
            model_id = node.config.get("model_id")
            if not model_id:
                raise ValueError(f"Node {node.id} missing model_id config")
                
            resolver = ModelResolver(self.db, self.tenant_id)
            try:
                provider = await resolver.resolve(model_id)
            except Exception as e:
                logger.error(f"Failed to resolve model {model_id}: {e}")
                raise ValueError(f"Failed to resolve model: {e}")

            # Prepare Messages
            # Ensure they are BaseMessage instances or dictionaries compatible with the provider
            current_messages = state.get("messages", [])
            formatted_messages = []
            
            for msg in current_messages:
                if isinstance(msg, dict):
                    role = msg.get("role")
                    content = msg.get("content")
                    if role == "user":
                        formatted_messages.append(HumanMessage(content=content))
                    elif role == "assistant":
                        formatted_messages.append(AIMessage(content=content))
                    elif role == "system":
                        formatted_messages.append(SystemMessage(content=content))
                    else:
                        formatted_messages.append(HumanMessage(content=str(content))) # Fallback
                elif isinstance(msg, BaseMessage):
                    formatted_messages.append(msg)
                else:
                    formatted_messages.append(HumanMessage(content=str(msg)))

            # System Prompt from Config? 
            system_prompt = node.config.get("system_prompt", None)
            
            # Execute
            try:
                response = await provider.generate(formatted_messages, system_prompt=system_prompt)
                
                # Logic to parse response into steps/reasoning if applicable?
                # For now, raw response
                
                return {
                    "steps": [f"Executed LLM Node {node.id}"],
                    "reasoning_steps_parsed": [{"type": "log", "content": f"Executed LLM: {model_id}"}],
                    "messages": [response],
                }
            except Exception as e:
                logger.error(f"LLM execution failed: {e}")
                return {
                    "reasoning_steps_parsed": [{"type": "error", "content": str(e)}],
                    "messages": [AIMessage(content=f"Error executing LLM: {str(e)}")]
                }

            
        async def tool_node(state: Any):
            # Placeholder for tool execution
            return {"steps": [f"Executed Tool {node.id}"]}

        if node.type in (NodeType.INPUT, NodeType.START):
            return input_node
        elif node.type in (NodeType.OUTPUT, NodeType.END):
            return output_node
        elif node.type in (NodeType.LLM_CALL, NodeType.LLM):
            return llm_node
        elif node.type == NodeType.TOOL_CALL:
            return tool_node
        else:
            # Fallback for generic nodes
            async def generic_node(state: Any):
                return state
            return generic_node
