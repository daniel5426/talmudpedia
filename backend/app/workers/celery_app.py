import os

from celery import Celery
from kombu import Queue

from app.core.env_loader import load_backend_env, running_under_pytest

load_backend_env(override=not running_under_pytest())

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _is_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


_quota_beat_enabled = _is_truthy(os.getenv("QUOTA_WORKERS_BEAT_ENABLED", "1"))
_expire_interval_seconds = int(os.getenv("QUOTA_EXPIRE_SWEEP_INTERVAL_SECONDS", "300"))
_reconcile_interval_seconds = int(os.getenv("QUOTA_RECONCILE_INTERVAL_SECONDS", "1800"))
_task_always_eager = _is_truthy(os.getenv("CELERY_TASK_ALWAYS_EAGER", "1" if running_under_pytest() else "0"))
_beat_schedule = {}
if _quota_beat_enabled:
    _beat_schedule = {
        "usage-quota-expire-reservations": {
            "task": "app.workers.tasks.expire_usage_quota_reservations_task",
            "schedule": max(60, _expire_interval_seconds),
        },
        "usage-quota-reconcile-counters": {
            "task": "app.workers.tasks.reconcile_usage_quota_counters_task",
            "schedule": max(300, _reconcile_interval_seconds),
        },
    }

celery_app = Celery(
    "rag_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.tasks", "app.workers.artifact_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("ingestion", routing_key="ingestion"),
        Queue("embedding", routing_key="embedding"),
        Queue("apps_build", routing_key="apps_build"),
        Queue("agent_runs", routing_key="agent_runs"),
        Queue("artifact_prod_interactive", routing_key="artifact_prod_interactive"),
        Queue("artifact_prod_background", routing_key="artifact_prod_background"),
        Queue("artifact_test", routing_key="artifact_test"),
    ),
    
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    
    task_routes={
        "app.workers.tasks.ingest_documents_task": {"queue": "ingestion"},
        "app.workers.tasks.embed_chunks_task": {"queue": "embedding"},
        "app.workers.tasks.execute_agent_run_task": {"queue": "agent_runs"},
        "app.workers.tasks.reap_published_app_draft_dev_sessions_task": {"queue": "default"},
        "app.workers.tasks.expire_usage_quota_reservations_task": {"queue": "default"},
        "app.workers.tasks.reconcile_usage_quota_counters_task": {"queue": "default"},
    },

    beat_schedule=_beat_schedule,

    result_expires=86400,
    task_always_eager=_task_always_eager,
    task_eager_propagates=True,
    
    broker_connection_retry_on_startup=True,
)
