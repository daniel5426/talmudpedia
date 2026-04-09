from __future__ import annotations

from uuid import UUID

from app.workers.celery_app import celery_app
from app.workers.async_runner import run_async


@celery_app.task(bind=True, name="app.workers.artifact_tasks.execute_artifact_run_task")
def execute_artifact_run_task(self, run_id: str):
    async def _run() -> None:
        from app.db.postgres.engine import sessionmaker as async_sessionmaker
        from app.services.artifact_runtime.execution_service import ArtifactExecutionService
        from app.services.artifact_runtime.policy_service import ArtifactConcurrencyLimitExceeded

        async with async_sessionmaker() as db:
            service = ArtifactExecutionService(db)
            try:
                await service.execute_enqueued_run(UUID(str(run_id)))
            except ArtifactConcurrencyLimitExceeded as exc:
                raise self.retry(
                    exc=exc,
                    countdown=min(30, 2 ** int(self.request.retries or 0)),
                    max_retries=5,
                )

    return run_async(_run())
