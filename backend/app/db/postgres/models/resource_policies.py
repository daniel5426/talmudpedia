from __future__ import annotations

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
    and_,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


def _enum_values(enum_cls):
    return [item.value for item in enum_cls]


class ResourcePolicyPrincipalType(str, enum.Enum):
    ORGANIZATION_USER = "organization_user"
    PUBLISHED_APP_ACCOUNT = "published_app_account"
    EMBEDDED_EXTERNAL_USER = "embedded_external_user"


class ResourcePolicyResourceType(str, enum.Enum):
    AGENT = "agent"
    TOOL = "tool"
    KNOWLEDGE_STORE = "knowledge_store"
    MODEL = "model"


class ResourcePolicyRuleType(str, enum.Enum):
    ALLOW = "allow"
    QUOTA = "quota"


class ResourcePolicyQuotaUnit(str, enum.Enum):
    TOKENS = "tokens"


class ResourcePolicyQuotaWindow(str, enum.Enum):
    MONTHLY = "monthly"


class ResourcePolicySet(Base):
    __tablename__ = "resource_policy_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization")
    creator = relationship("User")
    rules = relationship("ResourcePolicyRule", back_populates="policy_set", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_resource_policy_sets_organization_name"),
    )


class ResourcePolicySetInclude(Base):
    __tablename__ = "resource_policy_set_includes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_policy_set_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resource_policy_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    included_policy_set_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resource_policy_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    parent_policy_set = relationship("ResourcePolicySet", foreign_keys=[parent_policy_set_id])
    included_policy_set = relationship("ResourcePolicySet", foreign_keys=[included_policy_set_id])

    __table_args__ = (
        UniqueConstraint(
            "parent_policy_set_id",
            "included_policy_set_id",
            name="uq_resource_policy_set_include_edge",
        ),
    )


class ResourcePolicyRule(Base):
    __tablename__ = "resource_policy_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_set_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resource_policy_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type = Column(
        SQLEnum(ResourcePolicyResourceType, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    resource_id = Column(String, nullable=False, index=True)
    rule_type = Column(
        SQLEnum(ResourcePolicyRuleType, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    quota_unit = Column(
        SQLEnum(ResourcePolicyQuotaUnit, values_callable=_enum_values),
        nullable=True,
    )
    quota_window = Column(
        SQLEnum(ResourcePolicyQuotaWindow, values_callable=_enum_values),
        nullable=True,
    )
    quota_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    policy_set = relationship("ResourcePolicySet", back_populates="rules")

    __table_args__ = (
        Index(
            "uq_resource_policy_rules_allow_resource",
            "policy_set_id",
            "resource_type",
            "resource_id",
            unique=True,
            postgresql_where=and_(rule_type == ResourcePolicyRuleType.ALLOW),
            sqlite_where=and_(rule_type == ResourcePolicyRuleType.ALLOW),
        ),
        Index(
            "uq_resource_policy_rules_quota_resource",
            "policy_set_id",
            "resource_type",
            "resource_id",
            "quota_unit",
            "quota_window",
            unique=True,
            postgresql_where=and_(rule_type == ResourcePolicyRuleType.QUOTA),
            sqlite_where=and_(rule_type == ResourcePolicyRuleType.QUOTA),
        ),
    )


class ResourcePolicyAssignment(Base):
    __tablename__ = "resource_policy_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type = Column(
        SQLEnum(ResourcePolicyPrincipalType, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    policy_set_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resource_policy_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    published_app_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("published_app_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    embedded_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    external_user_id = Column(String(255), nullable=True, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization")
    policy_set = relationship("ResourcePolicySet")
    user = relationship("User", foreign_keys=[user_id])
    published_app_account = relationship("PublishedAppAccount")
    embedded_agent = relationship("Agent")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index(
            "uq_resource_policy_assignments_organization_user",
            "organization_id",
            "principal_type",
            "user_id",
            unique=True,
            postgresql_where=and_(
                principal_type == ResourcePolicyPrincipalType.ORGANIZATION_USER,
                user_id != None,
            ),
            sqlite_where=and_(
                principal_type == ResourcePolicyPrincipalType.ORGANIZATION_USER,
                user_id != None,
            ),
        ),
        Index(
            "uq_resource_policy_assignments_app_account",
            "organization_id",
            "principal_type",
            "published_app_account_id",
            unique=True,
            postgresql_where=and_(
                principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT,
                published_app_account_id != None,
            ),
            sqlite_where=and_(
                principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT,
                published_app_account_id != None,
            ),
        ),
        Index(
            "uq_resource_policy_assignments_embedded_user",
            "organization_id",
            "principal_type",
            "embedded_agent_id",
            "external_user_id",
            unique=True,
            postgresql_where=and_(
                principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER,
                embedded_agent_id != None,
                external_user_id != None,
            ),
            sqlite_where=and_(
                principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER,
                embedded_agent_id != None,
                external_user_id != None,
            ),
        ),
    )


class ResourcePolicyQuotaCounter(Base):
    __tablename__ = "resource_policy_quota_counters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type = Column(
        SQLEnum(ResourcePolicyPrincipalType, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    published_app_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("published_app_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    embedded_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    external_user_id = Column(String(255), nullable=True, index=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    quota_window = Column(
        SQLEnum(ResourcePolicyQuotaWindow, values_callable=_enum_values),
        nullable=False,
        default=ResourcePolicyQuotaWindow.MONTHLY,
        server_default=text("'monthly'"),
    )
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    used_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reserved_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "principal_type",
            "user_id",
            "published_app_account_id",
            "embedded_agent_id",
            "external_user_id",
            "model_id",
            "quota_window",
            "period_start",
            name="uq_resource_policy_quota_counter_scope_period",
        ),
    )


class ResourcePolicyQuotaReservation(Base):
    __tablename__ = "resource_policy_quota_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type = Column(
        SQLEnum(ResourcePolicyPrincipalType, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    published_app_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("published_app_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    embedded_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    external_user_id = Column(String(255), nullable=True, index=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    quota_window = Column(
        SQLEnum(ResourcePolicyQuotaWindow, values_callable=_enum_values),
        nullable=False,
        default=ResourcePolicyQuotaWindow.MONTHLY,
        server_default=text("'monthly'"),
    )
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    reserved_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    settled_at = Column(DateTime(timezone=True), nullable=True)
