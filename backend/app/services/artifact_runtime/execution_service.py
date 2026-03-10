from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from typing import Any
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_worker.schemas import ArtifactWorkerExecutionRequest
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactRevision, ArtifactRunStatus

from .difysandbox_client import DifySandboxWorkerClient
from .registry_service import ArtifactRegistryService
from .revision_service import ArtifactRevisionService
from .run_service import ArtifactRunService

logger = logging.getLogger("artifact.runtime")


def artifact_run_task_eager() -> bool:
    raw = os.getenv("ARTIFACT_RUN_TASK_EAGER")
    if raw is not None:
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


class ArtifactExecutionService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._registry = ArtifactRegistryService(db)
        self._revisions = ArtifactRevisionService(db)
        self._runs = ArtifactRunService(db)

    async def start_test_run(
        self,
        *,
        tenant_id: UUID,
        created_by: UUID | None,
        artifact_id: UUID | None,
        python_code: str | None,
        input_data: Any,
        config: dict[str, Any] | None,
        input_type: str,
        output_type: str,
    ):
        artifact = None
        revision = None
        if artifact_id is not None:
            artifact = await self._registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=tenant_id)
            if artifact is None:
                raise ValueError("Artifact not found")
            revision = artifact.latest_draft_revision or artifact.latest_published_revision
            if revision is None:
                raise ValueError("Artifact has no executable revision")

        request_code = str(python_code or "").strip()
        if request_code:
            if artifact is None or request_code != str((revision.source_code if revision else "") or ""):
                revision = await self._revisions.create_ephemeral_revision(
                    tenant_id=tenant_id,
                    created_by=created_by,
                    artifact=artifact,
                    display_name=artifact.display_name if artifact else "Unsaved Artifact",
                    description=artifact.description if artifact else None,
                    category=artifact.category if artifact else "custom",
                    scope=(getattr(artifact.scope, "value", artifact.scope) if artifact else "rag"),
                    input_type=input_type or (artifact.input_type if artifact else "raw_documents"),
                    output_type=output_type or (artifact.output_type if artifact else "raw_documents"),
                    source_code=request_code,
                    config_schema=list((revision.config_schema if revision else []) or []),
                    inputs=list((revision.inputs if revision else []) or []),
                    outputs=list((revision.outputs if revision else []) or []),
                    reads=list((revision.reads if revision else []) or []),
                    writes=list((revision.writes if revision else []) or []),
                )
        elif revision is None:
            raise ValueError("A saved artifact or python_code is required for test execution")

        run = await self._runs.create_test_run(
            tenant_id=tenant_id,
            artifact=artifact,
            revision=revision,
            input_payload={"value": input_data},
            config_payload=dict(config or {}),
            context_payload={
                "tenant_id": str(tenant_id),
                "artifact_id": str(artifact.id) if artifact else None,
                "revision_id": str(revision.id),
                "domain": "test",
            },
        )
        await self._runs.add_events(
            run,
            [
                {
                    "event_type": "run_prepared",
                    "payload": {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "run_prepared",
                        "name": "run_prepared",
                        "data": {
                            "artifact_id": str(artifact.id) if artifact else None,
                            "revision_id": str(revision.id),
                            "is_ephemeral_revision": bool(revision.is_ephemeral),
                            "used_unsaved_code": bool(request_code),
                            "queue_class": run.queue_class,
                        },
                    },
                }
            ],
        )
        await self._db.commit()
        await self.enqueue_run(run.id)
        return run

    async def enqueue_run(self, run_id: UUID) -> None:
        if artifact_run_task_eager():
            logger.info("Executing artifact run eagerly run_id=%s", run_id)
            await self.execute_enqueued_run(run_id)
            return
        from app.workers.artifact_tasks import execute_artifact_run_task

        logger.info("Enqueueing artifact run run_id=%s queue=artifact_test", run_id)
        execute_artifact_run_task.delay(str(run_id))

    async def execute_enqueued_run(self, run_id: UUID) -> None:
        run = await self._runs.get_run(run_id=run_id)
        if run is None:
            return
        if run.status == ArtifactRunStatus.CANCELLED:
            await self._db.commit()
            return

        worker_request = ArtifactWorkerExecutionRequest(
            run_id=run.id,
            tenant_id=run.tenant_id,
            artifact_id=run.artifact_id,
            revision_id=run.revision_id,
            domain=run.domain.value,
            inputs=dict(run.input_payload or {}),
            config=dict(run.config_payload or {}),
            context=dict(run.context_payload or {}),
            resource_limits={"timeout_seconds": 30},
        )

        client = DifySandboxWorkerClient(self._db)
        await self._runs.mark_running(run)
        await self._runs.add_events(
            run,
            [
                {
                    "event_type": "run_started",
                    "payload": {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "run_started",
                        "name": "run_started",
                        "data": {"domain": run.domain.value},
                    },
                }
                ,
                {
                    "event_type": "worker_dispatch_started",
                    "payload": {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "worker_dispatch_started",
                        "name": "worker_dispatch_started",
                        "data": {
                            "run_id": str(run.id),
                            "revision_id": str(run.revision_id),
                            "worker_client_mode": client._mode(),
                            "queue_class": run.queue_class,
                        },
                    },
                },
            ],
        )
        await self._db.commit()

        try:
            logger.info(
                "Dispatching artifact run run_id=%s revision_id=%s worker_mode=%s",
                run.id,
                run.revision_id,
                client._mode(),
            )
            response = await client.execute(worker_request)
        except Exception as exc:
            run = await self._runs.get_run(run_id=run_id)
            if run is None:
                return
            await self._runs.mark_failed(
                run,
                error_payload={"message": str(exc), "code": "WORKER_REQUEST_FAILED"},
                stdout_excerpt=None,
                stderr_excerpt=None,
                duration_ms=None,
            )
            await self._runs.add_events(
                run,
                [
                    {
                        "event_type": "run_failed",
                        "payload": {
                            "event": "run_failed",
                            "name": "run_failed",
                            "data": {"message": str(exc), "phase": "worker_request"},
                        },
                    }
                ],
            )
            await self._db.commit()
            return

        run = await self._runs.get_run(run_id=run_id)
        if run is None:
            return
        run.worker_id = response.worker_id
        run.sandbox_session_id = response.sandbox_session_id
        if run.cancel_requested and run.sandbox_session_id:
            try:
                await client.cancel(run.sandbox_session_id)
            except Exception:
                pass

        if response.status == "completed" and not run.cancel_requested:
            await self._runs.mark_completed(
                run,
                result_payload=response.result,
                stdout_excerpt=response.stdout_excerpt,
                stderr_excerpt=response.stderr_excerpt,
                duration_ms=response.duration_ms,
            )
        elif run.cancel_requested:
            await self._runs.mark_cancelled(run, duration_ms=response.duration_ms)
        else:
            await self._runs.mark_failed(
                run,
                error_payload=response.error,
                stdout_excerpt=response.stdout_excerpt,
                stderr_excerpt=response.stderr_excerpt,
                duration_ms=response.duration_ms,
            )
        await self._runs.add_events(
            run,
            [
                {
                    "event_type": "worker_dispatch_finished",
                    "payload": {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "worker_dispatch_finished",
                        "name": "worker_dispatch_finished",
                        "data": {
                            "status": response.status,
                            "worker_id": response.worker_id,
                            "sandbox_session_id": response.sandbox_session_id,
                            "duration_ms": response.duration_ms,
                        },
                    },
                }
            ],
        )
        await self._runs.add_events(run, response.events)
        await self._db.commit()

    async def wait_for_terminal_state(self, run_id: UUID, *, timeout_seconds: float = 30.0):
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            run = await self._runs.get_run(run_id=run_id)
            if run is not None and run.status in {
                ArtifactRunStatus.COMPLETED,
                ArtifactRunStatus.FAILED,
                ArtifactRunStatus.CANCELLED,
            }:
                return run
            if asyncio.get_running_loop().time() >= deadline:
                return run
            await asyncio.sleep(0.2)

    async def cancel_run(self, *, run_id: UUID, tenant_id: UUID):
        run = await self._runs.get_run(run_id=run_id)
        if run is None or str(run.tenant_id) != str(tenant_id):
            raise ValueError("Artifact run not found")
        await self._runs.mark_cancel_requested(run)
        if run.sandbox_session_id and run.status == ArtifactRunStatus.CANCEL_REQUESTED:
            client = DifySandboxWorkerClient(self._db)
            try:
                await client.cancel(run.sandbox_session_id)
                await self._runs.mark_cancelled(run)
            except Exception:
                pass
        await self._runs.add_events(
            run,
            [
                {
                    "event_type": "run_cancelled" if run.status == ArtifactRunStatus.CANCELLED else "run_cancel_requested",
                    "payload": {
                        "event": "run_cancel_requested",
                        "name": "run_cancel_requested",
                        "data": {"status": run.status.value},
                    },
                }
            ],
        )
        await self._db.commit()
        return run
