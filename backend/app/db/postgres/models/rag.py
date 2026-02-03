import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Integer, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..base import Base

# Enums



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



class PipelineType(str, enum.Enum):
    INGESTION = "ingestion"
    RETRIEVAL = "retrieval"



class PipelineJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineStepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class KnowledgeStoreStatus(str, enum.Enum):
    ACTIVE = "active"
    SYNCING = "syncing"
    ERROR = "error"
    ARCHIVED = "archived"


class StorageBackend(str, enum.Enum):
    PGVECTOR = "pgvector"
    PINECONE = "pinecone"
    QDRANT = "qdrant"


class RetrievalPolicy(str, enum.Enum):
    SEMANTIC_ONLY = "semantic_only"
    HYBRID = "hybrid"
    KEYWORD_ONLY = "keyword_only"
    RECENCY_BOOSTED = "recency_boosted"



def pg_enum(enum_cls):
    return SQLEnum(enum_cls, values_callable=lambda x: [e.value for e in x])

# Models

class KnowledgeStore(Base):
    """
    Logical knowledge repository that abstracts away vector DB implementation.
    
    This represents a corpus of knowledge with a defined embedding model and retrieval policy.
    The physical storage (Pinecone, PGVector, etc.) is an implementation detail.
    """
    __tablename__ = "knowledge_stores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Identity
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    # Logical Configuration (The Contract)
    embedding_model_id = Column(String, nullable=False)
    chunking_strategy = Column(JSONB, default={}, nullable=False)
    retrieval_policy = Column(pg_enum(RetrievalPolicy), default=RetrievalPolicy.SEMANTIC_ONLY, nullable=False)
    
    # Physical Binding (Implementation Detail - hidden from users)
    backend = Column(pg_enum(StorageBackend), default=StorageBackend.PGVECTOR, nullable=False)
    backend_config = Column(JSONB, default={}, nullable=False)
    
    # Status & Metrics
    status = Column(pg_enum(KnowledgeStoreStatus), default=KnowledgeStoreStatus.ACTIVE, nullable=False)
    document_count = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    
    # Timestamps & Ownership
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")




class RAGPipeline(Base):
    __tablename__ = "rag_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
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
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")


class VisualPipeline(Base):
    """Visual pipeline definition for the no-code builder."""
    __tablename__ = "visual_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    org_unit_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True)
    
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    
    # Graph definition stored as JSONB
    nodes = Column(JSONB, default=[], nullable=False)  # List of PipelineNode
    edges = Column(JSONB, default=[], nullable=False)  # List of PipelineEdge
    
    version = Column(Integer, default=1, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    
    pipeline_type = Column(pg_enum(PipelineType), default=PipelineType.INGESTION, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    org_unit = relationship("OrgUnit")
    creator = relationship("User")
    executable_pipelines = relationship("ExecutablePipeline", back_populates="visual_pipeline", cascade="all, delete-orphan")


class ExecutablePipeline(Base):
    """Compiled and executable pipeline version."""
    __tablename__ = "executable_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visual_pipeline_id = Column(UUID(as_uuid=True), ForeignKey("visual_pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    version = Column(Integer, nullable=False)
    
    # Compiled pipeline definition
    compiled_graph = Column(JSONB, default={}, nullable=False)
    pipeline_type = Column(pg_enum(PipelineType), default=PipelineType.INGESTION, nullable=False)
    
    is_valid = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    compiled_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    visual_pipeline = relationship("VisualPipeline", back_populates="executable_pipelines")
    tenant = relationship("Tenant")
    compiler = relationship("User")
    jobs = relationship("PipelineJob", back_populates="executable_pipeline", cascade="all, delete-orphan")


class PipelineJob(Base):
    """Pipeline execution job."""
    __tablename__ = "pipeline_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    executable_pipeline_id = Column(UUID(as_uuid=True), ForeignKey("executable_pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    
    status = Column(pg_enum(PipelineJobStatus), default=PipelineJobStatus.QUEUED, nullable=False)
    input_params = Column(JSONB, default={}, nullable=False)
    output = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    executable_pipeline = relationship("ExecutablePipeline", back_populates="jobs")
    trigger_user = relationship("User")


class CustomOperator(Base):
    """User-defined custom operator."""
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
    config_schema = Column(JSONB, default=[], nullable=False) # List[ConfigFieldSpec]
    
    version = Column(String, default="1.0.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    creator = relationship("User")


class PipelineStepExecution(Base):
    """Detailed execution status for a single step in a pipeline job."""
    __tablename__ = "pipeline_step_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    step_id = Column(String, nullable=False) # Node ID from visual graph
    operator_id = Column(String, nullable=False) # Operator Identifier
    
    status = Column(pg_enum(PipelineStepStatus), default=PipelineStepStatus.PENDING, nullable=False)
    
    input_data = Column(JSONB, nullable=True) # Serialized input
    output_data = Column(JSONB, nullable=True) # Serialized output
    metadata_ = Column(JSONB, default={}, nullable=False, name="metadata") # Execution metadata (time, tokens, etc)
    error_message = Column(Text, nullable=True)
    
    execution_order = Column(Integer, default=0) # Order in the execution sequence
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    job = relationship("PipelineJob", backref="steps")
    tenant = relationship("Tenant")


