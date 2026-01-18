import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Integer, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

# Enums

class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperatorCategory(str, enum.Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    RETRIEVAL = "retrieval"
    LLM = "llm"
    OUTPUT = "output"
    CONTROL = "control"
    EMBEDDING = "embedding"
    STORAGE = "storage"


class PipelineJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Models

class RAGPipeline(Base):
    __tablename__ = "rag_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    
    # Configuration
    embedding_model_id = Column(String, nullable=True) # Could be FK to ModelRegistry if we enforce strict linking
    vector_db_config = Column(JSONB, default={}, nullable=False) # Collection name, dimensions, etc
    
    chunk_size = Column(Integer, default=512)
    chunk_overlap = Column(Integer, default=50)
    
    is_default = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")
    ingestion_jobs = relationship("IngestionJob", back_populates="pipeline", cascade="all, delete-orphan")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("rag_pipelines.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    
    source_type = Column(String, nullable=False) # e.g. "url", "file", "text"
    source_uri = Column(String, nullable=True) # URL or file path
    
    document_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    
    status = Column(SQLEnum(IngestionStatus), default=IngestionStatus.PENDING, nullable=False)
    error_message = Column(Text, nullable=True)
    
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    pipeline = relationship("RAGPipeline", back_populates="ingestion_jobs")
    tenant = relationship("Tenant")
    creator = relationship("User")


class VisualPipeline(Base):
    """Visual pipeline definition for the no-code builder."""
    __tablename__ = "visual_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    org_unit_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=True, index=True)
    
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    
    # Graph definition stored as JSONB
    nodes = Column(JSONB, default=[], nullable=False)  # List of PipelineNode
    edges = Column(JSONB, default=[], nullable=False)  # List of PipelineEdge
    
    version = Column(Integer, default=1, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    org_unit = relationship("OrgUnit")
    creator = relationship("User")
    executable_pipelines = relationship("ExecutablePipeline", back_populates="visual_pipeline", cascade="all, delete-orphan")


class ExecutablePipeline(Base):
    """Compiled and executable pipeline version."""
    __tablename__ = "executable_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visual_pipeline_id = Column(UUID(as_uuid=True), ForeignKey("visual_pipelines.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    
    version = Column(Integer, nullable=False)
    
    # Compiled pipeline definition
    compiled_graph = Column(JSONB, default={}, nullable=False)
    
    is_valid = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    compiled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    visual_pipeline = relationship("VisualPipeline", back_populates="executable_pipelines")
    tenant = relationship("Tenant")
    compiler = relationship("User")
    jobs = relationship("PipelineJob", back_populates="executable_pipeline", cascade="all, delete-orphan")


class PipelineJob(Base):
    """Pipeline execution job."""
    __tablename__ = "pipeline_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    executable_pipeline_id = Column(UUID(as_uuid=True), ForeignKey("executable_pipelines.id"), nullable=False, index=True)
    
    status = Column(SQLEnum(PipelineJobStatus), default=PipelineJobStatus.QUEUED, nullable=False)
    input_params = Column(JSONB, default={}, nullable=False)
    output = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    executable_pipeline = relationship("ExecutablePipeline", back_populates="jobs")
    trigger_user = relationship("User")
