from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class ArtifactScope(str, enum.Enum):
    RAG = "rag"
    AGENT = "agent"
    BOTH = "both"
    TOOL = "tool"


class ArtifactStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class ArtifactRunDomain(str, enum.Enum):
    TEST = "test"
    AGENT = "agent"
    RAG = "rag"
    TOOL = "tool"


class ArtifactRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    slug = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=False, default="custom")
    input_type = Column(String, nullable=False, default="raw_documents")
    output_type = Column(String, nullable=False, default="raw_documents")
    scope = Column(
        SQLEnum(ArtifactScope, values_callable=_enum_values),
        nullable=False,
        default=ArtifactScope.RAG,
    )
    status = Column(
        SQLEnum(ArtifactStatus, values_callable=_enum_values),
        nullable=False,
        default=ArtifactStatus.DRAFT,
    )

    latest_draft_revision_id = Column(UUID(as_uuid=True), ForeignKey("artifact_revisions.id", ondelete="SET NULL"), nullable=True)
    latest_published_revision_id = Column(UUID(as_uuid=True), ForeignKey("artifact_revisions.id", ondelete="SET NULL"), nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    legacy_custom_operator_id = Column(UUID(as_uuid=True), ForeignKey("custom_operators.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    creator = relationship("User", foreign_keys=[created_by])
    revisions = relationship(
        "ArtifactRevision",
        back_populates="artifact",
        primaryjoin="Artifact.id == ArtifactRevision.artifact_id",
        cascade="all, delete-orphan",
    )
    latest_draft_revision = relationship("ArtifactRevision", foreign_keys=[latest_draft_revision_id], post_update=True)
    latest_published_revision = relationship("ArtifactRevision", foreign_keys=[latest_published_revision_id], post_update=True)

    __table_args__ = (
        Index("uq_artifacts_tenant_slug", "tenant_id", "slug", unique=True),
    )


class ArtifactRevision(Base):
    __tablename__ = "artifact_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    revision_number = Column(Integer, nullable=False, default=1)
    version_label = Column(String, nullable=False, default="draft")
    is_published = Column(Boolean, nullable=False, default=False)
    is_ephemeral = Column(Boolean, nullable=False, default=False)

    display_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=False, default="custom")
    input_type = Column(String, nullable=False, default="raw_documents")
    output_type = Column(String, nullable=False, default="raw_documents")
    scope = Column(
        SQLEnum(ArtifactScope, values_callable=_enum_values),
        nullable=False,
        default=ArtifactScope.RAG,
    )

    source_code = Column(Text, nullable=True)
    source_files = Column(JSONB, nullable=False, default=list)
    entry_module_path = Column(String, nullable=False, default="handler.py")
    manifest_json = Column(JSONB, nullable=False, default=dict)
    python_dependencies = Column(JSONB, nullable=False, default=list)
    config_schema = Column(JSONB, nullable=False, default=list)
    inputs = Column(JSONB, nullable=False, default=list)
    outputs = Column(JSONB, nullable=False, default=list)
    reads = Column(JSONB, nullable=False, default=list)
    writes = Column(JSONB, nullable=False, default=list)

    build_hash = Column(String(64), nullable=False, default="", index=True)
    dependency_hash = Column(String(64), nullable=False, default="")
    bundle_hash = Column(String(64), nullable=False, default="", index=True)
    bundle_storage_key = Column(String, nullable=True)
    bundle_inline_bytes = Column(LargeBinary, nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    artifact = relationship("Artifact", back_populates="revisions", foreign_keys=[artifact_id])
    tenant = relationship("Tenant")
    creator = relationship("User", foreign_keys=[created_by])


class ArtifactRun(Base):
    __tablename__ = "artifact_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True, index=True)
    revision_id = Column(UUID(as_uuid=True), ForeignKey("artifact_revisions.id", ondelete="CASCADE"), nullable=False, index=True)

    domain = Column(
        SQLEnum(ArtifactRunDomain, values_callable=_enum_values),
        nullable=False,
        default=ArtifactRunDomain.TEST,
    )
    status = Column(
        SQLEnum(ArtifactRunStatus, values_callable=_enum_values),
        nullable=False,
        default=ArtifactRunStatus.QUEUED,
        index=True,
    )
    queue_class = Column(String, nullable=False, default="artifact_test")
    sandbox_backend = Column(String, nullable=False, default="cloudflare_workers")
    worker_id = Column(String, nullable=True)
    sandbox_session_id = Column(String, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)

    input_payload = Column(JSONB, nullable=False, default=dict)
    config_payload = Column(JSONB, nullable=False, default=dict)
    context_payload = Column(JSONB, nullable=False, default=dict)
    result_payload = Column(JSONB, nullable=True)
    error_payload = Column(JSONB, nullable=True)
    stdout_excerpt = Column(Text, nullable=True)
    stderr_excerpt = Column(Text, nullable=True)
    runtime_metadata = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    tenant = relationship("Tenant")
    artifact = relationship("Artifact")
    revision = relationship("ArtifactRevision")
    events = relationship("ArtifactRunEvent", back_populates="run", cascade="all, delete-orphan")


class ArtifactRunEvent(Base):
    __tablename__ = "artifact_run_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("artifact_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)

    run = relationship("ArtifactRun", back_populates="events")

    __table_args__ = (
        Index("uq_artifact_run_events_run_sequence", "run_id", "sequence", unique=True),
    )


class ArtifactDeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class ArtifactDeployment(Base):
    __tablename__ = "artifact_deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id = Column(UUID(as_uuid=True), ForeignKey("artifact_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    namespace = Column(String, nullable=False)
    build_hash = Column(String(64), nullable=False, index=True)
    status = Column(
        SQLEnum(ArtifactDeploymentStatus, values_callable=_enum_values),
        nullable=False,
        default=ArtifactDeploymentStatus.PENDING,
    )
    worker_name = Column(String, nullable=False)
    script_name = Column(String, nullable=False)
    deployment_id = Column(String, nullable=True)
    version_id = Column(String, nullable=True)
    runtime_metadata = Column(JSONB, nullable=False, default=dict)
    error_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    revision = relationship("ArtifactRevision")

    __table_args__ = (
        Index("uq_artifact_deployments_namespace_build_hash", "tenant_id", "namespace", "build_hash", unique=True),
    )


class ArtifactTenantRuntimePolicy(Base):
    __tablename__ = "artifact_tenant_runtime_policies"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    interactive_concurrency_limit = Column(Integer, nullable=False, default=5)
    background_concurrency_limit = Column(Integer, nullable=False, default=2)
    test_concurrency_limit = Column(Integer, nullable=False, default=2)
    interactive_cpu_ms = Column(Integer, nullable=False, default=30000)
    background_cpu_ms = Column(Integer, nullable=False, default=60000)
    test_cpu_ms = Column(Integer, nullable=False, default=30000)
    interactive_subrequests = Column(Integer, nullable=False, default=50)
    background_subrequests = Column(Integer, nullable=False, default=100)
    test_subrequests = Column(Integer, nullable=False, default=50)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
