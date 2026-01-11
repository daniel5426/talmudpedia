from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    INGEST = "ingest"
    DELETE = "delete"
    REINDEX = "reindex"


class IngestionJobConfig(BaseModel):
    source_type: str
    source_path: str
    index_name: str
    namespace: Optional[str] = None
    chunker_config: Optional[Dict[str, Any]] = None
    metadata_overrides: Dict[str, Any] = {}


class JobProgress(BaseModel):
    total_documents: int = 0
    processed_documents: int = 0
    total_chunks: int = 0
    upserted_chunks: int = 0
    failed_chunks: int = 0
    current_stage: str = "initializing"


class IngestionJob(BaseModel):
    id: str
    job_type: JobType = JobType.INGEST
    status: JobStatus = JobStatus.PENDING
    config: IngestionJobConfig
    progress: JobProgress = JobProgress()
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    total_documents: int
    total_chunks: int
    successful_upserts: int
    failed_upserts: int
    duration_seconds: float
    errors: List[str] = []
