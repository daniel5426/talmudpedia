from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class Chunk(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = {}
    start_index: int = 0
    end_index: int = 0
    token_count: int = 0


class ChunkingConfig(BaseModel):
    chunk_size: int = 650
    chunk_overlap: int = 50
    min_chunk_size: int = 100


class ChunkerStrategy(ABC):
    
    @property
    @abstractmethod
    def strategy_name(self) -> str:
        pass
    
    @abstractmethod
    def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        pass
