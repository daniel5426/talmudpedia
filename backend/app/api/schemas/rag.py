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

class IngestionRequest(BaseModel):
    index_name: str
    documents: List[Dict[str, Any]]
    namespace: Optional[str] = None
    embedding_provider: str = "gemini"
    vector_store_provider: str = "pinecone"
    chunker_strategy: str = "token_based"
    chunk_size: int = 650
    chunk_overlap: int = 50
    use_celery: bool = True

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
