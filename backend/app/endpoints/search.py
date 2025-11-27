from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class SearchEndpoints:
    router = APIRouter(tags=["search"])

    @staticmethod
    @router.post("/search")
    async def search_documents(request_body: SearchRequest, request: Request):
        """
        Performs RAG search using the vector store.
        Returns a list of matching documents with metadata.
        """
        if not request_body.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        try:
            vector_store = request.app.state.vector_store
            results = vector_store.search(request_body.query, limit=request_body.limit)
            
            # Transform results to frontend-friendly format
            documents = []
            for result in results:
                metadata = result.get("metadata", {})
                documents.append({
                    "id": result.get("id"),
                    "title": metadata.get("ref", "Unknown Source"),
                    "snippet": metadata.get("text", "")[:200] + "..." if len(metadata.get("text", "")) > 200 else metadata.get("text", ""),
                    "source": metadata.get("ref", "Unknown Source"),
                    "ref": metadata.get("ref", "Unknown Source"),
                    "score": result.get("score", 0),
                })
            
            return {
                "results": documents,
                "total": len(documents),
                "query": request_body.query
            }
        except Exception as e:
            print(f"Search error: {e}")
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
