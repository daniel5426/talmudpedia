from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
import multiprocessing
import os
import asyncio
import logging
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
# Load environment variables BEFORE importing any modules that might need them
load_dotenv(Path(__file__).parent / ".env")

from app.db.connection import MongoDatabase
from vector_store import VectorStore

logger = logging.getLogger("backend.startup")
_INFRA_BOOTSTRAPPED = False


def _is_truthy(raw: str) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _auto_infra_bootstrap_enabled() -> bool:
    explicit = os.getenv("BACKEND_AUTO_INFRA_BOOTSTRAP")
    if explicit is not None:
        return _is_truthy(explicit)

    # Keep tests deterministic and fast.
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return False

    # Local-dev default.
    return True


def _is_port_open(host: str, port: int, timeout_seconds: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.25)
    return _is_port_open(host, port)


def _try_start_brew_service(service_name: str, host: str, port: int) -> bool:
    if _is_port_open(host, port):
        return True
    if shutil.which("brew") is None:
        logger.warning(
            "brew is unavailable; cannot auto-start %s (%s:%s)",
            service_name,
            host,
            port,
        )
        return False

    subprocess.run(
        ["brew", "services", "start", service_name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ready = _wait_for_port(host, port)
    if ready:
        logger.info("Started %s via brew services", service_name)
    else:
        logger.warning("Service %s is still unavailable on %s:%s", service_name, host, port)
    return ready


def _is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _parse_endpoint_host_port(endpoint: str) -> tuple[str, int] | None:
    parsed = urlparse((endpoint or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    default_port = 443 if parsed.scheme == "https" else 80
    return parsed.hostname, int(parsed.port or default_port)


def _ensure_local_moto_server_if_needed() -> None:
    endpoint = (os.getenv("APPS_BUNDLE_ENDPOINT") or "").strip()
    if not endpoint:
        return
    parsed = _parse_endpoint_host_port(endpoint)
    if not parsed:
        return
    host, port = parsed
    if not _is_local_host(host):
        return
    if _is_port_open(host, port):
        return

    moto_bin = os.getenv("MOTO_SERVER_BIN", "moto_server")
    if shutil.which(moto_bin) is None:
        logger.warning("Moto endpoint is local (%s) but `%s` is not installed", endpoint, moto_bin)
        return

    moto_log_path = Path(os.getenv("MOTO_LOG_PATH", "/tmp/talmudpedia-moto.log"))
    bind_host = "127.0.0.1"
    with moto_log_path.open("ab") as log_file:
        subprocess.Popen(
            [moto_bin, "-H", bind_host, "-p", str(port)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    if _wait_for_port(host, port):
        logger.info("Started local moto server on %s:%s", host, port)
    else:
        logger.warning("Failed to start local moto server on %s:%s", host, port)


def _ensure_local_bundle_bucket_if_needed() -> None:
    endpoint = (os.getenv("APPS_BUNDLE_ENDPOINT") or "").strip()
    bucket = (os.getenv("APPS_BUNDLE_BUCKET") or "").strip()
    if not endpoint or not bucket:
        return

    parsed = _parse_endpoint_host_port(endpoint)
    if not parsed:
        return
    host, _ = parsed
    if not _is_local_host(host):
        return

    try:
        import boto3
    except Exception:
        logger.warning("boto3 unavailable; cannot ensure local bundle bucket")
        return

    region = (os.getenv("APPS_BUNDLE_REGION") or "us-east-1").strip()
    access_key = (os.getenv("APPS_BUNDLE_ACCESS_KEY") or "test").strip() or "test"
    secret_key = (os.getenv("APPS_BUNDLE_SECRET_KEY") or "test").strip() or "test"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    try:
        existing = [item["Name"] for item in client.list_buckets().get("Buckets", [])]
        if bucket in existing:
            return

        create_kwargs = {"Bucket": bucket}
        if region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**create_kwargs)
        logger.info("Created local apps bundle bucket: %s", bucket)
    except Exception as exc:
        logger.warning("Failed ensuring local apps bundle bucket `%s`: %s", bucket, exc)


def _celery_worker_running() -> bool:
    if shutil.which("pgrep") is None:
        return False
    result = subprocess.run(
        ["pgrep", "-f", "celery -A app.workers.celery_app.celery_app worker"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _ensure_celery_worker_if_needed() -> None:
    if not _is_truthy(os.getenv("APPS_BUILDER_BUILD_AUTOMATION_ENABLED", "0")):
        return
    if _celery_worker_running():
        return

    redis_url = (os.getenv("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
    parsed = urlparse(redis_url)
    redis_host = parsed.hostname or "127.0.0.1"
    redis_port = int(parsed.port or 6379)
    if _is_local_host(redis_host) and not _is_port_open(redis_host, redis_port):
        logger.warning(
            "Redis is not reachable at %s:%s; skipping Celery auto-start",
            redis_host,
            redis_port,
        )
        return

    celery_log_path = Path(os.getenv("CELERY_LOG_PATH", "/tmp/talmudpedia-celery.log"))
    backend_dir = Path(__file__).resolve().parent
    celery_cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.workers.celery_app.celery_app",
        "worker",
        "-Q",
        "apps_build,default,ingestion,embedding",
        "-l",
        "info",
    ]
    with celery_log_path.open("ab") as log_file:
        subprocess.Popen(
            celery_cmd,
            cwd=str(backend_dir),
            env=os.environ.copy(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(1.0)
    if _celery_worker_running():
        logger.info("Started Celery worker for apps builder queues")
    else:
        logger.warning("Failed to auto-start Celery worker; check %s", celery_log_path)


def _ensure_local_draft_dev_runtime_if_needed() -> None:
    if not _is_truthy(os.getenv("APPS_BUILDER_DRAFT_DEV_ENABLED", "1")):
        return
    controller_url = (os.getenv("APPS_DRAFT_DEV_CONTROLLER_URL") or "").strip()
    embedded_enabled = _is_truthy(os.getenv("APPS_DRAFT_DEV_EMBEDDED_LOCAL_ENABLED", "1"))
    if controller_url or not embedded_enabled:
        return

    try:
        from app.services.published_app_draft_dev_local_runtime import get_local_draft_dev_runtime_manager

        manager = get_local_draft_dev_runtime_manager()
        manager.bootstrap()
        logger.info("Embedded local draft-dev runtime is ready")
    except Exception as exc:
        logger.warning("Failed to bootstrap embedded local draft-dev runtime: %s", exc)


def _bootstrap_local_infra_once() -> None:
    global _INFRA_BOOTSTRAPPED
    if _INFRA_BOOTSTRAPPED:
        return
    _INFRA_BOOTSTRAPPED = True

    if not _auto_infra_bootstrap_enabled():
        logger.info("Local infra bootstrap disabled")
        return

    logger.info("Running local infra bootstrap checks")
    _try_start_brew_service("postgresql@17", "127.0.0.1", 5432)
    _try_start_brew_service("redis", "127.0.0.1", 6379)
    _ensure_local_moto_server_if_needed()
    _ensure_local_bundle_bucket_if_needed()
    _ensure_celery_worker_if_needed()
    _ensure_local_draft_dev_runtime_if_needed()


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
    _bootstrap_local_infra_once()

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
        seed_builtin_tool_templates,
        seed_platform_architect_agent,
    )
    async with AsyncSessionLocal() as db:
        await seed_global_models(db)
        await seed_platform_sdk_tool(db)
        await seed_builtin_tool_templates(db)
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
    
    try:
        from app.services.published_app_draft_dev_local_runtime import get_local_draft_dev_runtime_manager

        await get_local_draft_dev_runtime_manager().stop_all()
    except Exception:
        # Cleanup failures should not block shutdown.
        pass

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
    allow_origin_regex=r"^https?://([a-z0-9-]+\.)*apps\.localhost(?::\d+)?$",
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
from app.api.routers import settings as settings_router
from app.api.routers import internal_auth as internal_auth_router
from app.api.routers import orchestration_internal as orchestration_internal_router
from app.api.routers import workload_security as workload_security_router
from app.api.routers import published_apps_admin as published_apps_admin_router
from app.api.routers import published_apps_public as published_apps_public_router

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
app.include_router(settings_router.router, prefix="/admin/settings", tags=["settings"])
app.include_router(workload_security_router.router)
app.include_router(internal_auth_router.router)
app.include_router(internal_auth_router.jwks_router)
app.include_router(orchestration_internal_router.router)
app.include_router(published_apps_admin_router.router)
app.include_router(published_apps_public_router.router)

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
