from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel


class EmbeddingResult(BaseModel):
    values: List[float]
    token_count: int = 0


class EmbeddingProvider(ABC):
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass
    
    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        pass
