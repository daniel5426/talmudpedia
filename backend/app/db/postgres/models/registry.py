import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

# Enums
class ToolDefinitionScope(str, enum.Enum):
    GLOBAL = "global"
    TENANT = "tenant"
    USER = "user"

class ModelProviderType(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    GEMINI = "gemini"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
    COHERE = "cohere"
    GROQ = "groq"
    MISTRAL = "mistral"
    TOGETHER = "together"
    CUSTOM = "custom"

class ModelCapabilityType(str, enum.Enum):
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    VISION = "vision"
    AUDIO = "audio"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    IMAGE = "image"
    RERANK = "rerank"

class ModelStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"

# Models

class ToolRegistry(Base):
    __tablename__ = "tool_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True) # Null for Global tools
    
    name = Column(String, nullable=False, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    
    scope = Column(SQLEnum(ToolDefinitionScope), default=ToolDefinitionScope.GLOBAL, nullable=False)
    
    # Metadata
    schema = Column(JSONB, default={}, nullable=False) 
    config_schema = Column(JSONB, default={}, nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    versions = relationship("ToolVersion", back_populates="tool", cascade="all, delete-orphan")


class ToolVersion(Base):
    __tablename__ = "tool_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("tool_registry.id"), nullable=False, index=True)
    
    version = Column(String, nullable=False) # semver
    code = Column(String, nullable=True) # Actual implementation code if stored
    artifact_url = Column(String, nullable=True) # URL to package/wasm if stored externally
    
    schema_snapshot = Column(JSONB, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    tool = relationship("ToolRegistry", back_populates="versions")
    creator = relationship("User")


class ModelRegistry(Base):
    """Logical Model definition - vendor agnostic."""
    __tablename__ = "model_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    
    name = Column(String, nullable=False) # Display Name
    slug = Column(String, nullable=False, index=True) # Unique identifier
    description = Column(String, nullable=True)
    
    capability_type = Column(SQLEnum(ModelCapabilityType), default=ModelCapabilityType.CHAT, nullable=False)
    status = Column(SQLEnum(ModelStatus), default=ModelStatus.ACTIVE, nullable=False)
    
    # Configuration
    default_resolution_policy = Column(JSONB, default={}, nullable=False)
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata")
    
    version = Column(Integer, default=1, nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    # Deprecated fields (kept for compatibility in current router logic, will migrate out)
    provider = Column(SQLEnum(ModelProviderType), nullable=True)
    context_window = Column(Integer, default=4096, nullable=False)
    max_tokens = Column(Integer, default=4096, nullable=False)
    cost_per_1k_input = Column(Float, default=0.0)
    cost_per_1k_output = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    providers = relationship("ModelProviderBinding", back_populates="model", cascade="all, delete-orphan")


class ModelProviderBinding(Base):
    """Link between a logical model and a specific provider implementation."""
    __tablename__ = "model_provider_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    
    provider = Column(SQLEnum(ModelProviderType), nullable=False)
    provider_model_id = Column(String, nullable=False) # e.g. "gpt-4o-2024-08-06"
    
    priority = Column(Integer, default=0, nullable=False) # Lower is higher priority
    is_enabled = Column(Boolean, default=True, nullable=False)
    
    config = Column(JSONB, default={}, nullable=False) # Provider specific config
    credentials_ref = Column(String, nullable=True) # Ref to vault/secret
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    model = relationship("ModelRegistry", back_populates="providers")
    tenant = relationship("Tenant")
