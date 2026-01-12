"""
Model Registry - Logical AI model definitions.

Models are vendor-agnostic capability definitions. Provider bindings are resolved
at execution time via ModelResolutionPolicy.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import Field

from .base import MongoModel, PyObjectId


class ModelCapabilityType(str, Enum):
    """The capability type of a logical model."""
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    VISION = "vision"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"


class ModelProviderType(str, Enum):
    """Supported model providers."""
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
    CUSTOM = "custom"


class ModelStatus(str, Enum):
    """Lifecycle status of a model."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class ModelMetadata(MongoModel):
    """Capability metadata for a logical model."""
    context_length: Optional[int] = None
    supports_streaming: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    embedding_dimensions: Optional[int] = None
    max_output_tokens: Optional[int] = None
    input_cost_per_1k: Optional[float] = None
    output_cost_per_1k: Optional[float] = None
    custom: dict[str, Any] = Field(default_factory=dict)


class ModelProvider(MongoModel):
    """
    A provider binding for a logical model.
    
    Multiple providers can be configured for failover and cost optimization.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    logical_model_id: PyObjectId
    provider: ModelProviderType
    provider_model_id: str  # e.g., "gpt-4o-2024-05-13"
    config: dict[str, Any] = Field(default_factory=dict)  # endpoint overrides, etc.
    credentials_ref: Optional[str] = None  # Reference to secrets manager
    priority: int = 0  # Lower = higher priority for failover
    is_enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ModelResolutionPolicy(MongoModel):
    """
    Policy for late-bound model resolution at execution time.
    """
    priority: list[str] = Field(default_factory=list)  # Provider preference order
    fallback_enabled: bool = True
    compliance_tags: list[str] = Field(default_factory=list)  # e.g., ["gdpr", "hipaa"]
    cost_tier: Optional[str] = None  # "budget" | "standard" | "premium"
    max_retries: int = 2
    timeout_seconds: int = 60


class LogicalModel(MongoModel):
    """
    A logical AI model definition.
    
    Logical models represent vendor-agnostic capabilities that can be bound
    to one or more providers at runtime.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str  # Display name, e.g., "GPT-4o"
    slug: str  # Unique identifier, e.g., "gpt-4o"
    description: Optional[str] = None
    capability_type: ModelCapabilityType
    metadata: ModelMetadata = Field(default_factory=ModelMetadata)
    default_resolution_policy: ModelResolutionPolicy = Field(default_factory=ModelResolutionPolicy)
    
    # Multi-tenancy
    tenant_id: PyObjectId
    
    # Versioning
    version: int = 1
    status: ModelStatus = ModelStatus.ACTIVE
    
    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[PyObjectId] = None
    updated_by: Optional[PyObjectId] = None

    class Config:
        collection_name = "logical_models"


class ModelProviderCollection:
    """Collection name for model providers."""
    collection_name = "model_providers"
