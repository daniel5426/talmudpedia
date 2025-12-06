import os
from typing import Any, List, Optional

from elasticsearch import AsyncElasticsearch
from app.agent.core.interfaces import Document, Retriever


class LexicalRetriever(Retriever):
    """
    Retriever implementation using Elasticsearch for lexical search.
    """

    def __init__(self, index_name: str = "reshet"):
        self.client = AsyncElasticsearch(
            os.getenv("ELASTICSEARCH_URL"),
            api_key=os.getenv("ELASTICSEARCH_API_KEY")
        )
        self.index_name = index_name

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """
        Retrieve documents using Elasticsearch.
        """
        try:
            response = await self.client.search(
                index=self.index_name,
                body={
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["text", "ref", "book"]
                        }
                    }
                },
                size=limit,
                _source=["text", "ref", "book", "heRef", "category"] # Adjust fields as needed based on ingestion
            )

            documents = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                doc = Document(
                    content=source.get("text", ""),
                    metadata={
                        "ref": source.get("ref", "Unknown Source"),
                        "id": hit.get("_id"),
                        "score": hit.get("_score"),
                        **source
                    },
                    score=hit.get("_score")
                )
                documents.append(doc)
            
            return documents

        except Exception as e:
            print(f"Error during lexical retrieval: {e}")
            return []

    async def close(self):
        await self.client.close()
