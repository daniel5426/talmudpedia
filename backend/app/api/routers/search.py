from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


router = APIRouter()

@router.post("/search")
async def search_documents(request_body: SearchRequest, request: Request):
    """
    Performs RAG search using the vector store.
    Returns a list of matching documents with metadata.
    """
    if not request_body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        vector_store = getattr(request.app.state, "vector_store", None)
        # Added safety check for vector_store presence
        if not vector_store:
             # Fallback or error if not initialized
             # Assuming main.py initializes it.
             # If strictly required:
             # raise HTTPException(status_code=503, detail="Vector store not initialized")
             pass 
        
        # Note: Original code accessed it directly. Safe to assume it exists if app configured correctly.
        # But 'getattr' with default is safer.
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
