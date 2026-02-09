import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class OrchestratorPolicy(Base):
    __tablename__ = "orchestrator_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    orchestrator_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)

    is_active = Column(Boolean, nullable=False, default=True)
    enforce_published_only = Column(Boolean, nullable=False, default=True)

    default_failure_policy = Column(String, nullable=False, default="best_effort")
    max_depth = Column(Integer, nullable=False, default=3)
    max_fanout = Column(Integer, nullable=False, default=8)
    max_children_total = Column(Integer, nullable=False, default=32)
    join_timeout_s = Column(Integer, nullable=False, default=60)

    # Optional scope whitelist for child token minting.
    allowed_scope_subset = Column(JSONB, nullable=False, default=list)

    capability_manifest_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    orchestrator_agent = relationship("Agent")

    __table_args__ = (
        UniqueConstraint("tenant_id", "orchestrator_agent_id", name="uq_orchestrator_policy_agent"),
    )


class OrchestratorTargetAllowlist(Base):
    __tablename__ = "orchestrator_target_allowlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    orchestrator_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)

    target_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True)
    target_agent_slug = Column(String, nullable=True)
    capability_tag = Column(String, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    orchestrator_agent = relationship("Agent", foreign_keys=[orchestrator_agent_id])
    target_agent = relationship("Agent", foreign_keys=[target_agent_id])

    __table_args__ = (
        Index(
            "ix_orchestrator_target_allowlists_orch_slug",
            "orchestrator_agent_id",
            "target_agent_slug",
        ),
    )


class OrchestrationGroup(Base):
    __tablename__ = "orchestration_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    orchestrator_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_node_id = Column(String, nullable=True)

    failure_policy = Column(String, nullable=False, default="best_effort")
    join_mode = Column(String, nullable=False, default="all")
    quorum_threshold = Column(Integer, nullable=True)
    timeout_s = Column(Integer, nullable=False, default=60)
    status = Column(String, nullable=False, default="running")

    policy_snapshot = Column(JSONB, nullable=False, default=dict)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    orchestrator_run = relationship("AgentRun", foreign_keys=[orchestrator_run_id])
    members = relationship("OrchestrationGroupMember", back_populates="group", cascade="all, delete-orphan")


class OrchestrationGroupMember(Base):
    __tablename__ = "orchestration_group_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("orchestration_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="queued")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    group = relationship("OrchestrationGroup", back_populates="members")
    run = relationship("AgentRun")

    __table_args__ = (
        UniqueConstraint("group_id", "run_id", name="uq_orchestration_group_member"),
    )
