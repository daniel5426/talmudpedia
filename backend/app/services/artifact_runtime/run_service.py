from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.artifact_runtime import (
    Artifact,
    ArtifactRevision,
    ArtifactRun,
    ArtifactRunDomain,
    ArtifactRunEvent,
    ArtifactRunStatus,
)


class ArtifactRunService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_run(
        self,
        *,
        tenant_id: UUID,
        artifact: Artifact | None,
        revision: ArtifactRevision,
        domain: ArtifactRunDomain | str,
        input_payload: Any,
        config_payload: dict[str, Any] | None,
        context_payload: dict[str, Any] | None,
        queue_class: str,
    ) -> ArtifactRun:
        normalized_domain = self._normalize_domain(domain)
        run = ArtifactRun(
            tenant_id=tenant_id,
            artifact_id=artifact.id if artifact else revision.artifact_id,
            revision_id=revision.id,
            domain=normalized_domain,
            status=ArtifactRunStatus.QUEUED,
            queue_class=queue_class,
            sandbox_backend="cloudflare_workers",
            input_payload=input_payload,
            config_payload=dict(config_payload or {}),
            context_payload=dict(context_payload or {}),
            runtime_metadata={},
        )
        self._db.add(run)
        await self._db.flush()
        await self.add_events(
            run,
            [
                {
                    "event_type": "run_queued",
                    "payload": {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "run_queued",
                        "name": "run_queued",
                        "data": {
                            "domain": normalized_domain.value,
                            "queue_class": queue_class,
                        },
                    },
                }
            ],
        )
        return run

    async def create_test_run(
        self,
        *,
        tenant_id: UUID,
        artifact: Artifact | None,
        revision: ArtifactRevision,
        input_payload: Any,
        config_payload: dict[str, Any] | None,
        context_payload: dict[str, Any] | None,
        queue_class: str = "artifact_test",
    ) -> ArtifactRun:
        return await self.create_run(
            tenant_id=tenant_id,
            artifact=artifact,
            revision=revision,
            domain=ArtifactRunDomain.TEST,
            input_payload=input_payload,
            config_payload=config_payload,
            context_payload=context_payload,
            queue_class=queue_class,
        )

    async def get_run(self, *, run_id: UUID) -> ArtifactRun | None:
        return await self._db.scalar(
            select(ArtifactRun)
            .where(ArtifactRun.id == run_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(ArtifactRun.events),
                selectinload(ArtifactRun.revision),
                selectinload(ArtifactRun.artifact),
            )
        )

    async def list_events(self, *, run_id: UUID) -> list[ArtifactRunEvent]:
        result = await self._db.execute(
            select(ArtifactRunEvent)
            .where(ArtifactRunEvent.run_id == run_id)
            .order_by(ArtifactRunEvent.sequence.asc())
        )
        return list(result.scalars().all())

    async def mark_running(self, run: ArtifactRun, *, worker_id: str | None = None, sandbox_session_id: str | None = None) -> None:
        run.status = ArtifactRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        if worker_id:
            run.worker_id = worker_id
        if sandbox_session_id:
            run.sandbox_session_id = sandbox_session_id

    async def mark_completed(
        self,
        run: ArtifactRun,
        *,
        result_payload: dict[str, Any] | None,
        stdout_excerpt: str | None,
        stderr_excerpt: str | None,
        duration_ms: int | None,
    ) -> None:
        run.status = ArtifactRunStatus.COMPLETED
        run.result_payload = result_payload
        run.stdout_excerpt = stdout_excerpt
        run.stderr_excerpt = stderr_excerpt
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = duration_ms

    async def mark_failed(
        self,
        run: ArtifactRun,
        *,
        error_payload: dict[str, Any] | None,
        stdout_excerpt: str | None,
        stderr_excerpt: str | None,
        duration_ms: int | None,
    ) -> None:
        run.status = ArtifactRunStatus.FAILED
        run.error_payload = error_payload
        run.stdout_excerpt = stdout_excerpt
        run.stderr_excerpt = stderr_excerpt
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = duration_ms

    async def mark_cancel_requested(self, run: ArtifactRun) -> None:
        run.cancel_requested = True
        if run.status == ArtifactRunStatus.QUEUED:
            run.status = ArtifactRunStatus.CANCELLED
            run.finished_at = datetime.now(timezone.utc)
            run.duration_ms = 0
        elif run.status == ArtifactRunStatus.RUNNING:
            run.status = ArtifactRunStatus.CANCEL_REQUESTED

    async def mark_cancelled(self, run: ArtifactRun, *, duration_ms: int | None = None) -> None:
        run.status = ArtifactRunStatus.CANCELLED
        run.cancel_requested = True
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = duration_ms

    async def add_events(self, run: ArtifactRun, events: Iterable[dict[str, Any]]) -> None:
        await self._db.flush()
        existing_count = await self._db.scalar(
            select(func.max(ArtifactRunEvent.sequence))
            .where(ArtifactRunEvent.run_id == run.id)
        )
        next_sequence = int(existing_count or 0)
        for item in events:
            next_sequence += 1
            event = ArtifactRunEvent(
                run_id=run.id,
                sequence=next_sequence,
                event_type=str(item.get("event_type") or item.get("event") or "event"),
                payload=dict(item.get("payload") or item),
            )
            self._db.add(event)

    @staticmethod
    def _normalize_domain(domain: ArtifactRunDomain | str) -> ArtifactRunDomain:
        if isinstance(domain, ArtifactRunDomain):
            return domain
        return ArtifactRunDomain(str(domain).strip().lower())
