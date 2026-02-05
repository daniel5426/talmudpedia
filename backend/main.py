from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
import multiprocessing
import os
import asyncio
# Load environment variables BEFORE importing any modules that might need them
load_dotenv(Path(__file__).parent / ".env")

from app.db.connection import MongoDatabase
from vector_store import VectorStore


def start_livekit_worker():
    """Run the LiveKit worker in a separate process"""
    try:
        from app.workers.livekit_worker import run_worker
        print("Starting LiveKit voice agent worker...")
        run_worker()
    except Exception as e:
        print(f"LiveKit worker failed to start: {e}")
        print("Voice mode will not be available, but the API will continue to work.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstraps shared services for the FastAPI lifecycle."""
    await MongoDatabase.connect()
    app.state.vector_store = VectorStore()
    
    # Pre-load library for instant menu speed (if ENABLE_FULL_LIBRARY_CACHE is true)
    from app.api.routers.library import preload_library_cache
    asyncio.create_task(preload_library_cache())

    print("VectorStore initialized successfully.")
    
    # Global Model Registry Seeding
    from app.db.postgres.engine import sessionmaker as AsyncSessionLocal
    from app.services.registry_seeding import (
        seed_global_models,
        seed_platform_sdk_tool,
        seed_platform_architect_agent,
    )
    async with AsyncSessionLocal() as db:
        await seed_global_models(db)
        await seed_platform_sdk_tool(db)
        await seed_platform_architect_agent(db)
    
    # Start LiveKit worker in separate process if credentials are configured
    # worker_process = None
    # if all([
    #     os.getenv("LIVEKIT_URL"),
    #     os.getenv("LIVEKIT_API_KEY"),
    #     os.getenv("LIVEKIT_API_SECRET")
    # ]):
    #     worker_process = multiprocessing.Process(target=start_livekit_worker, daemon=False)
    #     worker_process.start()
    #     print("LiveKit worker started in background process")
    # else:
    #     print("LiveKit credentials not found - voice mode disabled")
    
    yield
    
    # Cleanup
    # Cleanup
    # if worker_process and worker_process.is_alive():
    #     worker_process.terminate()
    #     worker_process.join(timeout=5)
    
    await MongoDatabase.close()


app = FastAPI(title="Rabbinic AI API", version="0.1.0", lifespan=lifespan)

# Add Middlewares
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# app.add_middleware(GZipMiddleware, minimum_size=500)

cors_origins = [
    'http://localhost:3000',
    'http://localhost:3001',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3001',
    'https://www.rishta.co.il',
    'http://10.0.0.10:3000',
    'https://reshet-self.vercel.app'
]

# If credentials are true, Starlette prohibits ["*"] origins.
# We handle this by ensuring specific origins are used if credentials are required.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Chat-ID"],
)

from app.api.routers import auth, chat, general, search, stt, texts, library, admin, tts, rag_admin, agent
from app.api.routers.agents import router as agents_router
from app.api.routers import org_units as org_units_router
from app.api.routers import rbac as rbac_router
from app.api.routers import audit as audit_router
from app.api.routers import rag_pipelines as rag_pipelines_router
from app.api.routers import rag_custom_operators as rag_custom_operators_router
from app.api.routers import models as models_router
from app.api.routers import tools as tools_router
from app.api.routers import artifacts as artifacts_router
from app.api.routers import stats as stats_router

app.include_router(auth.router, prefix="/auth", tags=["auth"])
from app.api.routers import agent_operators
app.include_router(agent_operators.router)
app.include_router(agents_router)
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(rag_admin.router, prefix="/admin/rag", tags=["rag-admin"])
app.include_router(rag_pipelines_router.router, prefix="/admin/pipelines", tags=["rag-pipelines"])
app.include_router(rag_custom_operators_router.router, prefix="/admin/rag/custom-operators", tags=["rag-custom-operators"])
app.include_router(artifacts_router.router, tags=["artifacts"])
app.include_router(stats_router.router, prefix="/admin", tags=["stats"])

from app.api.routers import knowledge_stores as knowledge_stores_router
app.include_router(knowledge_stores_router.router, prefix="/admin/knowledge-stores", tags=["knowledge-stores"])

app.include_router(models_router.router, tags=["models"])
app.include_router(tools_router.router, tags=["tools"])
app.include_router(org_units_router.router, prefix="/api", tags=["org-units"])
app.include_router(rbac_router.router, prefix="/api", tags=["rbac"])
app.include_router(audit_router.router, prefix="/api", tags=["audit"])
app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(agent.router)
app.include_router(chat.router, prefix="/chats", tags=["chats"])
app.include_router(general.router, tags=["general"])
app.include_router(search.router, tags=["search"])
app.include_router(stt.router, prefix="/stt", tags=["stt"])
app.include_router(texts.router, tags=["texts"])
app.include_router(tts.router, prefix="/tts", tags=["tts"])

from app.api.routers import voice_ws, rag_ws
app.include_router(voice_ws.router, prefix="/api/voice", tags=["voice"])
app.include_router(rag_ws.router, prefix="/admin/rag/ws", tags=["rag-websocket"])

@app.get("/health")
def health_check():
    """Reports service health for uptime monitors."""
    return {"status": "healthy"}


if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
