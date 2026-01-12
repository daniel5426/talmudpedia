"""
Tool Registry - Callable capability contracts.

Tools are platform capabilities exposed to agents via versioned schemas.
Agents invoke tools by contract, never by implementation.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import Field

from .base import MongoModel, PyObjectId


class ToolImplementationType(str, Enum):
    """How the tool is implemented."""
    INTERNAL = "internal"       # Platform-native implementation
    HTTP = "http"               # External HTTP endpoint
    RAG_RETRIEVAL = "rag_retrieval"  # RAG pipeline retrieval
    FUNCTION = "function"       # Python function
    CUSTOM = "custom"


class ToolStatus(str, Enum):
    """Lifecycle status of a tool."""
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class ToolFailurePolicy(str, Enum):
    """How to handle tool execution failures."""
    FAIL_FAST = "fail_fast"     # Abort the entire agent run
    CONTINUE = "continue"       # Mark failed, continue execution


class ToolRetryConfig(MongoModel):
    """Retry configuration for tool execution."""
    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000


class ToolExecutionConfig(MongoModel):
    """Execution configuration for a tool."""
    timeout_seconds: int = 30
    retry_config: ToolRetryConfig = Field(default_factory=ToolRetryConfig)
    failure_policy: ToolFailurePolicy = ToolFailurePolicy.FAIL_FAST
    circuit_breaker_threshold: int = 5  # Consecutive failures before disable


class ToolDefinition(MongoModel):
    """
    A tool definition with versioned input/output schemas.
    
    Tools represent callable capabilities that agents can invoke.
    The schema defines the contract; implementation is resolved at runtime.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str  # Display name
    slug: str  # Unique identifier within tenant
    description: str
    
    # Schema (JSON Schema format)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    
    # Implementation
    implementation_type: ToolImplementationType
    implementation_config: dict[str, Any] = Field(default_factory=dict)
    """
    Config depends on implementation_type:
    - HTTP: {"endpoint": "...", "method": "POST", "headers": {...}}
    - RAG_RETRIEVAL: {"pipeline_id": "...", "index_id": "..."}
    - FUNCTION: {"module": "...", "function": "..."}
    """
    
    # Execution
    execution_config: ToolExecutionConfig = Field(default_factory=ToolExecutionConfig)
    
    # Versioning
    version: str = "1.0.0"  # Semver
    status: ToolStatus = ToolStatus.DRAFT
    
    # Multi-tenancy
    tenant_id: PyObjectId
    
    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[PyObjectId] = None
    updated_by: Optional[PyObjectId] = None
    published_at: Optional[datetime] = None

    class Config:
        collection_name = "tool_definitions"


class ToolExecutionStatus(str, Enum):
    """Status of a tool execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ToolExecution(MongoModel):
    """
    Record of a tool execution for observability.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    tool_id: PyObjectId
    tool_version: str
    agent_run_id: Optional[PyObjectId] = None  # If invoked by an agent
    
    # Input/Output
    input: dict[str, Any] = Field(default_factory=dict)
    output: Optional[dict[str, Any]] = None
    
    # Status
    status: ToolExecutionStatus = ToolExecutionStatus.PENDING
    error: Optional[str] = None
    attempt_count: int = 1
    
    # Metrics
    duration_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Context
    tenant_id: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        collection_name = "tool_executions"
