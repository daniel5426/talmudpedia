from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

@router.get("/")
def read_root():
    """Returns a short status snapshot for the API."""
    return {"message": "Welcome to the Rabbinic AI API", "status": "active"}

@router.get("/search")
def search(request: Request, q: str, limit: int = 10):
    """Runs semantic search against the configured vector store."""
    vector_store = getattr(request.app.state, "vector_store", None)
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector search service unavailable (missing configuration).")
    results = vector_store.search(q, limit=limit)
    return {"results": results}
