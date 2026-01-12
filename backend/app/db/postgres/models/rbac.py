import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, UniqueConstraint
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
    TENANT = "tenant"
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
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    assignments = relationship("RoleAssignment", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_role_tenant_name'),
    )

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    resource_type = Column(SQLEnum(ResourceType), nullable=False)
    action = Column(SQLEnum(Action), nullable=False)

    # Relationships
    role = relationship("Role", back_populates="permissions")

    __table_args__ = (
        UniqueConstraint('role_id', 'resource_type', 'action', name='uq_role_permission'),
    )

class RoleAssignment(Base):
    __tablename__ = "role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    
    # Actor (Polymorphic-ish, usually User)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    actor_type = Column(SQLEnum(ActorType), default=ActorType.USER, nullable=False)
    
    # Scope (Polymorphic)
    scope_id = Column(UUID(as_uuid=True), nullable=False, index=True) # Could be Tenant ID, OrgUnit ID, or Resource ID
    scope_type = Column(String, nullable=False) # e.g. "tenant", "org_unit"

    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    role = relationship("Role", back_populates="assignments")
    user = relationship("User", foreign_keys=[user_id])
    assigner = relationship("User", foreign_keys=[assigned_by])
