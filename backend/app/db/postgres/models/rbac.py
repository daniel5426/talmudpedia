import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

# Enums
class Action(str, enum.Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"

class ResourceType(str, enum.Enum):
    INDEX = "index"
    PIPELINE = "pipeline"
    JOB = "job"
    TENANT = "organization"
    ORG_UNIT = "org_unit"
    ROLE = "role"
    MEMBERSHIP = "membership"
    AUDIT = "audit"

class ActorType(str, enum.Enum):
    USER = "user"
    SERVICE = "service"
    AGENT = "agent"

# Models

class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    family = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization")
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    assignments = relationship("RoleAssignment", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('organization_id', 'family', 'name', name='uq_role_organization_family_name'),
    )

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    # Canonical permission key used by scope-based auth (e.g. `agents.write`).
    scope_key = Column(String, nullable=False, index=True)
    # Legacy fields kept nullable for backward compatibility during migration.
    resource_type = Column(SQLEnum(ResourceType), nullable=True)
    action = Column(SQLEnum(Action), nullable=True)

    # Relationships
    role = relationship("Role", back_populates="permissions")

    __table_args__ = (
        UniqueConstraint('role_id', 'scope_key', name='uq_role_permission_scope'),
    )

class RoleAssignment(Base):
    __tablename__ = "role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True)

    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("Organization")
    role = relationship("Role", back_populates="assignments")
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project")
    assigner = relationship("User", foreign_keys=[assigned_by])

    __table_args__ = (
        Index(
            "uq_role_assignments_org_user",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("project_id IS NULL"),
        ),
        Index(
            "uq_role_assignments_project_user",
            "organization_id",
            "user_id",
            "project_id",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL"),
        ),
    )
