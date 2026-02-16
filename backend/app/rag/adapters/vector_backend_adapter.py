"""
Vector Backend Adapter - Unified interface for vector store operations.

This module provides adapters that wrap the existing VectorStoreProvider implementations
and expose a simplified interface for the RetrievalService and KnowledgeStoreSinkExecutor.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel

from app.rag.interfaces.vector_store import VectorDocument, VectorSearchResult
from app.db.postgres.models import StorageBackend


class VectorRecord(BaseModel):
    """A record to be stored in a vector database."""
    id: str
    values: List[float]
    text: str
    metadata: Dict[str, Any] = {}


class SearchResult(BaseModel):
    """A search result from a vector database."""
    id: str
    score: float
    text: str
    metadata: Dict[str, Any] = {}


class VectorBackendAdapter(ABC):
    """
    Abstract adapter interface for vector store operations.
    
    This provides a simplified interface used by the RetrievalService and
    KnowledgeStoreSinkExecutor, abstracting away provider-specific details.
    """
    
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return the backend name (e.g., 'pinecone', 'pgvector', 'qdrant')."""
        pass
    
    @abstractmethod
    async def upsert(self, vectors: List[VectorRecord], namespace: Optional[str] = None) -> int:
        """Upsert vectors into the store. Returns count of upserted records."""
        pass
    
    @abstractmethod
    async def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None
    ) -> List[SearchResult]:
        """Query for similar vectors. Returns list of search results."""
        pass
    
    @abstractmethod
    async def delete(self, ids: List[str], namespace: Optional[str] = None) -> int:
        """Delete vectors by ID. Returns count of deleted records."""
        pass
    
    @abstractmethod
    async def count(self, namespace: Optional[str] = None) -> int:
        """Count total vectors in the namespace."""
        pass


class PineconeAdapter(VectorBackendAdapter):
    """Adapter for Pinecone vector store."""
    
    def __init__(self, config: Dict[str, Any]):
        from app.rag.providers.vector_store.pinecone import PineconeVectorStore
        
        self._index_name = config.get("index_name")
        self._api_key = config.get("api_key")
        if not self._index_name:
            raise ValueError("Missing Pinecone index_name in knowledge store backend configuration")
        if not self._api_key:
            raise ValueError(
                "Missing Pinecone API key. Configure a tenant vector_store credential and bind it to the knowledge store."
            )

        self._store = PineconeVectorStore(api_key=self._api_key, allow_env_fallback=False)
    
    @property
    def backend_name(self) -> str:
        return "pinecone"
    
    async def upsert(self, vectors: List[VectorRecord], namespace: Optional[str] = None) -> int:
        docs = [
            VectorDocument(
                id=v.id,
                values=v.values,
                metadata={**v.metadata, "text": v.text}
            )
            for v in vectors
        ]
        return await self._store.upsert(self._index_name, docs, namespace)
    
    async def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None
    ) -> List[SearchResult]:
        results = await self._store.search(
            self._index_name,
            vector,
            top_k,
            namespace,
            filters
        )
        return [
            SearchResult(
                id=r.id,
                score=r.score,
                text=r.metadata.pop("text", ""),
                metadata=r.metadata
            )
            for r in results
        ]
    
    async def delete(self, ids: List[str], namespace: Optional[str] = None) -> int:
        success = await self._store.delete(self._index_name, ids, namespace)
        return len(ids) if success else 0
    
    async def count(self, namespace: Optional[str] = None) -> int:
        stats = await self._store.get_index_stats(self._index_name)
        if not stats:
            return 0
        if namespace and stats.namespaces:
            return stats.namespaces.get(namespace, 0)
        return stats.total_vector_count


class PgVectorAdapter(VectorBackendAdapter):
    """Adapter for PGVector (PostgreSQL with pgvector extension)."""
    
    def __init__(self, config: Dict[str, Any]):
        from app.rag.providers.vector_store.pgvector import PgvectorVectorStore
        
        self._collection_name = config.get("collection_name", config.get("index_name"))
        self._store = PgvectorVectorStore()
    
    @property
    def backend_name(self) -> str:
        return "pgvector"
    
    async def upsert(self, vectors: List[VectorRecord], namespace: Optional[str] = None) -> int:
        if not vectors:
            return 0

        # Ensure the backing pgvector table/index exists before first upsert.
        dimension = next((len(v.values) for v in vectors if isinstance(v.values, list) and v.values), 0)
        if dimension <= 0:
            raise ValueError("No valid embedding vectors were provided for PGVector upsert")
        created = await self._store.create_index(self._collection_name, dimension)
        if not created:
            raise ValueError(f"Failed to initialize pgvector collection '{self._collection_name}'")

        docs = [
            VectorDocument(
                id=v.id,
                values=v.values,
                metadata={**v.metadata, "text": v.text, "namespace": namespace or "default"}
            )
            for v in vectors
        ]
        return await self._store.upsert(self._collection_name, docs, namespace)
    
    async def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None
    ) -> List[SearchResult]:
        results = await self._store.search(
            self._collection_name,
            vector,
            top_k,
            namespace=namespace,
            filter=filters
        )
        return [
            SearchResult(
                id=r.id,
                score=r.score,
                text=r.metadata.pop("text", ""),
                metadata=r.metadata
            )
            for r in results
        ]
    
    async def delete(self, ids: List[str], namespace: Optional[str] = None) -> int:
        success = await self._store.delete(self._collection_name, ids, namespace)
        return len(ids) if success else 0
    
    async def count(self, namespace: Optional[str] = None) -> int:
        # PGVector stats - implementation depends on your pgvector store
        try:
            stats = await self._store.get_index_stats(self._collection_name)
            return stats.total_vector_count if stats else 0
        except Exception:
            return 0


class QdrantAdapter(VectorBackendAdapter):
    """Adapter for Qdrant vector store."""
    
    def __init__(self, config: Dict[str, Any]):
        from app.rag.providers.vector_store.qdrant import QdrantVectorStore
        
        self._collection_name = config.get("collection_name", config.get("index_name"))
        self._store = QdrantVectorStore(
            url=config.get("url"),
            api_key=config.get("api_key")
        )
    
    @property
    def backend_name(self) -> str:
        return "qdrant"
    
    async def upsert(self, vectors: List[VectorRecord], namespace: Optional[str] = None) -> int:
        docs = [
            VectorDocument(
                id=v.id,
                values=v.values,
                metadata={**v.metadata, "text": v.text}
            )
            for v in vectors
        ]
        return await self._store.upsert(self._collection_name, docs, namespace)
    
    async def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None
    ) -> List[SearchResult]:
        results = await self._store.search(
            self._collection_name,
            vector,
            top_k,
            namespace,
            filters
        )
        return [
            SearchResult(
                id=r.id,
                score=r.score,
                text=r.metadata.pop("text", ""),
                metadata=r.metadata
            )
            for r in results
        ]
    
    async def delete(self, ids: List[str], namespace: Optional[str] = None) -> int:
        success = await self._store.delete(self._collection_name, ids, namespace)
        return len(ids) if success else 0
    
    async def count(self, namespace: Optional[str] = None) -> int:
        try:
            stats = await self._store.get_index_stats(self._collection_name)
            return stats.total_vector_count if stats else 0
        except Exception:
            return 0


def create_adapter(backend: StorageBackend, config: Dict[str, Any]) -> VectorBackendAdapter:
    """Factory function to create the appropriate adapter for a backend."""
    adapters = {
        StorageBackend.PINECONE: PineconeAdapter,
        StorageBackend.PGVECTOR: PgVectorAdapter,
        StorageBackend.QDRANT: QdrantAdapter,
    }
    
    adapter_class = adapters.get(backend)
    if not adapter_class:
        raise ValueError(f"Unsupported storage backend: {backend}")
    
    return adapter_class(config)
