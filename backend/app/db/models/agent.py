"""
Agent Definition Models - Versioned, immutable agent workflow definitions.

Agents are DAG-based workflow definitions that compose models, tools, and RAG
capabilities. Definitions are immutable once published; modifications create
new versions.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from .base import MongoModel, PyObjectId


class AgentStatus(str, Enum):
    """Lifecycle status of an agent."""
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class NodeType(str, Enum):
    """Types of nodes in an agent graph."""
    INPUT = "input"              # Entry point
    OUTPUT = "output"            # Exit point
    LLM_CALL = "llm_call"        # Model invocation
    TOOL_CALL = "tool_call"      # Tool execution
    CONDITIONAL = "conditional"  # Branching logic
    LOOP = "loop"                # Iteration
    PARALLEL = "parallel"        # Fan-out execution
    TRANSFORM = "transform"      # Data transformation


class EdgeType(str, Enum):
    """Types of edges in an agent graph."""
    CONTROL = "control"  # Execution flow
    DATA = "data"        # Data dependency


class AgentNodePosition(BaseModel):
    """Position of a node in the visual editor."""
    x: float
    y: float
    
    model_config = ConfigDict(extra="forbid")


class AgentNode(BaseModel):
    """A node in the agent graph."""
    id: str
    type: NodeType
    position: AgentNodePosition
    config: dict[str, Any] = Field(default_factory=dict)
    """
    Config varies by node type:
    - LLM_CALL: {model_id: str, system_prompt?: str, temperature?: float}
    - TOOL_CALL: {tool_id: str, input_mapping?: dict}
    - CONDITIONAL: {condition: str, branches: list[str]}
    - TRANSFORM: {expression: str}
    """
    
    model_config = ConfigDict(extra="forbid")


class AgentEdge(BaseModel):
    """An edge connecting nodes in the agent graph."""
    id: str
    source: str  # Source node ID
    target: str  # Target node ID
    type: EdgeType = EdgeType.CONTROL
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    condition: Optional[str] = None  # For conditional edges
    
    model_config = ConfigDict(extra="forbid")


class AgentGraph(BaseModel):
    """The complete graph definition of an agent."""
    nodes: list[AgentNode] = Field(default_factory=list)
    edges: list[AgentEdge] = Field(default_factory=list)
    
    model_config = ConfigDict(extra="forbid")


class MemoryConfig(BaseModel):
    """Configuration for agent memory."""
    short_term_enabled: bool = True
    short_term_max_messages: int = 20
    long_term_enabled: bool = False
    long_term_index_id: Optional[str] = None  # RAG index for long-term memory
    
    model_config = ConfigDict(extra="forbid")


class ExecutionConstraints(BaseModel):
    """Constraints for agent execution."""
    timeout_seconds: int = 300
    max_tokens: Optional[int] = None
    max_iterations: int = 10
    allow_parallel_tools: bool = True
    
    model_config = ConfigDict(extra="forbid")


class AgentDefinition(MongoModel):
    """
    A versioned, immutable agent workflow definition.
    
    Defines a DAG of nodes (LLM calls, tools, conditionals) that compose
    into an executable reasoning workflow.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    slug: str  # Unique within tenant
    description: Optional[str] = None
    
    # Graph definition
    graph: AgentGraph = Field(default_factory=AgentGraph)
    
    # Referenced resources (validated at compile time)
    referenced_model_ids: list[str] = Field(default_factory=list)
    referenced_tool_ids: list[str] = Field(default_factory=list)
    
    # Configuration
    memory_config: MemoryConfig = Field(default_factory=MemoryConfig)
    execution_constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)
    
    # Versioning
    version: int = 1
    status: AgentStatus = AgentStatus.DRAFT
    
    # Multi-tenancy
    tenant_id: PyObjectId
    
    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[PyObjectId] = None
    updated_by: Optional[PyObjectId] = None
    published_at: Optional[datetime] = None

    class Config:
        collection_name = "agent_definitions"


class AgentVersion(MongoModel):
    """
    Snapshot of a published agent version.
    
    When an agent is published, a snapshot is created for rollback
    and audit purposes.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    agent_id: PyObjectId
    version: int
    
    # Snapshot of the agent at publish time
    graph_snapshot: AgentGraph
    memory_config_snapshot: MemoryConfig
    execution_constraints_snapshot: ExecutionConstraints
    
    # Diff tracking (optional, for UI display)
    diff_from_previous: Optional[dict[str, Any]] = None
    
    # Audit
    published_by: PyObjectId
    published_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        collection_name = "agent_versions"
