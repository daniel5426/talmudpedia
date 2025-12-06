from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from langchain_core.messages import BaseMessage
from pydantic import BaseModel


class LLMProvider(ABC):
    """Abstract base class for Language Model Providers."""

    @abstractmethod
    async def generate(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> BaseMessage:
        """Generate a complete response."""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        """Stream the response."""
        pass


class Document(BaseModel):
    """Standardized document model."""
    content: str
    metadata: Dict[str, Any] = {}
    score: Optional[float] = None


class Retriever(ABC):
    """Abstract base class for Retrievers."""

    @abstractmethod
    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """Retrieve relevant documents."""
        pass


class Reranker(ABC):
    """Abstract base class for Rerankers."""

    @abstractmethod
    async def rerank(self, query: str, documents: List[Document], top_n: int = 5) -> List[Document]:
        """Rerank a list of documents based on the query."""
        pass


class Tool(ABC):
    """Abstract base class for Tools."""

    name: str
    description: str

    @abstractmethod
    async def execute(self, input_data: Any, **kwargs: Any) -> Any:
        """Execute the tool."""
        pass
