from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    ArtifactRun,
    ArtifactRunStatus,
    ArtifactTenantRuntimePolicy,
)


class ArtifactConcurrencyLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRuntimePolicySnapshot:
    queue_class: str
    concurrency_limit: int
    cpu_ms: int
    subrequests: int


class ArtifactRuntimePolicyService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_snapshot(self, *, tenant_id: UUID, queue_class: str) -> ArtifactRuntimePolicySnapshot:
        policy = await self._db.get(ArtifactTenantRuntimePolicy, tenant_id)
        if policy is None:
            policy = ArtifactTenantRuntimePolicy(tenant_id=tenant_id)
            self._db.add(policy)
            await self._db.flush()
        return ArtifactRuntimePolicySnapshot(
            queue_class=queue_class,
            concurrency_limit=self._concurrency_limit(policy, queue_class),
            cpu_ms=self._cpu_ms(policy, queue_class),
            subrequests=self._subrequests(policy, queue_class),
        )

    async def assert_capacity(self, *, tenant_id: UUID, queue_class: str) -> ArtifactRuntimePolicySnapshot:
        snapshot = await self.get_snapshot(tenant_id=tenant_id, queue_class=queue_class)
        active = await self._active_runs(tenant_id=tenant_id, queue_class=queue_class)
        if active >= snapshot.concurrency_limit:
            raise ArtifactConcurrencyLimitExceeded(
                f"Tenant concurrency limit reached for {queue_class}: {active}/{snapshot.concurrency_limit}"
            )
        return snapshot

    async def _active_runs(self, *, tenant_id: UUID, queue_class: str) -> int:
        result = await self._db.scalar(
            select(func.count(ArtifactRun.id)).where(
                ArtifactRun.tenant_id == tenant_id,
                ArtifactRun.queue_class == queue_class,
                ArtifactRun.status.in_([ArtifactRunStatus.RUNNING, ArtifactRunStatus.CANCEL_REQUESTED]),
            )
        )
        return int(result or 0)

    @staticmethod
    def _concurrency_limit(policy: ArtifactTenantRuntimePolicy, queue_class: str) -> int:
        if queue_class == "artifact_prod_interactive":
            return int(policy.interactive_concurrency_limit or 1)
        if queue_class == "artifact_prod_background":
            return int(policy.background_concurrency_limit or 1)
        return int(policy.test_concurrency_limit or 1)

    @staticmethod
    def _cpu_ms(policy: ArtifactTenantRuntimePolicy, queue_class: str) -> int:
        if queue_class == "artifact_prod_interactive":
            return int(policy.interactive_cpu_ms or 30000)
        if queue_class == "artifact_prod_background":
            return int(policy.background_cpu_ms or 60000)
        return int(policy.test_cpu_ms or 30000)

    @staticmethod
    def _subrequests(policy: ArtifactTenantRuntimePolicy, queue_class: str) -> int:
        if queue_class == "artifact_prod_interactive":
            return int(policy.interactive_subrequests or 50)
        if queue_class == "artifact_prod_background":
            return int(policy.background_subrequests or 100)
        return int(policy.test_subrequests or 50)
