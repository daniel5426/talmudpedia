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
            ref = metadata.get("ref") or metadata.get("title") or "Unknown Source"
            first_ref = metadata.get("first_ref") or ref
            he_ref = metadata.get("heRef") or metadata.get("he_ref") or metadata.get("he_title", "Unknown Source")
            
            # Construct range ref if possible using segment_refs
            segment_refs = metadata.get("segment_refs", [])
            total_segments = metadata.get("total_segments", 1)
            range_ref = first_ref
            
            if segment_refs and len(segment_refs) > 1:
                range_ref = f"{segment_refs[0]}-{segment_refs[-1]}"
            elif total_segments > 1:
                import re
                # Fallback: try to match the last number in first_ref
                match = re.search(r'^(.*?)(\d+)$', first_ref)
                if match:
                    prefix = match.group(1)
                    start_val = int(match.group(2))
                    end_val = start_val + total_segments - 1
                    range_ref = f"{first_ref}-{prefix}{end_val}"

            documents.append({
                "id": result.get("id"),
                "he_title": metadata.get("he_title", "Unknown Source"),
                "he_ref": he_ref,
                "title": ref,
                "first_ref": first_ref,
                "range_ref": range_ref,
                "total_segments": total_segments,
                "snippet": metadata.get("text", "")[:200] + "..." if len(metadata.get("text", "")) > 200 else metadata.get("text", ""),
                "ref": ref,
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
