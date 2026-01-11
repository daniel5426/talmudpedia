import os
import asyncio
from typing import List, Dict, Any, Optional
import uuid

from app.rag.interfaces.vector_store import (
    VectorStoreProvider,
    VectorDocument,
    VectorSearchResult,
    IndexStats,
)


class QdrantVectorStore(VectorStoreProvider):
    
    def __init__(
        self,
        url: str = None,
        api_key: str = None,
        prefer_grpc: bool = True
    ):
        self._url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self._api_key = api_key or os.getenv("QDRANT_API_KEY")
        self._prefer_grpc = prefer_grpc
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "qdrant"
    
    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(
                    url=self._url,
                    api_key=self._api_key,
                    prefer_grpc=self._prefer_grpc
                )
            except ImportError:
                raise ImportError(
                    "qdrant-client is required. Install with: pip install qdrant-client"
                )
        return self._client
    
    async def create_index(
        self,
        name: str,
        dimension: int,
        metric: str = "cosine",
        **kwargs: Any
    ) -> bool:
        try:
            from qdrant_client.models import Distance, VectorParams
            
            distance_map = {
                "cosine": Distance.COSINE,
                "euclidean": Distance.EUCLID,
                "dot": Distance.DOT,
            }
            
            client = self._get_client()
            await asyncio.to_thread(
                client.create_collection,
                collection_name=name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=distance_map.get(metric, Distance.COSINE)
                )
            )
            return True
        except Exception:
            return False
    
    async def delete_index(self, name: str) -> bool:
        try:
            client = self._get_client()
            await asyncio.to_thread(client.delete_collection, collection_name=name)
            return True
        except Exception:
            return False
    
    async def list_indices(self) -> List[str]:
        try:
            client = self._get_client()
            collections = await asyncio.to_thread(client.get_collections)
            return [c.name for c in collections.collections]
        except Exception:
            return []
    
    async def get_index_stats(self, name: str) -> Optional[IndexStats]:
        try:
            client = self._get_client()
            info = await asyncio.to_thread(client.get_collection, collection_name=name)
            
            return IndexStats(
                name=name,
                dimension=info.config.params.vectors.size,
                total_vector_count=info.points_count,
                namespaces={}
            )
        except Exception:
            return None
    
    async def upsert(
        self,
        index_name: str,
        documents: List[VectorDocument],
        namespace: Optional[str] = None
    ) -> int:
        if not documents:
            return 0
        
        try:
            from qdrant_client.models import PointStruct
            
            client = self._get_client()
            points = [
                PointStruct(
                    id=doc.id if doc.id.isalnum() else str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.id)),
                    vector=doc.values,
                    payload={
                        **doc.metadata,
                        "_original_id": doc.id,
                        "_namespace": namespace or ""
                    }
                )
                for doc in documents
            ]
            
            await asyncio.to_thread(
                client.upsert,
                collection_name=index_name,
                points=points
            )
            return len(documents)
        except Exception:
            return 0
    
    async def delete(
        self,
        index_name: str,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> bool:
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchAny
            
            client = self._get_client()
            
            filter_conditions = Filter(
                must=[
                    FieldCondition(
                        key="_original_id",
                        match=MatchAny(any=ids)
                    )
                ]
            )
            
            if namespace:
                filter_conditions.must.append(
                    FieldCondition(key="_namespace", match=MatchAny(any=[namespace]))
                )
            
            await asyncio.to_thread(
                client.delete,
                collection_name=index_name,
                points_selector=filter_conditions
            )
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
            from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
            
            client = self._get_client()
            
            query_filter = None
            conditions = []
            
            if namespace:
                conditions.append(
                    FieldCondition(key="_namespace", match=MatchValue(value=namespace))
                )
            
            if filter:
                for key, value in filter.items():
                    if isinstance(value, dict) and "$in" in value:
                        conditions.append(
                            FieldCondition(key=key, match=MatchAny(any=value["$in"]))
                        )
                    else:
                        conditions.append(
                            FieldCondition(key=key, match=MatchValue(value=value))
                        )
            
            if conditions:
                query_filter = Filter(must=conditions)
            
            results = await asyncio.to_thread(
                client.search,
                collection_name=index_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=query_filter
            )
            
            return [
                VectorSearchResult(
                    id=r.payload.get("_original_id", str(r.id)),
                    score=r.score,
                    metadata={k: v for k, v in r.payload.items() if not k.startswith("_")}
                )
                for r in results
            ]
        except Exception:
            return []
