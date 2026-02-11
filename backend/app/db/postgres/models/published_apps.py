import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


def _enum_values(enum_cls):
    return [e.value for e in enum_cls]


class PublishedAppStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    paused = "paused"
    archived = "archived"


class PublishedAppRevisionKind(str, enum.Enum):
    draft = "draft"
    published = "published"


class PublishedAppUserMembershipStatus(str, enum.Enum):
    active = "active"
    blocked = "blocked"


class PublishedApp(Base):
    __tablename__ = "published_apps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False, index=True)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)

    status = Column(
        SQLEnum(PublishedAppStatus, values_callable=_enum_values),
        nullable=False,
        default=PublishedAppStatus.draft,
    )
    auth_enabled = Column(Boolean, nullable=False, default=True)
    auth_providers = Column(JSONB, nullable=False, default=lambda: ["password"])
    published_url = Column(String, nullable=True)
    template_key = Column(String, nullable=False, default="chat-classic")
    current_draft_revision_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    current_published_revision_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    agent = relationship("Agent")
    creator = relationship("User")
    memberships = relationship("PublishedAppUserMembership", back_populates="published_app", cascade="all, delete-orphan")
    sessions = relationship("PublishedAppSession", back_populates="published_app", cascade="all, delete-orphan")
    revisions = relationship("PublishedAppRevision", back_populates="published_app", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_published_apps_tenant_name"),
    )


class PublishedAppUserMembership(Base):
    __tablename__ = "published_app_user_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(
        SQLEnum(PublishedAppUserMembershipStatus, values_callable=_enum_values),
        nullable=False,
        default=PublishedAppUserMembershipStatus.active,
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    published_app = relationship("PublishedApp", back_populates="memberships")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("published_app_id", "user_id", name="uq_published_app_user_membership"),
    )


class PublishedAppSession(Base):
    __tablename__ = "published_app_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    jti = Column(String, nullable=False, unique=True, index=True)
    provider = Column(String, nullable=False)
    metadata_ = Column(JSONB, nullable=False, default=dict, name="metadata")

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    published_app = relationship("PublishedApp", back_populates="sessions")
    user = relationship("User")

    __table_args__ = (
        Index("ix_published_app_sessions_app_user", "published_app_id", "user_id"),
    )


class PublishedAppRevision(Base):
    __tablename__ = "published_app_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    published_app_id = Column(
        UUID(as_uuid=True),
        ForeignKey("published_apps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(
        SQLEnum(PublishedAppRevisionKind, values_callable=_enum_values),
        nullable=False,
        default=PublishedAppRevisionKind.draft,
    )
    template_key = Column(String, nullable=False, default="chat-classic")
    entry_file = Column(String, nullable=False, default="src/main.tsx")
    files = Column(JSONB, nullable=False, default=dict)
    compiled_bundle = Column(String, nullable=True)
    bundle_hash = Column(String, nullable=True, index=True)
    source_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("published_app_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    published_app = relationship("PublishedApp", back_populates="revisions")
    creator = relationship("User")
