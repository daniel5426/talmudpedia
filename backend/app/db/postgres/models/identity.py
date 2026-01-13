import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

# Enums
class TenantStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    pending = "pending"

class OrgUnitType(str, enum.Enum):
    org = "org"
    dept = "dept"
    team = "team"

class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"
    system = "system"

# Models

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    status = Column(SQLEnum(TenantStatus), default=TenantStatus.active, nullable=False)
    settings = Column(JSONB, default={}, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    org_units = relationship("OrgUnit", back_populates="tenant", cascade="all, delete-orphan")
    memberships = relationship("OrgMembership", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    role = Column(String, default="user", nullable=False) # Keeping as string to match Pydantic, or could upgrade to Enum
    token_usage = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    memberships = relationship("OrgMembership", back_populates="user", cascade="all, delete-orphan")


class OrgUnit(Base):
    __tablename__ = "org_units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=True, index=True)
    
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    type = Column(SQLEnum(OrgUnitType), nullable=False)
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata") # metadata is reserved in SQLAlchemy
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="org_units")
    parent = relationship("OrgUnit", remote_side=[id], backref="children")
    memberships = relationship("OrgMembership", back_populates="org_unit", cascade="all, delete-orphan")


class OrgMembership(Base):
    __tablename__ = "org_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    org_unit_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=False)
    
    status = Column(String, default="active", nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
    org_unit = relationship("OrgUnit", back_populates="memberships")

