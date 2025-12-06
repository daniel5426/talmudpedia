import os
from typing import List, Optional
from pinecone import Pinecone

from app.agent.core.interfaces import Document, Reranker


class PineconeReranker(Reranker):
    """
    Reranker implementation using Pinecone's inference API.
    """

    def __init__(self, model: str = "bge-reranker-v2-m3"):
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.model = model

    async def rerank(self, query: str, documents: List[Document], top_n: int = 5) -> List[Document]:
        """
        Rerank documents using Pinecone's inference API.
        """
        if not documents:
            return []

        # Prepare documents for reranking (list of strings or dicts)
        # Pinecone rerank expects a list of strings or dicts with 'text' key
        # We'll use the document content
        docs_content = [doc.content for doc in documents]

        try:
            # The user provided example uses pc.inference.rerank
            # We assume this is available in the installed pinecone version
            results = self.pc.inference.rerank(
                model=self.model,
                query=query,
                documents=docs_content,
                top_n=top_n,
                return_documents=False # We only need indices and scores
            )
            
            # Reconstruct the list of documents based on the reranked results
            reranked_docs = []
            for result in results.data:
                # result has 'index' and 'score'
                original_doc = documents[result.index]
                # Update score
                original_doc.score = result.score
                reranked_docs.append(original_doc)
                
            return reranked_docs

        except Exception as e:
            print(f"Error during reranking: {e}")
            # Fallback to returning original documents (sliced) if reranking fails
            return documents[:top_n]


class NoOpReranker(Reranker):
    """
    Pass-through reranker that does nothing.
    """

    async def rerank(self, query: str, documents: List[Document], top_n: int = 5) -> List[Document]:
        return documents[:top_n]
