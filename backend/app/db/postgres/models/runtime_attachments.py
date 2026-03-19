import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base
from .agent_threads import AgentThreadSurface


class RuntimeAttachmentKind(str, enum.Enum):
    image = "image"
    document = "document"
    audio = "audio"


class RuntimeAttachmentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processed = "processed"
    failed = "failed"


class RuntimeAttachment(Base):
    __tablename__ = "runtime_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("agent_threads.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    app_account_id = Column(UUID(as_uuid=True), ForeignKey("published_app_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    tenant_api_key_id = Column(UUID(as_uuid=True), ForeignKey("tenant_api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="SET NULL"), nullable=True, index=True)
    external_user_id = Column(String(255), nullable=True, index=True)
    external_session_id = Column(String(255), nullable=True, index=True)
    surface = Column(SQLEnum(AgentThreadSurface), nullable=False, index=True)
    kind = Column(SQLEnum(RuntimeAttachmentKind), nullable=False, index=True)
    mime_type = Column(String(255), nullable=False)
    filename = Column(String(1024), nullable=False)
    byte_size = Column(Integer, nullable=False)
    storage_key = Column(String(2048), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False, index=True)
    status = Column(SQLEnum(RuntimeAttachmentStatus), nullable=False, default=RuntimeAttachmentStatus.uploaded, index=True)
    processing_error = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)
    metadata_ = Column(JSONB, nullable=False, default=dict, name="metadata")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    thread = relationship("AgentThread", back_populates="attachments")
    user = relationship("User")
    app_account = relationship("PublishedAppAccount")
    tenant_api_key = relationship("TenantAPIKey")
    agent = relationship("Agent")
    published_app = relationship("PublishedApp")
    turn_links = relationship(
        "AgentThreadTurnAttachment",
        back_populates="attachment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_runtime_attachments_scope_lookup", "tenant_id", "surface", "thread_id", "created_at"),
        Index("ix_runtime_attachments_embed_lookup", "tenant_id", "agent_id", "external_user_id", "created_at"),
    )


class AgentThreadTurnAttachment(Base):
    __tablename__ = "agent_thread_turn_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("agent_thread_turns.id", ondelete="CASCADE"), nullable=False, index=True)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("runtime_attachments.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    turn = relationship("AgentThreadTurn", back_populates="attachment_links")
    attachment = relationship("RuntimeAttachment", back_populates="turn_links")

    __table_args__ = (
        UniqueConstraint("turn_id", "attachment_id", name="uq_agent_thread_turn_attachment"),
    )
