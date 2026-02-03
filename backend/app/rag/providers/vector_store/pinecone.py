import os
import asyncio
from typing import List, Dict, Any, Optional

from pinecone import Pinecone, ServerlessSpec

from app.rag.interfaces.vector_store import (
    VectorStoreProvider,
    VectorDocument,
    VectorSearchResult,
    IndexStats,
)


class PineconeVectorStore(VectorStoreProvider):
    
    _instance: Optional["Pinecone"] = None
    _indices: Dict[str, Any] = {}
    
    def __init__(
        self,
        api_key: str = None,
        environment: str = None,
        cloud: str = "aws",
        region: str = "us-east-1"
    ):
        self._api_key = api_key or os.getenv("PINECONE_API_KEY")
        self._environment = environment
        self._cloud = cloud
        self._region = region
        
        if PineconeVectorStore._instance is None:
            PineconeVectorStore._instance = Pinecone(api_key=self._api_key)
        
        self._client = PineconeVectorStore._instance
    
    @property
    def provider_name(self) -> str:
        return "pinecone"
    
    def _get_index(self, name: str):
        if name not in PineconeVectorStore._indices:
            PineconeVectorStore._indices[name] = self._client.Index(name)
        return PineconeVectorStore._indices[name]
    
    async def create_index(
        self,
        name: str,
        dimension: int,
        metric: str = "cosine",
        **kwargs: Any
    ) -> bool:
        try:
            existing = await self.list_indices()
            if name in existing:
                return True
            
            await asyncio.to_thread(
                self._client.create_index,
                name=name,
                dimension=dimension,
                metric=metric,
                spec=ServerlessSpec(cloud=self._cloud, region=self._region)
            )
            return True
        except Exception:
            return False
    
    async def delete_index(self, name: str) -> bool:
        try:
            await asyncio.to_thread(self._client.delete_index, name)
            if name in PineconeVectorStore._indices:
                del PineconeVectorStore._indices[name]
            return True
        except Exception:
            return False
    
    async def list_indices(self) -> List[str]:
        try:
            result = await asyncio.to_thread(self._client.list_indexes)
            return result.names()
        except Exception:
            return []
    
    async def get_index_stats(self, name: str) -> Optional[IndexStats]:
        try:
            index = self._get_index(name)
            stats = await asyncio.to_thread(index.describe_index_stats)
            
            namespaces = {}
            if hasattr(stats, 'namespaces') and stats.namespaces:
                for ns_name, ns_stats in stats.namespaces.items():
                    namespaces[ns_name] = ns_stats.vector_count
            
            return IndexStats(
                name=name,
                dimension=stats.dimension,
                total_vector_count=stats.total_vector_count,
                namespaces=namespaces
            )
        except Exception:
            return None
    
    async def upsert(
        self,
        index_name: str,
        documents: List[VectorDocument],
        namespace: Optional[str] = None
    ) -> int:
        # Validate inputs
        if not documents:
            return 0
        
        # Propagate exceptions to caller (PipelineExecutor) for proper failure handling
        try:
            index = self._get_index(index_name)
            vectors = [
                {
                    "id": doc.id,
                    "values": doc.values,
                    "metadata": doc.metadata
                }
                for doc in documents
            ]
            
            kwargs = {"vectors": vectors}
            if namespace:
                kwargs["namespace"] = namespace
            
            # This will raise PineconeException if it fails (e.g. auth error, network)
            await asyncio.to_thread(index.upsert, **kwargs)
            
            return len(documents)
            
        except Exception as e:
            # We still catch to log, but we re-raise so the pipeline fails
            print(f"Error upserting to Pinecone index '{index_name}': {str(e)}")
            raise e
    
    async def delete(
        self,
        index_name: str,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> bool:
        try:
            index = self._get_index(index_name)
            kwargs = {"ids": ids}
            if namespace:
                kwargs["namespace"] = namespace
            
            await asyncio.to_thread(index.delete, **kwargs)
            return True
        except Exception:
            return False
    
    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        try:
            index = self._get_index(index_name)
            
            kwargs = {
                "vector": query_vector,
                "top_k": top_k,
                "include_metadata": True
            }
            if namespace:
                kwargs["namespace"] = namespace
            if filter:
                kwargs["filter"] = filter
            
            results = await asyncio.to_thread(index.query, **kwargs)
            
            return [
                VectorSearchResult(
                    id=match["id"],
                    score=match["score"],
                    metadata=match.get("metadata", {})
                )
                for match in results.get("matches", [])
            ]
        except Exception:
            return []
