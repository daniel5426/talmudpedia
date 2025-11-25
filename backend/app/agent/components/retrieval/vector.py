from typing import Any, List

from app.agent.core.interfaces import Document, Retriever
from vector_store import VectorStore


class VectorRetriever(Retriever):
    """
    Retriever implementation using the existing VectorStore (Pinecone + Gemini).
    """

    def __init__(self, index_name: str = "talmudpedia"):
        self.vector_store = VectorStore(index_name=index_name)

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """
        Retrieve documents using the vector store.
        """
        results = self.vector_store.search(query, limit=limit)
        
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
