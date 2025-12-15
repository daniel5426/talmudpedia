import asyncio
from typing import Any, List

from app.agent.core.interfaces import Document, Retriever
from vector_store import VectorStore


class VectorRetriever(Retriever):
    """
    Retriever implementation using the existing VectorStore (Pinecone + Gemini).
    """

    def __init__(self, index_name: str = "talmudpedia", limit: int = 5):
        self.limit = limit
        self.vector_store = VectorStore(index_name=index_name)

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """
        Retrieve documents using the vector store.
        """
        limit = self.limit if limit is None else limit
        # region agent log
        try:
            with open("/Users/danielbenassaya/Code/personal/talmudpedia/.cursor/debug.log", "a", encoding="utf-8") as f:
                f.write(__import__("json").dumps({"sessionId":"debug-session","runId":"vector","hypothesisId":"A","location":"vector.py:retrieve","message":"to_thread_begin","data":{"queryLen":len(query or ''),"limit":limit},"timestamp":0}) + "\n")
        except Exception:
            pass
        # endregion
        results = await asyncio.to_thread(self.vector_store.search, query, limit=self.limit)
        # region agent log
        try:
            with open("/Users/danielbenassaya/Code/personal/talmudpedia/.cursor/debug.log", "a", encoding="utf-8") as f:
                f.write(__import__("json").dumps({"sessionId":"debug-session","runId":"vector","hypothesisId":"A","location":"vector.py:retrieve","message":"to_thread_end","data":{"results":len(results or [])},"timestamp":0}) + "\n")
        except Exception:
            pass
        # endregion
        
        documents = []
        for res in results:
            meta = res.get("metadata", {})
            doc = Document(
                content=meta.get("text", ""),
                metadata={
                    "ref": meta.get("ref", "Unknown Source"),
                    "id": res.get("id"),
                    **meta
                },
                score=res.get("score")
            )
            documents.append(doc)
            
        return documents
