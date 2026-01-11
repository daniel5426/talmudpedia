from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

from .base import MongoModel, PyObjectId


class RAGProviderType(str, Enum):
    EMBEDDING = "embedding"
    VECTOR_STORE = "vector_store"
    CHUNKER = "chunker"
    LOADER = "loader"


class RAGProviderConfig(MongoModel):
    name: str
    provider_type: RAGProviderType
    provider_name: str
    is_active: bool = False
    config: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RAGIndex(MongoModel):
    tenant_id: Optional[PyObjectId] = None
    owner_id: Optional[PyObjectId] = None
    name: str
    display_name: Optional[str] = None
    vector_store_provider: str
    embedding_provider: str
    dimension: int
    namespace: Optional[str] = None
    document_count: int = 0
    chunk_count: int = 0
    status: str = "active"
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RAGIngestionJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RAGIngestionJob(MongoModel):
    tenant_id: Optional[PyObjectId] = None
    owner_id: Optional[PyObjectId] = None
    index_name: str
    source_type: str
    source_path: str
    namespace: Optional[str] = None
    status: RAGIngestionJobStatus = RAGIngestionJobStatus.PENDING
    total_documents: int = 0
    processed_documents: int = 0
    total_chunks: int = 0
    upserted_chunks: int = 0
    failed_chunks: int = 0
    current_stage: str = "pending"
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RAGPipelineConfig(MongoModel):
    tenant_id: Optional[PyObjectId] = None
    owner_id: Optional[PyObjectId] = None
    name: str
    description: Optional[str] = None
    embedding_provider: str
    vector_store_provider: str
    chunker_strategy: str = "token_based"
    chunk_size: int = 650
    chunk_overlap: int = 50
    is_default: bool = False
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OperatorCategory(str, Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    EMBEDDING = "embedding"
    STORAGE = "storage"


class PipelineNodePosition(BaseModel):
    x: float
    y: float

    model_config = ConfigDict(extra="forbid")


class PipelineNode(BaseModel):
    id: str
    category: OperatorCategory
    operator: str
    position: PipelineNodePosition
    config: Dict[str, Any] = {}

    model_config = ConfigDict(extra="forbid")


class PipelineEdge(BaseModel):
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class VisualPipeline(MongoModel):
    tenant_id: PyObjectId
    org_unit_id: Optional[PyObjectId] = None
    name: str
    description: Optional[str] = None
    nodes: List[PipelineNode] = []
    edges: List[PipelineEdge] = []
    version: int = 1
    is_published: bool = False
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutableStep(BaseModel):
    step_id: str
    operator: str
    category: OperatorCategory
    config: Dict[str, Any]
    depends_on: List[str] = []

    model_config = ConfigDict(extra="forbid")


class ExecutablePipeline(MongoModel):
    visual_pipeline_id: PyObjectId
    version: int
    tenant_id: PyObjectId
    dag: List[ExecutableStep]
    config_snapshot: Dict[str, Any] = {}
    is_valid: bool = True
    compiled_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PipelineJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineJob(MongoModel):
    tenant_id: PyObjectId
    executable_pipeline_id: PyObjectId
    status: PipelineJobStatus = PipelineJobStatus.QUEUED
    input_params: Dict[str, Any] = {}
    triggered_by: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    logs_ref: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
