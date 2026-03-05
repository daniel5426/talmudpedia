import uuid
from datetime import datetime
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class UsageQuotaScopeType(str, enum.Enum):
    tenant = "tenant"
    user = "user"


class UsageQuotaPeriodType(str, enum.Enum):
    monthly = "monthly"


class UsageQuotaReservationStatus(str, enum.Enum):
    active = "active"
    settled = "settled"
    released = "released"
    expired = "expired"


class UsageQuotaPolicy(Base):
    __tablename__ = "usage_quota_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    scope_type = Column(SQLEnum(UsageQuotaScopeType), nullable=False, index=True)
    period_type = Column(SQLEnum(UsageQuotaPeriodType), nullable=False, default=UsageQuotaPeriodType.monthly)
    limit_tokens = Column(Integer, nullable=False)
    timezone = Column(String, nullable=False, default="UTC", server_default=text("'UTC'"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    user = relationship("User")

    __table_args__ = (
        Index(
            "ix_usage_quota_policies_lookup",
            "tenant_id",
            "user_id",
            "scope_type",
            "is_active",
        ),
    )


class UsageQuotaCounter(Base):
    __tablename__ = "usage_quota_counters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(SQLEnum(UsageQuotaScopeType), nullable=False, index=True)
    scope_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    used_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reserved_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "period_start", name="uq_usage_quota_counters_scope_period"),
    )


class UsageQuotaReservation(Base):
    __tablename__ = "usage_quota_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # `run_id` is intentionally not a DB FK so reservations can be created
    # before AgentRun insert and atomically rolled back on quota failure.
    run_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    reserved_tokens_user = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reserved_tokens_tenant = Column(Integer, nullable=False, default=0, server_default=text("0"))
    status = Column(
        SQLEnum(UsageQuotaReservationStatus),
        nullable=False,
        default=UsageQuotaReservationStatus.active,
        server_default=text("'active'"),
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    settled_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    user = relationship("User")
