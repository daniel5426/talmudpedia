from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    ArtifactRun,
    ArtifactRunStatus,
    ArtifactOrganizationRuntimePolicy,
)


class ArtifactConcurrencyLimitExceeded(RuntimeError):
    def __init__(self, *, queue_class: str, active_count: int, concurrency_limit: int):
        self.queue_class = queue_class
        self.active_count = active_count
        self.concurrency_limit = concurrency_limit
        super().__init__(
            f"Organization concurrency limit reached for {queue_class}: {active_count}/{concurrency_limit}"
        )


@dataclass(frozen=True)
class ArtifactRuntimePolicySnapshot:
    queue_class: str
    concurrency_limit: int
    cpu_ms: int
    subrequests: int


@dataclass(frozen=True)
class ArtifactRuntimeQueueStatus:
    queue_class: str
    active_count: int
    concurrency_limit: int


class ArtifactRuntimePolicyService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_snapshot(self, *, organization_id: UUID, queue_class: str) -> ArtifactRuntimePolicySnapshot:
        policy = await self._db.get(ArtifactOrganizationRuntimePolicy, organization_id)
        if policy is None:
            policy = ArtifactOrganizationRuntimePolicy(organization_id=organization_id)
            self._db.add(policy)
            await self._db.flush()
        return ArtifactRuntimePolicySnapshot(
            queue_class=queue_class,
            concurrency_limit=self._concurrency_limit(policy, queue_class),
            cpu_ms=self._cpu_ms(policy, queue_class),
            subrequests=self._subrequests(policy, queue_class),
        )

    async def reconcile_stale_test_runs(self, *, organization_id: UUID) -> None:
        await self._reconcile_stale_active_runs(organization_id=organization_id, queue_class="artifact_test")

    async def get_queue_status(self, *, organization_id: UUID, queue_class: str) -> ArtifactRuntimeQueueStatus:
        snapshot = await self.get_snapshot(organization_id=organization_id, queue_class=queue_class)
        active = await self._active_runs(organization_id=organization_id, queue_class=queue_class)
        return ArtifactRuntimeQueueStatus(
            queue_class=queue_class,
            active_count=active,
            concurrency_limit=snapshot.concurrency_limit,
        )

    async def assert_capacity(self, *, organization_id: UUID, queue_class: str) -> ArtifactRuntimePolicySnapshot:
        status = await self.get_queue_status(organization_id=organization_id, queue_class=queue_class)
        if status.active_count >= status.concurrency_limit:
            raise ArtifactConcurrencyLimitExceeded(
                queue_class=queue_class,
                active_count=status.active_count,
                concurrency_limit=status.concurrency_limit,
            )
        return await self.get_snapshot(organization_id=organization_id, queue_class=queue_class)

    async def _active_runs(self, *, organization_id: UUID, queue_class: str) -> int:
        await self._reconcile_stale_active_runs(organization_id=organization_id, queue_class=queue_class)
        result = await self._db.scalar(
            select(func.count(ArtifactRun.id)).where(
                ArtifactRun.organization_id == organization_id,
                ArtifactRun.queue_class == queue_class,
                ArtifactRun.status.in_([ArtifactRunStatus.RUNNING, ArtifactRunStatus.CANCEL_REQUESTED]),
            )
        )
        return int(result or 0)

    @staticmethod
    def _concurrency_limit(policy: ArtifactOrganizationRuntimePolicy, queue_class: str) -> int:
        if queue_class == "artifact_prod_interactive":
            return int(policy.interactive_concurrency_limit or 1)
        if queue_class == "artifact_prod_background":
            return int(policy.background_concurrency_limit or 1)
        return int(policy.test_concurrency_limit or 10)

    @staticmethod
    def _cpu_ms(policy: ArtifactOrganizationRuntimePolicy, queue_class: str) -> int:
        if queue_class == "artifact_prod_interactive":
            return int(policy.interactive_cpu_ms or 30000)
        if queue_class == "artifact_prod_background":
            return int(policy.background_cpu_ms or 60000)
        return int(policy.test_cpu_ms or 30000)

    @staticmethod
    def _subrequests(policy: ArtifactOrganizationRuntimePolicy, queue_class: str) -> int:
        if queue_class == "artifact_prod_interactive":
            return int(policy.interactive_subrequests or 50)
        if queue_class == "artifact_prod_background":
            return int(policy.background_subrequests or 100)
        return int(policy.test_subrequests or 50)

    async def _reconcile_stale_active_runs(self, *, organization_id: UUID, queue_class: str) -> None:
        if queue_class != "artifact_test":
            return
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._stale_test_run_timeout_seconds())
        result = await self._db.execute(
            select(ArtifactRun).where(
                ArtifactRun.organization_id == organization_id,
                ArtifactRun.queue_class == queue_class,
                ArtifactRun.status.in_([ArtifactRunStatus.QUEUED, ArtifactRunStatus.RUNNING, ArtifactRunStatus.CANCEL_REQUESTED]),
                or_(
                    ArtifactRun.started_at <= cutoff,
                    (ArtifactRun.started_at.is_(None) & (ArtifactRun.created_at <= cutoff)),
                ),
            )
        )
        stale_runs = list(result.scalars().all())
        if not stale_runs:
            return
        reconciled_at = datetime.now(timezone.utc)
        for run in stale_runs:
            run.finished_at = reconciled_at
            run.duration_ms = self._duration_ms(run=run, finished_at=reconciled_at)
            run.runtime_metadata = {
                **dict(run.runtime_metadata or {}),
                "stale_reconciled": True,
                "stale_reconciled_at": reconciled_at.isoformat(),
            }
            if run.status == ArtifactRunStatus.CANCEL_REQUESTED:
                run.status = ArtifactRunStatus.CANCELLED
                run.cancel_requested = True
                continue
            run.status = ArtifactRunStatus.FAILED
            run.error_payload = {
                **dict(run.error_payload or {}),
                "code": "STALE_ARTIFACT_TEST_RUN_RECONCILED",
                "message": "Artifact test run was marked failed after exceeding the stale active-run timeout.",
            }
        await self._db.flush()

    @staticmethod
    def _stale_test_run_timeout_seconds() -> int:
        raw = os.getenv("ARTIFACT_TEST_STALE_RUN_TIMEOUT_SECONDS")
        if raw is None:
            return 900
        try:
            return max(60, int(raw))
        except (TypeError, ValueError):
            return 900

    @staticmethod
    def _duration_ms(*, run: ArtifactRun, finished_at: datetime) -> int:
        started_at = run.started_at or run.created_at or finished_at
        return max(0, int((finished_at - started_at).total_seconds() * 1000))
