import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class FileSpaceStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class FileEntryType(str, enum.Enum):
    file = "file"
    directory = "directory"


class FileAccessMode(str, enum.Enum):
    read = "read"
    read_write = "read_write"


class FileSpace(Base):
    __tablename__ = "file_spaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(FileSpaceStatus), nullable=False, default=FileSpaceStatus.active, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization")
    project = relationship("Project")
    creator = relationship("User")
    entries = relationship("FileSpaceEntry", back_populates="space", cascade="all, delete-orphan")
    agent_links = relationship("AgentFileSpaceLink", back_populates="space", cascade="all, delete-orphan")


class FileSpaceEntry(Base):
    __tablename__ = "file_space_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("file_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    path = Column(String(2048), nullable=False)
    entry_type = Column(SQLEnum(FileEntryType), nullable=False, index=True)
    current_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("file_entry_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mime_type = Column(String(255), nullable=True)
    byte_size = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)
    is_text = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    space = relationship("FileSpace", back_populates="entries")
    current_revision = relationship("FileEntryRevision", foreign_keys=[current_revision_id], post_update=True)
    revisions = relationship(
        "FileEntryRevision",
        back_populates="entry",
        cascade="all, delete-orphan",
        foreign_keys="FileEntryRevision.entry_id",
    )
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    __table_args__ = (
        UniqueConstraint("space_id", "path", name="uq_file_space_entries_space_path"),
        Index("ix_file_space_entries_space_deleted_path", "space_id", "deleted_at", "path"),
    )


class FileEntryRevision(Base):
    __tablename__ = "file_entry_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(UUID(as_uuid=True), ForeignKey("file_space_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key = Column(String(2048), nullable=False, unique=True)
    mime_type = Column(String(255), nullable=False)
    byte_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    is_text = Column(Boolean, nullable=False, default=False, server_default="false")
    encoding = Column(String(64), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entry = relationship("FileSpaceEntry", back_populates="revisions", foreign_keys=[entry_id])
    creator = relationship("User")
    run = relationship("AgentRun")

    __table_args__ = (
        Index("ix_file_entry_revisions_entry_created", "entry_id", "created_at"),
    )


class AgentFileSpaceLink(Base):
    __tablename__ = "agent_file_space_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    file_space_id = Column(UUID(as_uuid=True), ForeignKey("file_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    access_mode = Column(SQLEnum(FileAccessMode), nullable=False, default=FileAccessMode.read, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization")
    project = relationship("Project")
    agent = relationship("Agent")
    space = relationship("FileSpace", back_populates="agent_links")
    creator = relationship("User")

    __table_args__ = (
        UniqueConstraint("project_id", "agent_id", "file_space_id", name="uq_agent_file_space_project_agent_space"),
    )
