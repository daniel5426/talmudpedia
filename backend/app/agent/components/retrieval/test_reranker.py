import asyncio
from typing import List, Any
from app.agent.core.interfaces import Document, Retriever, Reranker
from app.agent.components.retrieval.reranking_retriever import RerankingRetriever

# Mock classes
class MockRetriever(Retriever):
    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        # Return 10 documents with dummy scores
        return [
            Document(content=f"Doc {i}", metadata={"id": i}, score=0.1 * i)
            for i in range(10)
        ][:limit]

class MockReranker(Reranker):
    async def rerank(self, query: str, documents: List[Document], top_n: int = 5) -> List[Document]:
        # Reverse the order to simulate reranking
        print(f"Reranking {len(documents)} documents...")
        reversed_docs = list(reversed(documents))
        # Assign new scores
        for i, doc in enumerate(reversed_docs):
            doc.score = 0.9 - (0.1 * i)
        return reversed_docs[:top_n]

async def test_reranking_retriever():
    print("Testing RerankingRetriever...")
    
    base_retriever = MockRetriever()
    reranker = MockReranker()
    retriever = RerankingRetriever(base_retriever=base_retriever, reranker=reranker, fetch_k_multiplier=2)
    
    # We ask for 3 documents. 
    # fetch_k_multiplier is 2, so it should fetch 6 from base retriever.
    # Then reranker should reverse them and return top 3.
    
    results = await retriever.retrieve("test query", limit=3)
    
    print(f"Got {len(results)} results.")
    for doc in results:
        print(f"Content: {doc.content}, Score: {doc.score}")
        
    assert len(results) == 3
    assert results[0].content == "Doc 5" # Base fetched 0-5 (6 docs). Reversed: 5,4,3,2,1,0. Top 3: 5,4,3.
    assert results[1].content == "Doc 4"
    assert results[2].content == "Doc 3"
    
    print("Test passed!")

if __name__ == "__main__":
    asyncio.run(test_reranking_retriever())
