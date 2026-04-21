import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Enum as SQLEnum, Text, Index, and_
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

# Enums
class OrganizationStatus(str, enum.Enum):
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

class MembershipStatus(str, enum.Enum):
    active = "active"
    pending = "pending"
    invited = "invited"
    suspended = "suspended"

# Models

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    workos_organization_id = Column(String, unique=True, nullable=True, index=True)
    status = Column(SQLEnum(OrganizationStatus), default=OrganizationStatus.active, nullable=False)
    settings = Column(JSONB, default={}, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    org_units = relationship("OrgUnit", back_populates="organization", cascade="all, delete-orphan")
    memberships = relationship("OrgMembership", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    workos_user_id = Column(String, unique=True, nullable=True, index=True)
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
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=True, index=True)
    
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    system_key = Column(String, nullable=True, index=True)
    type = Column(SQLEnum(OrgUnitType), nullable=False)
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata") # metadata is reserved in SQLAlchemy
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="org_units")
    parent = relationship("OrgUnit", remote_side=[id], backref="children")
    memberships = relationship("OrgMembership", back_populates="org_unit", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_org_units_organization_system_key",
            "organization_id",
            "system_key",
            unique=True,
            postgresql_where=and_(organization_id != None, system_key != None),
            sqlite_where=and_(organization_id != None, system_key != None),
        ),
    )


class OrgMembership(Base):
    __tablename__ = "org_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_unit_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=False)
    workos_membership_id = Column(String, unique=True, nullable=True, index=True)
    status = Column(SQLEnum(MembershipStatus), default=MembershipStatus.active, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
    org_unit = relationship("OrgUnit", back_populates="memberships")


class OrgInvite(Base):
    __tablename__ = "org_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_ids = Column(JSONB, default=list, nullable=False)
    project_role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("Organization")
    creator = relationship("User")
