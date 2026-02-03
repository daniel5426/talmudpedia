from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.core.interfaces import Document, Retriever
from app.services.retrieval_service import RetrievalService, RetrievalResult


class KnowledgeStoreRetriever(Retriever):
    """
    Retriever implementation using the centralized RetrievalService and Knowledge Stores.
    """

    def __init__(
        self, 
        db: AsyncSession,
        store_ids: List[UUID],
        limit: int = 5
    ):
        self.db = db
        self.store_ids = store_ids
        self.limit = limit
        self.service = RetrievalService(db)

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """
        Retrieve documents from the configured Knowledge Stores.
        """
        limit = limit if limit is not None else self.limit
        
        # Query all stores
        results: List[RetrievalResult] = await self.service.query_multiple_stores(
            store_ids=self.store_ids,
            query=query,
            top_k=limit
        )
        
        documents = []
        for res in results:
            doc = Document(
                content=res.text,
                metadata={
                    "id": res.id,
                    "knowledge_store_id": str(res.knowledge_store_id),
                    **res.metadata
                },
                score=res.score
            )
            documents.append(doc)
            
        return documents
