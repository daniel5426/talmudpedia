import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from ..base import Base


def _enum_values(enum_cls):
    return [e.value for e in enum_cls]


class PublishedAppAnalyticsEventType(str, enum.Enum):
    bootstrap_view = "bootstrap_view"
    visit_started = "visit_started"


class PublishedAppAnalyticsSurface(str, enum.Enum):
    host_runtime = "host_runtime"
    external_runtime = "external_runtime"
    preview_runtime = "preview_runtime"


class PublishedAppAnalyticsEvent(Base):
    __tablename__ = "published_app_analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="CASCADE"), nullable=False, index=True)
    app_account_id = Column(UUID(as_uuid=True), ForeignKey("published_app_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("published_app_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(
        SQLEnum(PublishedAppAnalyticsEventType, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    surface = Column(
        SQLEnum(PublishedAppAnalyticsSurface, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    visitor_key = Column(String(128), nullable=False, index=True)
    visit_key = Column(String(128), nullable=False, index=True)
    path = Column(String(512), nullable=True)
    referer = Column(String(1024), nullable=True)
    user_agent = Column(String(1024), nullable=True)
    ip_hash = Column(String(128), nullable=True, index=True)
    metadata_ = Column(JSONB, nullable=False, default=dict, name="metadata")
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index(
            "ix_published_app_analytics_app_visitor_event_occurred",
            "published_app_id",
            "visitor_key",
            "event_type",
            "occurred_at",
        ),
        Index(
            "ix_published_app_analytics_organization_app_occurred",
            "organization_id",
            "published_app_id",
            "occurred_at",
        ),
    )
