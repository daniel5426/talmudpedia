from typing import Any, List, Set

from app.agent.core.interfaces import Document, Reranker, Retriever


class HybridRetriever(Retriever):
    """
    Retriever that combines results from lexical and semantic retrievers and reranks them.
    """

    def __init__(
        self,
        lexical_retriever: Retriever,
        semantic_retriever: Retriever,
        reranker: Reranker,
        lexical_limit: int = 5,
        semantic_limit: int = 20
    ):
        self.lexical_retriever = lexical_retriever
        self.semantic_retriever = semantic_retriever
        self.reranker = reranker
        self.lexical_limit = lexical_limit
        self.semantic_limit = semantic_limit

    async def retrieve(self, query: str, limit: int = 20, **kwargs: Any) -> List[Document]:
        """
        Retrieve from both sources, merge, and rerank.
        """
        # 1. Retrieve from both sources in parallel
        import asyncio
        lexical_task = self.lexical_retriever.retrieve(query, limit=self.lexical_limit, **kwargs)
        semantic_task = self.semantic_retriever.retrieve(query, limit=self.semantic_limit, **kwargs)
        
        lexical_docs, semantic_docs = await asyncio.gather(lexical_task, semantic_task)
        
        # 3. Merge and Deduplicate
        merged_docs = []
        seen_ids: Set[str] = set()
        
        # Helper to add docs
        def add_docs(docs: List[Document]):
            for doc in docs:
                # Use a unique identifier if available, otherwise fallback to content hash or similar
                # Here we assume metadata['id'] is populated and unique across systems if they index same content
                # If IDs differ between systems for same content, we might need content-based dedup
                doc_id = doc.metadata.get("id")
                if not doc_id:
                    # Fallback to content if no ID
                    doc_id = hash(doc.content)
                
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    merged_docs.append(doc)

        add_docs(lexical_docs)
        add_docs(semantic_docs)
        
        if not merged_docs:
            return []

        # 4. Rerank
        reranked_docs = await self.reranker.rerank(query, merged_docs, top_n=limit)
        
        return reranked_docs
