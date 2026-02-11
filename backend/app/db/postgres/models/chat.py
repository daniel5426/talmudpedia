import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class Chat(Base):
    __tablename__ = "chats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    published_app_id = Column(UUID(as_uuid=True), ForeignKey("published_apps.id", ondelete="SET NULL"), nullable=True, index=True)
    
    title = Column(String, nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    
    # Metadata for RAG/Agent configuration used
    agent_id = Column(String, nullable=True) # Optional link to an agent ID (if not FK initially)
    model_name = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    user = relationship("User")
    published_app = relationship("PublishedApp")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.index")

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    
    # For keeping consistent ordering
    index = Column(Integer, nullable=False)
    
    # Additional data
    tool_calls = Column(JSONB, nullable=True) # If role == assistant
    tool_result_id = Column(String, nullable=True) # If role == tool
    token_count = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    chat = relationship("Chat", back_populates="messages")
