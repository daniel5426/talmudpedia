import os
from typing import Any, List, Optional

from elasticsearch import AsyncElasticsearch
from app.agent.core.interfaces import Document, Retriever


class LexicalRetriever(Retriever):
    """
    Retriever implementation using Elasticsearch for lexical search.
    """

    def __init__(self, index_name: str = "reshet"):
        es_url = os.getenv("ELASTICSEARCH_URL")
        es_api_key = os.getenv("ELASTICSEARCH_API_KEY")
        
        if not es_url:
            self.client = None
            self.index_name = index_name
            return
        
        self.client = AsyncElasticsearch(
            es_url,
            api_key=es_api_key
        )
        self.index_name = index_name

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> List[Document]:
        """
        Retrieve documents using Elasticsearch.
        """
        if not self.client:
            return []
        
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
        if self.client:
            await self.client.close()
