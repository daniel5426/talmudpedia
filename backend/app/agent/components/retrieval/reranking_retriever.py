from typing import Any, List

from app.agent.core.interfaces import Document, Reranker, Retriever


class RerankingRetriever(Retriever):
    """
    Retriever that wraps another retriever and applies reranking.
    """

    def __init__(self, base_retriever: Retriever, reranker: Reranker, fetch_k_multiplier: int = 5):
        self.base_retriever = base_retriever
        self.reranker = reranker
        self.fetch_k_multiplier = fetch_k_multiplier

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """
        Retrieve documents from base retriever and then rerank them.
        """
        # Fetch more documents than needed
        fetch_k = limit * self.fetch_k_multiplier
        
        # 1. Retrieve from base retriever
        initial_docs = await self.base_retriever.retrieve(query, limit=fetch_k, **kwargs)
        
        if not initial_docs:
            return []
            
        # 2. Rerank
        reranked_docs = await self.reranker.rerank(query, initial_docs, top_n=limit)
        
        return reranked_docs
