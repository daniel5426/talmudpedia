import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base


class AgentStatus(str, enum.Enum):
    """Lifecycle status of an agent."""
    draft = "draft"
    published = "published"
    deprecated = "deprecated"
    archived = "archived"


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    
    # Graph Definition (DAG nodes and edges for visual builder)
    graph_definition = Column(JSONB, default={"nodes": [], "edges": []}, nullable=False)
    
    # Legacy simple config (kept for backward compatibility)
    model_provider = Column(String, nullable=True) 
    model_name = Column(String, nullable=True)
    temperature = Column(Float, default=0.7)
    system_prompt = Column(String, nullable=True)
    
    # Tool references (list of tool IDs/slugs)
    tools = Column(JSONB, default=[], nullable=False)
    
    # Referenced resources from graph (auto-populated on save)
    referenced_model_ids = Column(JSONB, default=[], nullable=False)
    referenced_tool_ids = Column(JSONB, default=[], nullable=False)
    
    # Configuration
    memory_config = Column(JSONB, default={
        "short_term_enabled": True,
        "short_term_max_messages": 20,
        "long_term_enabled": False,
        "long_term_index_id": None
    }, nullable=False)
    execution_constraints = Column(JSONB, default={
        "timeout_seconds": 300,
        "max_tokens": None,
        "max_iterations": 10,
        "allow_parallel_tools": True
    }, nullable=False)
    
    # Versioning & Status
    version = Column(Integer, default=1, nullable=False)
    status = Column(SQLEnum(AgentStatus), default=AgentStatus.draft, nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")
    runs = relationship("AgentRun", back_populates="agent", cascade="all, delete-orphan")


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)
    
    version = Column(Integer, nullable=False)
    config_snapshot = Column(JSONB, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    agent = relationship("Agent")


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    
    status = Column(SQLEnum(RunStatus), default=RunStatus.queued, nullable=False)
    
    input_params = Column(JSONB, default={})
    output_result = Column(JSONB, nullable=True)
    error_message = Column(String, nullable=True)
    
    usage_tokens = Column(Integer, default=0)
    cost = Column(String, nullable=True)
    
    trace_id = Column(String, nullable=True)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="runs")
    user = relationship("User")
    traces = relationship("AgentTrace", back_populates="run", cascade="all, delete-orphan")


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False, index=True)
    
    span_id = Column(String, nullable=False)
    parent_span_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    
    span_type = Column(String, nullable=False)
    
    inputs = Column(JSONB, nullable=True)
    outputs = Column(JSONB, nullable=True)
    
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata")
    
    # Relationships
    run = relationship("AgentRun", back_populates="traces")
