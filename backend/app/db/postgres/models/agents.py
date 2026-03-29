import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Integer, Float, UniqueConstraint, Index, text
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
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
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

    # Workload provisioning metadata (security control plane).
    workload_scope_profile = Column(String, nullable=False, default="default_agent_run")
    workload_scope_overrides = Column(JSONB, default=[], nullable=False)
    
    # Versioning & Status
    version = Column(Integer, default=1, nullable=False)
    status = Column(SQLEnum(AgentStatus), default=AgentStatus.draft, nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    show_in_playground = Column(Boolean, default=True, nullable=False, server_default=text("true"))
    default_embed_policy_set_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resource_policy_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")
    default_embed_policy_set = relationship("ResourcePolicySet", foreign_keys=[default_embed_policy_set_id])
    runs = relationship("AgentRun", back_populates="agent", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_agent_tenant_slug"),
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    version = Column(Integer, nullable=False)
    config_snapshot = Column(JSONB, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    agent = relationship("Agent")


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    status = Column(SQLEnum(RunStatus), default=RunStatus.queued, nullable=False)
    
    input_params = Column(JSONB, default={})
    output_result = Column(JSONB, nullable=True)
    checkpoint = Column(JSONB, nullable=True)  # Store suspended state for resuming
    error_message = Column(String, nullable=True)
    
    usage_tokens = Column(Integer, default=0)
    cost = Column(String, nullable=True)
    
    trace_id = Column(String, nullable=True)
    workload_principal_id = Column(UUID(as_uuid=True), ForeignKey("workload_principals.id", ondelete="SET NULL"), nullable=True, index=True)
    delegation_grant_id = Column(UUID(as_uuid=True), ForeignKey("delegation_grants.id", ondelete="SET NULL"), nullable=True, index=True)
    initiator_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    surface = Column(String, nullable=True, index=True)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="SET NULL"), nullable=True, index=True)
    published_app_account_id = Column(UUID(as_uuid=True), ForeignKey("published_app_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    external_user_id = Column(String(255), nullable=True, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="SET NULL"), nullable=True, index=True)
    base_revision_id = Column(UUID(as_uuid=True), ForeignKey("published_app_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    result_revision_id = Column(UUID(as_uuid=True), ForeignKey("published_app_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    requested_model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_binding_id = Column(UUID(as_uuid=True), ForeignKey("model_provider_bindings.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_provider = Column(String, nullable=True, index=True)
    resolved_provider_model_id = Column(String, nullable=True)
    usage_source = Column(String, nullable=True, index=True)
    cost_source = Column(String, nullable=True, index=True)
    context_window_json = Column(JSONB, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    cached_input_tokens = Column(Integer, nullable=True)
    cached_output_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    usage_breakdown_json = Column(JSONB, nullable=True)
    cost_usd = Column(Float, nullable=True)
    cost_breakdown_json = Column(JSONB, nullable=True)
    pricing_snapshot_json = Column(JSONB, nullable=True)
    execution_engine = Column(String, nullable=False, default="opencode", server_default=text("'opencode'"), index=True)
    engine_run_ref = Column(String, nullable=True)
    has_workspace_writes = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    batch_finalized_at = Column(DateTime(timezone=True), nullable=True)

    # Orchestration lineage and idempotency
    root_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_node_id = Column(String, nullable=True)
    depth = Column(Integer, nullable=False, default=0)
    spawn_key = Column(String, nullable=True)
    orchestration_group_id = Column(UUID(as_uuid=True), ForeignKey("orchestration_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    agent = relationship("Agent", back_populates="runs")
    user = relationship("User", foreign_keys=[user_id])
    initiator_user = relationship("User", foreign_keys=[initiator_user_id])
    published_app = relationship("PublishedApp", foreign_keys=[published_app_id])
    published_app_account = relationship("PublishedAppAccount", foreign_keys=[published_app_account_id])
    thread = relationship("AgentThread", foreign_keys=[thread_id])
    base_revision = relationship("PublishedAppRevision", foreign_keys=[base_revision_id])
    result_revision = relationship("PublishedAppRevision", foreign_keys=[result_revision_id])
    requested_model = relationship("ModelRegistry", foreign_keys=[requested_model_id])
    resolved_model = relationship("ModelRegistry", foreign_keys=[resolved_model_id])
    resolved_binding = relationship("ModelProviderBinding", foreign_keys=[resolved_binding_id])
    root_run = relationship("AgentRun", remote_side=[id], foreign_keys=[root_run_id], post_update=True)
    parent_run = relationship("AgentRun", remote_side=[id], foreign_keys=[parent_run_id], backref="child_runs")
    orchestration_group = relationship("OrchestrationGroup", foreign_keys=[orchestration_group_id])
    thread_turn = relationship("AgentThreadTurn", back_populates="run", uselist=False)
    traces = relationship("AgentTrace", back_populates="run", cascade="all, delete-orphan")
    invocations = relationship("AgentRunInvocation", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("parent_run_id", "spawn_key", name="uq_agent_runs_parent_spawn_key"),
        Index("ix_agent_runs_root_created_at", "root_run_id", "created_at"),
        Index("ix_agent_runs_parent_created_at", "parent_run_id", "created_at"),
        Index("ix_agent_runs_thread_created_at", "thread_id", "created_at"),
        Index(
            "ix_agent_runs_coding_scope_status_created_at",
            "surface",
            "published_app_id",
            "published_app_account_id",
            "initiator_user_id",
            "status",
            "created_at",
        ),
    )

class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    
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


class AgentRunInvocation(Base):
    __tablename__ = "agent_run_invocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    node_id = Column(String, nullable=True)
    node_name = Column(String, nullable=True)
    node_type = Column(String, nullable=True)
    model_id = Column(String, nullable=True)
    resolved_provider = Column(String, nullable=True)
    resolved_provider_model_id = Column(String, nullable=True)
    usage_source = Column(String, nullable=False, default="unknown", server_default=text("'unknown'"), index=True)
    context_source = Column(String, nullable=False, default="unknown", server_default=text("'unknown'"))
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    cached_input_tokens = Column(Integer, nullable=True)
    cached_output_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    context_input_tokens = Column(Integer, nullable=True)
    max_context_tokens = Column(Integer, nullable=True)
    max_context_tokens_source = Column(String, nullable=True)
    payload_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("AgentRun", back_populates="invocations")

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_run_invocations_run_sequence"),
        Index("ix_agent_run_invocations_run_sequence", "run_id", "sequence"),
    )
