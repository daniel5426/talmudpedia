from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI

import agent as agent_module
from app.db.connection import MongoDatabase
from app.endpoints import register_endpoints
from vector_store import VectorStore

load_dotenv(Path(__file__).parent / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstraps shared services for the FastAPI lifecycle."""
    await MongoDatabase.connect()
    app.state.vector_store = VectorStore()
    agent_module.vector_store = app.state.vector_store
    print("VectorStore initialized successfully.")
    yield
    await MongoDatabase.close()


app = FastAPI(title="Rabbinic AI API", version="0.1.0", lifespan=lifespan)

register_endpoints(app)


@app.get("/health")
def health_check():
    """Reports service health for uptime monitors."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
