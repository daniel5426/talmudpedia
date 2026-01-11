from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class VectorDocument(BaseModel):
    id: str
    values: List[float]
    metadata: Dict[str, Any] = {}


class VectorSearchResult(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any] = {}


class IndexStats(BaseModel):
    name: str
    dimension: int
    total_vector_count: int
    namespaces: Dict[str, int] = {}


class VectorStoreProvider(ABC):
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass
    
    @abstractmethod
    async def create_index(
        self,
        name: str,
        dimension: int,
        metric: str = "cosine",
        **kwargs: Any
    ) -> bool:
        pass
    
    @abstractmethod
    async def delete_index(self, name: str) -> bool:
        pass
    
    @abstractmethod
    async def list_indices(self) -> List[str]:
        pass
    
    @abstractmethod
    async def get_index_stats(self, name: str) -> Optional[IndexStats]:
        pass
    
    @abstractmethod
    async def upsert(
        self,
        index_name: str,
        documents: List[VectorDocument],
        namespace: Optional[str] = None
    ) -> int:
        pass
    
    @abstractmethod
    async def delete(
        self,
        index_name: str,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> bool:
        pass
    
    @abstractmethod
    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        pass
