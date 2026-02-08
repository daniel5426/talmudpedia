import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base
from .rbac import Action, ResourceType, ActorType

# Enums
class AuditResult(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"

# Models

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    org_unit_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=True, index=True)

    actor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    actor_type = Column(SQLEnum(ActorType), nullable=False)
    actor_email = Column(String, nullable=False)

    action = Column(SQLEnum(Action), nullable=False)
    resource_type = Column(SQLEnum(ResourceType), nullable=False)
    resource_id = Column(String, nullable=True)
    resource_name = Column(String, nullable=True)
    initiator_user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workload_principal_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    delegation_grant_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    token_jti = Column(String, nullable=True, index=True)
    scopes = Column(JSONB, nullable=True)

    result = Column(SQLEnum(AuditResult), nullable=False)
    failure_reason = Column(String, nullable=True)

    before_state = Column(JSONB, nullable=True)
    after_state = Column(JSONB, nullable=True)
    request_params = Column(JSONB, nullable=True)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    duration_ms = Column(Integer, nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    org_unit = relationship("OrgUnit")
