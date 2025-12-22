from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
import multiprocessing
import os

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

    print("VectorStore initialized successfully.")
    
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

# Add CORS middleware
from fastapi.middleware.cors import CORSMiddleware

cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://10.0.0.10:3000,reshet-self.vercel.app")
cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

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

from app.api.routers import agent, auth, chat, general, search, stt, texts, library, admin, tts

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(agent.router, tags=["agent"])
app.include_router(chat.router, prefix="/chats", tags=["chats"])
app.include_router(general.router, tags=["general"])
app.include_router(search.router, tags=["search"])
app.include_router(stt.router, prefix="/stt", tags=["stt"])
app.include_router(texts.router, tags=["texts"])
app.include_router(tts.router, prefix="/tts", tags=["tts"])

from app.api.routers import voice_ws
app.include_router(voice_ws.router, prefix="/api/voice", tags=["voice"])

@app.get("/health")
def health_check():
    """Reports service health for uptime monitors."""
    return {"status": "healthy"}


if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
