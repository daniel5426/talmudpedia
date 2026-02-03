"""
Graph Schema - Pydantic models for agent graph validation.
"""
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class NodeType(str, Enum):
    """Types of nodes in an agent graph."""
    INPUT = "input"
    START = "start" # Alias for INPUT
    OUTPUT = "output"
    END = "end" # Alias for OUTPUT
    LLM_CALL = "llm_call"
    LLM = "llm" # Alias for LLM_CALL
    TOOL_CALL = "tool_call"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    PARALLEL = "parallel"
    TRANSFORM = "transform"
    RAG_RETRIEVAL = "rag_retrieval"
    HUMAN_INPUT = "human_input"


class EdgeType(str, Enum):
    """Types of edges in an agent graph."""
    CONTROL = "control"
    DATA = "data"


class AgentNodePosition(BaseModel):
    """Position of a node in the visual editor."""
    x: float
    y: float
    model_config = ConfigDict(extra="ignore")


class AgentNode(BaseModel):
    """A node in the agent graph."""
    id: str
    type: NodeType
    position: AgentNodePosition
    label: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    data: Optional[dict[str, Any]] = None # React Flow data support
    
    # Field mapping for artifacts: maps input field names to expressions
    # Example: {"documents": "{{ upstream.ingest_node.output }}", "query": "{{ state.messages[-1].content }}"}
    input_mappings: Optional[dict[str, str]] = None
    
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode='before')
    @classmethod
    def lift_config_from_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Check if config is provided at top level
            if "config" not in data or not data["config"]:
                # Try to find it in data.config
                node_data = data.get("data", {})
                if node_data and isinstance(node_data, dict) and "config" in node_data:
                    data["config"] = node_data["config"]
        return data


class AgentEdge(BaseModel):
    """An edge connecting nodes in the agent graph."""
    id: str
    source: str
    target: str
    type: EdgeType = EdgeType.CONTROL
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    label: Optional[str] = None
    condition: Optional[str] = None
    model_config = ConfigDict(extra="ignore")


class AgentGraph(BaseModel):
    """The complete graph definition of an agent."""
    nodes: list[AgentNode] = Field(default_factory=list)
    edges: list[AgentEdge] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")
    
    def get_node(self, node_id: str) -> Optional[AgentNode]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_input_nodes(self) -> list[AgentNode]:
        return [n for n in self.nodes if n.type in (NodeType.INPUT, NodeType.START)]
    
    def get_output_nodes(self) -> list[AgentNode]:
        return [n for n in self.nodes if n.type in (NodeType.OUTPUT, NodeType.END)]
    
    def get_outgoing_edges(self, node_id: str) -> list[AgentEdge]:
        return [e for e in self.edges if e.source == node_id]
    
    def get_incoming_edges(self, node_id: str) -> list[AgentEdge]:
        return [e for e in self.edges if e.target == node_id]


class MemoryConfig(BaseModel):
    """Configuration for agent memory."""
    short_term_enabled: bool = True
    short_term_max_messages: int = 20
    long_term_enabled: bool = False
    long_term_index_id: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class ExecutionConstraints(BaseModel):
    """Constraints for agent execution."""
    timeout_seconds: int = 300
    max_tokens: Optional[int] = None
    max_iterations: int = 10
    allow_parallel_tools: bool = True
    model_config = ConfigDict(extra="forbid")
