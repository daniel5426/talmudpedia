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
