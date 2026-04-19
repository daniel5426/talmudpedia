import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class TenantAPIKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class TenantAPIKey(Base):
    __tablename__ = "tenant_api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False, unique=True, index=True)
    secret_hash = Column(String, nullable=False)
    scopes = Column(JSONB, default=list, nullable=False)
    status = Column(
        SQLEnum(
            TenantAPIKeyStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=TenantAPIKeyStatus.ACTIVE,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    creator = relationship("User")


class ProjectAPIKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ProjectAPIKey(Base):
    __tablename__ = "project_api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False, unique=True, index=True)
    secret_hash = Column(String, nullable=False)
    scopes = Column(JSONB, default=list, nullable=False)
    status = Column(
        SQLEnum(
            ProjectAPIKeyStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ProjectAPIKeyStatus.ACTIVE,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    project = relationship("Project")
    creator = relationship("User")
