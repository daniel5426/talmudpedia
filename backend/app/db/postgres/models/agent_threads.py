import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class AgentThreadStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class AgentThreadSurface(str, enum.Enum):
    internal = "internal"
    published_host_runtime = "published_host_runtime"
    preview_runtime = "preview_runtime"
    artifact_admin = "artifact_admin"
    embedded_runtime = "embedded_runtime"


class AgentThreadTurnStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class AgentThread(Base):
    __tablename__ = "agent_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    app_account_id = Column(UUID(as_uuid=True), ForeignKey("published_app_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    tenant_api_key_id = Column(UUID(as_uuid=True), ForeignKey("tenant_api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="SET NULL"), nullable=True, index=True)
    external_user_id = Column(String(255), nullable=True, index=True)
    external_session_id = Column(String(255), nullable=True, index=True)
    surface = Column(SQLEnum(AgentThreadSurface), nullable=False, default=AgentThreadSurface.internal, index=True)
    title = Column(String(255), nullable=True)
    status = Column(SQLEnum(AgentThreadStatus), nullable=False, default=AgentThreadStatus.active, index=True)
    last_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    user = relationship("User")
    app_account = relationship("PublishedAppAccount")
    tenant_api_key = relationship("TenantAPIKey")
    agent = relationship("Agent")
    published_app = relationship("PublishedApp")
    last_run = relationship("AgentRun", foreign_keys=[last_run_id])
    turns = relationship(
        "AgentThreadTurn",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AgentThreadTurn.turn_index",
    )
    attachments = relationship(
        "RuntimeAttachment",
        back_populates="thread",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agent_threads_scope_activity", "tenant_id", "user_id", "last_activity_at"),
        Index("ix_agent_threads_app_account_activity", "tenant_id", "app_account_id", "last_activity_at"),
        Index("ix_agent_threads_embed_activity", "tenant_id", "agent_id", "external_user_id", "last_activity_at"),
    )


class AgentThreadTurn(Base):
    __tablename__ = "agent_thread_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    turn_index = Column(Integer, nullable=False)
    user_input_text = Column(Text, nullable=True)
    assistant_output_text = Column(Text, nullable=True)
    status = Column(SQLEnum(AgentThreadTurnStatus), nullable=False, default=AgentThreadTurnStatus.running, index=True)
    usage_tokens = Column(Integer, nullable=False, default=0)
    metadata_ = Column(JSONB, nullable=False, default=dict, name="metadata")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    thread = relationship("AgentThread", back_populates="turns")
    run = relationship("AgentRun", foreign_keys=[run_id], back_populates="thread_turn")
    attachment_links = relationship(
        "AgentThreadTurnAttachment",
        back_populates="turn",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agent_thread_turns_thread_turn_index", "thread_id", "turn_index"),
    )
