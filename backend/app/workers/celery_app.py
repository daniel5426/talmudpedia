import os
from celery import Celery
from kombu import Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rag_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.tasks"]
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
    ),
    
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    
    task_routes={
        "app.workers.tasks.ingest_documents_task": {"queue": "ingestion"},
        "app.workers.tasks.embed_chunks_task": {"queue": "embedding"},
        "app.workers.tasks.build_published_app_revision_task": {"queue": "apps_build"},
        "app.workers.tasks.publish_published_app_task": {"queue": "apps_build"},
        "app.workers.tasks.reap_published_app_draft_dev_sessions_task": {"queue": "default"},
    },
    
    result_expires=86400,
    
    broker_connection_retry_on_startup=True,
)
