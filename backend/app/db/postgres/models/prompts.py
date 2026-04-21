from __future__ import annotations

import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class PromptScope(str, enum.Enum):
    TENANT = "organization"
    GLOBAL = "global"


class PromptStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PromptOwnership(str, enum.Enum):
    MANUAL = "manual"
    SYSTEM = "system"


class PromptLibrary(Base):
    __tablename__ = "prompt_library"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=False, default="")
    scope = Column(
        SQLEnum(PromptScope, values_callable=_enum_values),
        nullable=False,
        default=PromptScope.TENANT,
        index=True,
    )
    status = Column(
        SQLEnum(PromptStatus, values_callable=_enum_values),
        nullable=False,
        default=PromptStatus.ACTIVE,
        index=True,
    )
    ownership = Column(
        SQLEnum(PromptOwnership, values_callable=_enum_values),
        nullable=False,
        default=PromptOwnership.MANUAL,
        index=True,
    )
    managed_by = Column(String, nullable=True, index=True)
    allowed_surfaces = Column(JSONB, nullable=False, default=list)
    tags = Column(JSONB, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization")
    versions = relationship("PromptLibraryVersion", back_populates="prompt", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_prompt_library_organization_name", "organization_id", "name"),
    )


class PromptLibraryVersion(Base):
    __tablename__ = "prompt_library_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("prompt_library.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=False, default="")
    allowed_surfaces = Column(JSONB, nullable=False, default=list)
    tags = Column(JSONB, nullable=False, default=list)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    prompt = relationship("PromptLibrary", back_populates="versions")
    creator = relationship("User")

    __table_args__ = (
        Index("uq_prompt_library_versions_prompt_version", "prompt_id", "version", unique=True),
    )
