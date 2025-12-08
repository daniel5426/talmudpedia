import asyncio
import os
import sys
from typing import List, Any
from unittest.mock import MagicMock
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Add current directory to path
sys.path.append(os.getcwd())

from app.agent.core.interfaces import Document, Retriever, Reranker
from app.agent.components.retrieval.lexical import LexicalRetriever
from app.agent.components.retrieval.hybrid import HybridRetriever

# Mock Semantic Retriever
class MockSemanticRetriever(Retriever):
    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        print(f"MockSemanticRetriever called with: {query}")
        return [
            Document(
                content="Semantic Result 1",
                metadata={"id": "sem-1", "ref": "Semantic Source 1"},
                score=0.8
            ),
            Document(
                content="Semantic Result 2",
                metadata={"id": "sem-2", "ref": "Semantic Source 2"},
                score=0.7
            )
        ]

# Mock Reranker
class MockReranker(Reranker):
    async def rerank(self, query: str, documents: List[Document], top_n: int = 5) -> List[Document]:
        print(f"MockReranker called with {len(documents)} documents")
        # Just reverse them to show reranking happened
        return list(reversed(documents))[:top_n]

async def main():
    print("Starting Hybrid Retriever Verification...")
    
    # Check for Elasticsearch env vars
    if not os.getenv("ELASTICSEARCH_URL"):
        print("ELASTICSEARCH_URL not set. Skipping real LexicalRetriever test.")
        # We could mock it here too if needed, but we want to test the real one if possible
        return

    try:
        # 1. Initialize Real Lexical Retriever
        print("Initializing LexicalRetriever...")
        lexical_retriever = LexicalRetriever(index_name="reshet")
        
        # 2. Initialize Mock Semantic and Reranker
        semantic_retriever = MockSemanticRetriever()
        reranker = MockReranker()
        
        # 3. Initialize Hybrid Retriever
        print("Initializing HybridRetriever...")
        hybrid_retriever = HybridRetriever(
            lexical_retriever=lexical_retriever,
            semantic_retriever=semantic_retriever,
            reranker=reranker,
            lexical_limit=2,
            semantic_limit=2
        )
        
        # 4. Run Retrieve
        print("Waiting for ES refresh...")
        await asyncio.sleep(2)
        query = "חֲז֖וֹן"
        print(f"Searching for: '{query}'")
        results = await hybrid_retriever.retrieve(query, limit=5)
        
        print(f"\nFinal Results ({len(results)}):")
        for i, doc in enumerate(results):
            print(f"{i+1}. [{doc.metadata.get('id')}] {doc.content[:50]}... (Score: {doc.score})")
            
        # Cleanup
        await lexical_retriever.close()
        print("\nVerification Successful!")

    except Exception as e:
        print(f"\nVerification Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
