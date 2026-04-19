import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from ..base import Base


class WorkOSWebhookEvent(Base):
    __tablename__ = "workos_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workos_event_id = Column(String, nullable=False, unique=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    organization_id = Column(String, nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="received", index=True)
    payload = Column(JSONB, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
