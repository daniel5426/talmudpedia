
import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..base import Base

class OperatorCategory(str, enum.Enum):
    SOURCE = "source"
    NORMALIZATION = "normalization"
    ENRICHMENT = "enrichment"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    STORAGE = "storage"
    RETRIEVAL = "retrieval"
    RERANKING = "reranking"
    CUSTOM = "custom"
    # Legacy support
    TRANSFORM = "transform"
    LLM = "llm"
    OUTPUT = "output"
    CONTROL = "control"

def pg_enum(enum_cls):
    return SQLEnum(enum_cls, values_callable=lambda x: [e.value for e in x])

class CustomOperator(Base):
    """User-defined custom operator (Draft Artifact)."""
    __tablename__ = "custom_operators"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    category = Column(pg_enum(OperatorCategory), nullable=False)
    description = Column(String, nullable=True)
    
    # Python code for the operator
    python_code = Column(Text, nullable=False)
    
    # JSON Schema definitions
    input_type = Column(String, nullable=False) # DataType
    output_type = Column(String, nullable=False) # DataType
    config_schema = Column(JSONB, default=[], nullable=False) # List[Dict[str, Any]]
    
    # Scope and Agent-specific fields
    scope = Column(String, default="rag", nullable=False) # rag, agent, both
    
    version = Column(String, default="1.0.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")
