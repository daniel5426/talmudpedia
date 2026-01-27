from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class RAGIndex(BaseModel):
    name: str
    display_name: str
    dimension: int
    total_vectors: int
    namespaces: Dict[str, int]
    status: str
    synced: bool
    owner_id: Optional[str] = None

class CreateIndexRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    dimension: int = 768
    namespace: Optional[str] = None
    metadata: Dict[str, Any] = {}
    owner_id: Optional[str] = None

class ChunkPreviewRequest(BaseModel):
    text: str
    chunk_size: int = 650
    chunk_overlap: int = 50


class RAGStats(BaseModel):
    total_indices: int
    live_indices: int
    total_chunks: int
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    running_jobs: int
    total_pipelines: Optional[int] = None
    compiled_pipelines: Optional[int] = None
    available_providers: Dict[str, List[str]]

class CustomOperatorBase(BaseModel):
    name: str
    display_name: str
    category: str
    description: Optional[str] = None
    python_code: str
    input_type: str
    output_type: str
    config_schema: List[Dict[str, Any]] = []
    is_active: bool = True

class CustomOperatorCreate(CustomOperatorBase):
    pass

class CustomOperatorUpdate(BaseModel):
    display_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    python_code: Optional[str] = None
    input_type: Optional[str] = None
    output_type: Optional[str] = None
    config_schema: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None

class CustomOperatorResponse(CustomOperatorBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    version: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[uuid.UUID] = None

class CustomOperatorTestRequest(BaseModel):
    python_code: str
    input_data: Any
    config: Dict[str, Any] = {}
    input_type: str = "raw_documents"
    output_type: str = "raw_documents"

class CustomOperatorTestResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0

