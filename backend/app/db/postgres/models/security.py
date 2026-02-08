import uuid
import enum

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Integer,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class WorkloadPrincipalType(str, enum.Enum):
    AGENT = "agent"
    ARTIFACT = "artifact"
    TOOL = "tool"
    SYSTEM = "system"


class WorkloadResourceType(str, enum.Enum):
    AGENT = "agent"
    ARTIFACT = "artifact"
    TOOL = "tool"


class WorkloadPolicyStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DelegationGrantStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkloadPrincipal(Base):
    __tablename__ = "workload_principals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    principal_type = Column(
        SQLEnum(
            WorkloadPrincipalType,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    creator = relationship("User")

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_workload_principal_tenant_slug"),
    )


class WorkloadPrincipalBinding(Base):
    __tablename__ = "workload_principal_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_id = Column(UUID(as_uuid=True), ForeignKey("workload_principals.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(
        SQLEnum(
            WorkloadResourceType,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    resource_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    principal = relationship("WorkloadPrincipal")
    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_workload_binding_resource"),
    )


class WorkloadScopePolicy(Base):
    __tablename__ = "workload_scope_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    principal_id = Column(UUID(as_uuid=True), ForeignKey("workload_principals.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_scopes = Column(JSONB, default=list, nullable=False)
    approved_scopes = Column(JSONB, default=list, nullable=False)
    status = Column(
        SQLEnum(
            WorkloadPolicyStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=WorkloadPolicyStatus.PENDING,
    )
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    principal = relationship("WorkloadPrincipal")
    approver = relationship("User")

    __table_args__ = (
        UniqueConstraint("principal_id", "version", name="uq_workload_policy_principal_version"),
    )


class DelegationGrant(Base):
    __tablename__ = "delegation_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_id = Column(UUID(as_uuid=True), ForeignKey("workload_principals.id", ondelete="CASCADE"), nullable=False, index=True)
    initiator_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    requested_scopes = Column(JSONB, default=list, nullable=False)
    effective_scopes = Column(JSONB, default=list, nullable=False)
    status = Column(
        SQLEnum(
            DelegationGrantStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DelegationGrantStatus.ACTIVE,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    principal = relationship("WorkloadPrincipal")
    initiator = relationship("User")


class TokenJTIRegistry(Base):
    __tablename__ = "token_jti_registry"

    jti = Column(String, primary_key=True)
    grant_id = Column(UUID(as_uuid=True), ForeignKey("delegation_grants.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    grant = relationship("DelegationGrant")


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    action_scope = Column(String, nullable=False)
    status = Column(
        SQLEnum(
            ApprovalStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rationale = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    decider = relationship("User")

    __table_args__ = (
        Index("ix_approval_subject", "tenant_id", "subject_type", "subject_id"),
    )
