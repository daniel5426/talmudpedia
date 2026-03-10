from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import ArtifactRevision

from .bundle_cache import ArtifactBundleCache
from .difysandbox_adapter import DifySandboxAdapter
from .schemas import ArtifactWorkerExecutionRequest, ArtifactWorkerExecutionResponse


class ArtifactWorkerExecutor:
    def __init__(self) -> None:
        self._bundle_cache = ArtifactBundleCache()
        self._adapter = DifySandboxAdapter()

    async def execute(self, db: AsyncSession, request: ArtifactWorkerExecutionRequest) -> ArtifactWorkerExecutionResponse:
        revision = await db.scalar(
            select(ArtifactRevision).where(
                ArtifactRevision.id == request.revision_id,
                ArtifactRevision.tenant_id == request.tenant_id,
            )
        )
        if revision is None:
            return ArtifactWorkerExecutionResponse(
                status="failed",
                error={"message": "Artifact revision not found", "code": "REVISION_NOT_FOUND"},
                events=[self._event("run_failed", {"message": "Artifact revision not found"})],
            )

        events = [
            self._event(
                "revision_loaded",
                {
                    "revision_id": str(revision.id),
                    "artifact_id": str(revision.artifact_id) if revision.artifact_id else None,
                    "bundle_hash": revision.bundle_hash,
                    "is_ephemeral": bool(revision.is_ephemeral),
                },
            )
        ]
        bundle_resolution = self._bundle_cache.ensure_bundle_dir(revision)
        bundle_dir = bundle_resolution.bundle_dir
        events.append(
            self._event(
                "bundle_ready",
                {
                    "bundle_hash": revision.bundle_hash,
                    "cache_hit": bundle_resolution.cache_hit,
                    "payload_source": bundle_resolution.payload_source,
                    "bundle_dir": str(bundle_dir),
                },
            )
        )
        started_ts = datetime.now(timezone.utc).isoformat()
        events.append(
            self._event(
                "worker_execute_started",
                {
                    "ts": started_ts,
                    "domain": request.domain,
                    "worker_mode": "direct",
                    "timeout_seconds": int(request.resource_limits.get("timeout_seconds") or 30),
                },
            )
        )
        result = self._adapter.execute(
            bundle_dir=bundle_dir,
            payload=request.model_dump(mode="json"),
            timeout_seconds=int(request.resource_limits.get("timeout_seconds") or 30),
        )
        events.append(
            self._event(
                "run_started",
                {
                    "ts": started_ts,
                    "domain": request.domain,
                    "worker_id": result.worker_id,
                },
            )
        )
        if result.stdout_excerpt:
            events.append(self._event("stdout", {"content": result.stdout_excerpt}))
        if result.stderr_excerpt:
            events.append(self._event("stderr", {"content": result.stderr_excerpt}))
        events.append(
            self._event(
                "run_completed" if result.status == "completed" else "run_failed",
                {
                    "duration_ms": result.duration_ms,
                    "sandbox_session_id": result.sandbox_session_id,
                    "code": (result.error or {}).get("code") if result.error else None,
                },
            )
        )
        return ArtifactWorkerExecutionResponse(
            status=result.status,
            result=result.result,
            error=result.error,
            stdout_excerpt=result.stdout_excerpt,
            stderr_excerpt=result.stderr_excerpt,
            events=events,
            duration_ms=result.duration_ms,
            worker_id=result.worker_id,
            sandbox_session_id=result.sandbox_session_id,
        )

    def cancel(self, sandbox_session_id: str) -> None:
        self._adapter.cancel(sandbox_session_id=sandbox_session_id)

    @staticmethod
    def _event(event_name: str, data: dict) -> dict:
        ts = datetime.now(timezone.utc).isoformat()
        return {
            "event_type": event_name,
            "payload": {
                "ts": ts,
                "event": event_name,
                "name": event_name,
                "data": data,
                "source_run_id": None,
            },
        }
