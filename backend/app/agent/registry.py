import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.agent.executors.base import BaseNodeExecutor

logger = logging.getLogger(__name__)


class AgentStateField(str, Enum):
    """
    Enum representing different fields in the AgentState.
    Used to define read/write contracts for operators.
    """
    MESSAGE_HISTORY = "messages"       # The conversation history
    TOOL_CALLS = "tool_calls"          # Pending tool calls
    OBSERVATIONS = "tool_outputs"      # Results from tool executions
    MEMORY = "memory"                  # Short/Long term memory state
    ROUTING_KEY = "next"               # Control flow decision
    FINAL_OUTPUT = "final_output"      # Final response to user
    CONTEXT = "context"                # Global context variables


class AgentOperatorSpec(BaseModel):
    """
    Definition of an Agent Operator (Node).
    Describes its contract, configuration, and UI representation.
    """
    type: str = Field(..., description="Unique identifier for the node type (e.g., 'llm', 'tool')")
    category: str = Field(..., description="Visual category for the builder palette")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Brief description of what the node does")
    
    # Contract
    reads: List[AgentStateField] = Field(default_factory=list, description="State fields this node reads")
    writes: List[AgentStateField] = Field(default_factory=list, description="State fields this node mutates")
    
    # Configuration
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for the node configuration")
    
    # UI Metadata
    ui: Dict[str, Any] = Field(default_factory=dict, description="Frontend metadata (icon, color, etc.)")


class AgentOperatorRegistry:
    """
    Registry for all available Agent Operators.
    Used by the frontend to populate the node catalog.
    """
    _instance = None
    _operators: Dict[str, AgentOperatorSpec] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentOperatorRegistry, cls).__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, spec: AgentOperatorSpec):
        """Register a new operator specification."""
        if spec.type in cls._operators:
            logger.warning(f"Overwriting existing operator registration: {spec.type}")
        cls._operators[spec.type] = spec
        logger.info(f"Registered agent operator: {spec.type}")

    @classmethod
    def get(cls, node_type: str) -> Optional[AgentOperatorSpec]:
        """Get an operator specification by type."""
        return cls._operators.get(node_type)

    @classmethod
    def list_operators(cls) -> List[AgentOperatorSpec]:
        """List all registered operators."""
        return list(cls._operators.values())


class AgentExecutorRegistry:
    """
    Registry mapping node types to their Executor implementation classes.
    Used by the backend to execute nodes.
    """
    _instance = None
    _executors: Dict[str, Type['BaseNodeExecutor']] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentExecutorRegistry, cls).__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, node_type: str, executor_cls: Type['BaseNodeExecutor']):
        """Register an executor class for a node type."""
        cls._executors[node_type] = executor_cls
        logger.info(f"Registered executor for: {node_type}")

    @classmethod
    def get_executor_cls(cls, node_type: str) -> Optional[Type['BaseNodeExecutor']]:
        """Get the executor class for a node type."""
        return cls._executors.get(node_type)
