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
    CUSTOM = "custom"

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
    __tablename__ = "model_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    
    provider = Column(SQLEnum(ModelProviderType), nullable=False)
    name = Column(String, nullable=False) # e.g. "gpt-4"
    display_name = Column(String, nullable=True)
    
    # Properties
    context_window = Column(Integer, default=4096, nullable=False)
    max_tokens = Column(Integer, default=4096, nullable=False)
    
    cost_per_1k_input = Column(Float, default=0.0)
    cost_per_1k_output = Column(Float, default=0.0)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant")
