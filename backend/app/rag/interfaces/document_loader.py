from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from pydantic import BaseModel
from enum import Enum


class DocumentType(str, Enum):
    TEXT = "text"
    PDF = "pdf"
    JSON = "json"
    CSV = "csv"
    HTML = "html"
    MARKDOWN = "markdown"


class RawDocument(BaseModel):
    id: str
    content: str
    doc_type: DocumentType = DocumentType.TEXT
    metadata: Dict[str, Any] = {}
    source_path: Optional[str] = None


class DocumentLoader(ABC):
    
    @property
    @abstractmethod
    def loader_name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def supported_types(self) -> List[DocumentType]:
        pass
    
    @abstractmethod
    async def load(self, source: str, **kwargs: Any) -> List[RawDocument]:
        pass
    
    @abstractmethod
    async def load_stream(self, source: str, **kwargs: Any) -> AsyncIterator[RawDocument]:
        pass
