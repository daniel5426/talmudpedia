from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from typing import Any
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_worker.schemas import ArtifactWorkerExecutionRequest
from app.db.postgres.models.artifact_runtime import (
    Artifact,
    ArtifactRevision,
    ArtifactRunDomain,
    ArtifactRunStatus,
)

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
        dependencies: list[str] | None,
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
        requested_dependencies = list(dependencies or [])
        if request_code:
            same_code = request_code == str((revision.source_code if revision else "") or "")
            same_dependencies = requested_dependencies == list((revision.python_dependencies if revision else []) or [])
            if artifact is None or not (same_code and same_dependencies):
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
                    python_dependencies=requested_dependencies or list((revision.python_dependencies if revision else []) or []),
                    config_schema=list((revision.config_schema if revision else []) or []),
                    inputs=list((revision.inputs if revision else []) or []),
                    outputs=list((revision.outputs if revision else []) or []),
                    reads=list((revision.reads if revision else []) or []),
                    writes=list((revision.writes if revision else []) or []),
                )
        elif revision is None:
            raise ValueError("A saved artifact or python_code is required for test execution")
        elif requested_dependencies and requested_dependencies != list((revision.python_dependencies if revision else []) or []):
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
                source_code=str((revision.source_code if revision else "") or ""),
                python_dependencies=requested_dependencies,
                config_schema=list((revision.config_schema if revision else []) or []),
                inputs=list((revision.inputs if revision else []) or []),
                outputs=list((revision.outputs if revision else []) or []),
                reads=list((revision.reads if revision else []) or []),
                writes=list((revision.writes if revision else []) or []),
            )

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

    async def execute_live_run(
        self,
        *,
        tenant_id: UUID,
        created_by: UUID | None,
        revision_id: UUID,
        domain: ArtifactRunDomain | str,
        queue_class: str,
        input_payload: Any,
        config_payload: dict[str, Any] | None = None,
        context_payload: dict[str, Any] | None = None,
        require_published: bool = True,
        wait_timeout_seconds: float = 30.0,
    ):
        normalized_domain = self._normalize_domain(domain)
        revision = await self._resolve_revision_for_execution(
            revision_id=revision_id,
            tenant_id=tenant_id,
            require_published=require_published and normalized_domain != ArtifactRunDomain.TEST,
        )
        artifact = None
        if revision.artifact_id is not None:
            artifact = await self._registry.get_tenant_artifact(
                artifact_id=revision.artifact_id,
                tenant_id=tenant_id,
            )

        run = await self._runs.create_run(
            tenant_id=tenant_id,
            artifact=artifact,
            revision=revision,
            domain=normalized_domain,
            input_payload=input_payload,
            config_payload=config_payload,
            context_payload={
                **dict(context_payload or {}),
                "tenant_id": str(tenant_id),
                "artifact_id": str(revision.artifact_id) if revision.artifact_id else None,
                "revision_id": str(revision.id),
                "domain": normalized_domain.value,
                "created_by": str(created_by) if created_by else None,
            },
            queue_class=queue_class,
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
                            "artifact_id": str(revision.artifact_id) if revision.artifact_id else None,
                            "revision_id": str(revision.id),
                            "is_ephemeral_revision": bool(revision.is_ephemeral),
                            "queue_class": run.queue_class,
                            "require_published": bool(require_published),
                        },
                    },
                }
            ],
        )
        await self._db.commit()

        if queue_class == "artifact_prod_interactive":
            logger.info("Executing interactive artifact run run_id=%s queue=%s", run.id, queue_class)
            await self.execute_enqueued_run(run.id)
        else:
            await self.enqueue_run(run.id)

        return await self.wait_for_terminal_state(run.id, timeout_seconds=wait_timeout_seconds)

    async def enqueue_run(self, run_id: UUID) -> None:
        run = await self._runs.get_run(run_id=run_id)
        if run is None:
            return
        if artifact_run_task_eager():
            logger.info("Executing artifact run eagerly run_id=%s", run_id)
            await self.execute_enqueued_run(run_id)
            return
        from app.workers.artifact_tasks import execute_artifact_run_task

        logger.info("Enqueueing artifact run run_id=%s queue=%s", run_id, run.queue_class)
        execute_artifact_run_task.apply_async(args=[str(run_id)], queue=run.queue_class)

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
            domain=self._enum_text(run.domain),
            inputs=run.input_payload,
            config=dict(run.config_payload or {}),
            context=dict(run.context_payload or {}),
            bundle_hash=str((run.revision.bundle_hash if run.revision else "") or ""),
            bundle_storage_key=str((run.revision.bundle_storage_key if run.revision else "") or "") or None,
            dependency_hash=str((run.revision.dependency_hash if run.revision else "") or ""),
            dependency_manifest=list((run.revision.python_dependencies if run.revision else []) or []),
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
                        "data": {"domain": self._enum_text(run.domain)},
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

    async def _resolve_revision_for_execution(
        self,
        *,
        revision_id: UUID,
        tenant_id: UUID,
        require_published: bool,
    ) -> ArtifactRevision:
        revision = await self._registry.get_revision(revision_id=revision_id, tenant_id=tenant_id)
        if revision is None:
            raise ValueError("Artifact revision not found")
        if require_published and (not revision.is_published or revision.is_ephemeral):
            raise PermissionError("Live artifact execution requires a published immutable revision")
        return revision

    @staticmethod
    def _normalize_domain(domain: ArtifactRunDomain | str) -> ArtifactRunDomain:
        if isinstance(domain, ArtifactRunDomain):
            return domain
        return ArtifactRunDomain(str(domain).strip().lower())

    @staticmethod
    def _enum_text(value: Any) -> str:
        return str(getattr(value, "value", value))
