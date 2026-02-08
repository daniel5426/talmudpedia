import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Integer, Float, UniqueConstraint, Index
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

class ToolStatus(str, enum.Enum):
    # Stored in DB as uppercase enum literals to match existing schema
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"
    DISABLED = "DISABLED"

class ToolImplementationType(str, enum.Enum):
    INTERNAL = "INTERNAL"
    HTTP = "HTTP"
    RAG_RETRIEVAL = "RAG_RETRIEVAL"
    FUNCTION = "FUNCTION"
    CUSTOM = "CUSTOM"
    ARTIFACT = "ARTIFACT"
    MCP = "MCP"

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

    # Tool execution metadata
    status = Column(SQLEnum(ToolStatus), default=ToolStatus.DRAFT, nullable=False)
    version = Column(String, default="1.0.0", nullable=False)
    implementation_type = Column(SQLEnum(ToolImplementationType), default=ToolImplementationType.CUSTOM, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

    # Artifact Integration
    artifact_id = Column(String, nullable=True, index=True)
    artifact_version = Column(String, nullable=True)
    
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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    providers = relationship("ModelProviderBinding", back_populates="model", cascade="all, delete-orphan")

    __table_args__ = (
        Index('uq_model_registry_slug_tenant', 'slug', 'tenant_id', unique=True, postgresql_where=(tenant_id != None)),
        Index('uq_model_registry_slug_global', 'slug', unique=True, postgresql_where=(tenant_id == None)),
    )


class ModelProviderBinding(Base):
    """Link between a logical model and a specific provider implementation."""
    __tablename__ = "model_provider_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    
    provider = Column(SQLEnum(ModelProviderType), nullable=False)
    provider_model_id = Column(String, nullable=False) # e.g. "gpt-4o-2024-08-06"
    credentials_ref = Column(UUID(as_uuid=True), ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True, index=True)
    
    priority = Column(Integer, default=0, nullable=False) # Lower is higher priority
    is_enabled = Column(Boolean, default=True, nullable=False)
    
    config = Column(JSONB, default={}, nullable=False) # Provider specific config
    
    # Cost configuration for spend calculation (per 1K tokens in USD)
    cost_per_1k_input_tokens = Column(Float, nullable=True)
    cost_per_1k_output_tokens = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    model = relationship("ModelRegistry", back_populates="providers")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index('uq_model_binding_tenant', 'model_id', 'provider', 'provider_model_id', 'tenant_id', unique=True, postgresql_where=(tenant_id != None)),
        Index('uq_model_binding_global', 'model_id', 'provider', 'provider_model_id', unique=True, postgresql_where=(tenant_id == None)),
    )


class ProviderConfig(Base):
    """Centralized configuration for model providers (credentials, base_url, etc)."""
    __tablename__ = "provider_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True) # Null for Global
    
    provider = Column(SQLEnum(ModelProviderType), nullable=False)
    provider_variant = Column(String, nullable=True) # e.g. "azure", "org_abc", or null
    
    # Stores SECRETS (api_key, base_url, org_id) - Encrypted in future
    credentials = Column(JSONB, default={}, nullable=False)
    
    is_enabled = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")


class IntegrationCredentialCategory(str, enum.Enum):
    LLM_PROVIDER = "llm_provider"
    VECTOR_STORE = "vector_store"
    ARTIFACT_SECRET = "artifact_secret"
    CUSTOM = "custom"


class IntegrationCredential(Base):
    """Tenant-scoped credentials for external integrations."""
    __tablename__ = "integration_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    category = Column(
        SQLEnum(
            IntegrationCredentialCategory,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    provider_key = Column(String, nullable=False, index=True)
    provider_variant = Column(String, nullable=True)
    display_name = Column(String, nullable=False)

    credentials = Column(JSONB, default={}, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")

    __table_args__ = (
        Index(
            "uq_integration_credentials_variant",
            "tenant_id",
            "category",
            "provider_key",
            "provider_variant",
            unique=True,
            postgresql_where=(provider_variant != None),
        ),
        Index(
            "uq_integration_credentials_no_variant",
            "tenant_id",
            "category",
            "provider_key",
            unique=True,
            postgresql_where=(provider_variant == None),
        ),
    )
