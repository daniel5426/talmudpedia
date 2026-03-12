from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    Artifact,
    ArtifactRunDomain,
    ArtifactRunStatus,
)

from .cloudflare_dispatch_client import CloudflareDispatchClient
from .cloudflare_dispatch_client import CloudflareDispatchHTTPError
from .deployment_service import ArtifactDeploymentService
from .policy_service import ArtifactConcurrencyLimitExceeded, ArtifactRuntimePolicyService
from .registry_service import ArtifactRegistryService
from .revision_service import ArtifactRevisionService
from .runtime_mode import RUNTIME_MODE_STANDARD_WORKER_TEST, artifact_cloudflare_runtime_mode
from .run_service import ArtifactRunService
from .source_utils import normalize_artifact_source

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
        self._deployments = ArtifactDeploymentService(db)
        self._policies = ArtifactRuntimePolicyService(db)

    async def start_test_run(
        self,
        *,
        tenant_id: UUID,
        created_by: UUID | None,
        artifact_id: UUID | None,
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        input_data: Any,
        config: dict[str, Any] | None,
        dependencies: list[str] | None,
        kind: str | None,
        runtime_target: str | None,
        capabilities: dict[str, Any] | None,
        config_schema: dict[str, Any] | None,
        agent_contract: dict[str, Any] | None,
        rag_contract: dict[str, Any] | None,
        tool_contract: dict[str, Any] | None,
    ):
        artifact: Artifact | None = None
        revision = None
        if artifact_id is not None:
            artifact = await self._registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=tenant_id)
            if artifact is None:
                raise ValueError("Artifact not found")
            revision = artifact.latest_draft_revision or artifact.latest_published_revision
            if revision is None:
                raise ValueError("Artifact has no executable revision")

        requested_dependencies = list(dependencies or [])
        source = None
        if source_files:
            source = normalize_artifact_source(
                source_files=source_files,
                entry_module_path=entry_module_path or (revision.entry_module_path if revision else None),
            )
        should_materialize = artifact is None or source is not None
        if revision is not None and source is not None:
            current_files = list(revision.source_files or [])
            should_materialize = (
                current_files != source.source_files
                or source.entry_module_path != revision.entry_module_path
                or requested_dependencies != list(revision.python_dependencies or [])
            )

        if should_materialize:
            revision = await self._revisions.create_ephemeral_revision(
                tenant_id=tenant_id,
                created_by=created_by,
                artifact=artifact,
                display_name=artifact.display_name if artifact else "Unsaved Artifact",
                description=artifact.description if artifact else None,
                kind=(getattr(artifact.kind, "value", artifact.kind) if artifact else kind),
                source_files=source.source_files if source is not None else None,
                entry_module_path=source.entry_module_path if source is not None else None,
                python_dependencies=requested_dependencies or list((revision.python_dependencies if revision else []) or []),
                runtime_target=runtime_target or str((revision.runtime_target if revision else None) or "cloudflare_workers"),
                capabilities=dict(capabilities or dict((revision.capabilities if revision else {}) or {})),
                config_schema=dict(config_schema or dict((revision.config_schema if revision else {}) or {})),
                agent_contract=agent_contract if agent_contract is not None else (dict(revision.agent_contract or {}) if revision and revision.agent_contract is not None else None),
                rag_contract=rag_contract if rag_contract is not None else (dict(revision.rag_contract or {}) if revision and revision.rag_contract is not None else None),
                tool_contract=tool_contract if tool_contract is not None else (dict(revision.tool_contract or {}) if revision and revision.tool_contract is not None else None),
            )
        elif revision is None:
            raise ValueError("A saved artifact or source_files is required for test execution")

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
            artifact = await self._registry.get_accessible_artifact(artifact_id=revision.artifact_id, tenant_id=tenant_id)

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
            try:
                await self.execute_enqueued_run(run.id)
            except ArtifactConcurrencyLimitExceeded as exc:
                run = await self._runs.get_run(run_id=run.id)
                if run is not None:
                    await self._runs.mark_failed(
                        run,
                        error_payload={"message": str(exc), "code": "TENANT_ARTIFACT_CAPACITY_EXCEEDED"},
                        stdout_excerpt=None,
                        stderr_excerpt=None,
                        duration_ms=0,
                    )
                    await self._runs.add_events(
                        run,
                        [
                            {
                                "event_type": "dispatch_rejected",
                                "payload": {
                                    "event": "dispatch_rejected",
                                    "name": "dispatch_rejected",
                                    "data": {"message": str(exc), "queue_class": queue_class},
                                },
                            }
                        ],
                    )
                    await self._db.commit()
                raise
        else:
            await self.enqueue_run(run.id)

        return await self.wait_for_terminal_state(run.id, timeout_seconds=wait_timeout_seconds)

    async def enqueue_run(self, run_id: UUID) -> None:
        run = await self._runs.get_run(run_id=run_id)
        if run is None:
            return
        if artifact_run_task_eager():
            await self.execute_enqueued_run(run_id)
            return
        from app.workers.artifact_tasks import execute_artifact_run_task

        execute_artifact_run_task.apply_async(args=[str(run_id)], queue=run.queue_class)

    async def execute_enqueued_run(self, run_id: UUID) -> None:
        run = await self._runs.get_run(run_id=run_id)
        if run is None:
            return
        if run.status == ArtifactRunStatus.CANCELLED:
            await self._db.commit()
            return

        policy = await self._policies.assert_capacity(tenant_id=run.tenant_id, queue_class=run.queue_class)
        namespace = "staging" if run.queue_class == "artifact_test" else "production"
        deployment = await self._deployments.ensure_deployment(
            revision=run.revision,
            namespace=namespace,
            tenant_id=run.tenant_id,
        )

        run.runtime_metadata = {
            **dict(run.runtime_metadata or {}),
            "namespace": namespace,
            "worker_name": deployment.worker_name,
            "deployment_id": deployment.deployment_id,
            "version_id": deployment.version_id,
        }
        await self._runs.mark_running(run, worker_id=deployment.worker_name, sandbox_session_id=deployment.deployment_id)
        await self._runs.add_events(
            run,
            [
                {
                    "event_type": "deployment_resolved",
                    "payload": {
                        "event": "deployment_resolved",
                        "name": "deployment_resolved",
                        "data": {
                            "namespace": namespace,
                            "worker_name": deployment.worker_name,
                            "build_hash": deployment.build_hash,
                        },
                    },
                },
                {
                    "event_type": "dispatch_started",
                    "payload": {
                        "event": "dispatch_started",
                        "name": "dispatch_started",
                        "data": {
                            "queue_class": run.queue_class,
                            "namespace": namespace,
                            "cpu_ms": policy.cpu_ms,
                            "subrequests": policy.subrequests,
                        },
                    },
                },
            ],
        )
        await self._db.commit()

        request_payload = {
            "tenant_id": str(run.tenant_id),
            "run_id": str(run.id),
            "artifact_id": str(run.artifact_id) if run.artifact_id else None,
            "revision_id": str(run.revision_id),
            "queue_class": run.queue_class,
            "domain": self._enum_text(run.domain),
            "namespace": namespace,
            "worker_name": deployment.worker_name,
            "deployment_id": deployment.deployment_id,
            "version_id": deployment.version_id,
            "limits": {"cpu_ms": policy.cpu_ms, "subrequests": policy.subrequests},
            "inputs": run.input_payload,
            "config": dict(run.config_payload or {}),
            "context": dict(run.context_payload or {}),
            "secret_capabilities": list((run.context_payload or {}).get("secret_capabilities") or []),
            "allowed_hosts": list((run.context_payload or {}).get("allowed_hosts") or []),
        }
        if artifact_cloudflare_runtime_mode() == RUNTIME_MODE_STANDARD_WORKER_TEST:
            request_payload["source_files"] = list(run.revision.source_files or [])
            request_payload["entry_module_path"] = run.revision.entry_module_path
            request_payload["python_dependencies"] = list(run.revision.python_dependencies or [])

        client = CloudflareDispatchClient()
        try:
            response = await client.execute(request_payload)
        except Exception as exc:
            run = await self._runs.get_run(run_id=run_id)
            if run is None:
                return
            if isinstance(exc, CloudflareDispatchHTTPError):
                error_payload = exc.to_error_payload()
            else:
                error_payload = {"message": str(exc), "code": "CLOUDFLARE_DISPATCH_FAILED"}
            await self._runs.mark_failed(
                run,
                error_payload=error_payload,
                stdout_excerpt=None,
                stderr_excerpt=None,
                duration_ms=None,
            )
            await self._runs.add_events(
                run,
                [
                    {
                        "event_type": "dispatch_finished",
                        "payload": {
                            "event": "dispatch_finished",
                            "name": "dispatch_finished",
                            "data": {
                                "status": "failed",
                                "message": str(exc),
                                "error_payload": error_payload,
                            },
                        },
                    }
                ],
            )
            await self._db.commit()
            raise

        run = await self._runs.get_run(run_id=run_id)
        if run is None:
            return
        dispatch_request_id = getattr(response, "sandbox_session_id", None) or getattr(
            response, "dispatch_request_id", None
        )
        run.worker_id = getattr(response, "worker_id", None)
        run.sandbox_session_id = dispatch_request_id
        run.runtime_metadata = {**dict(run.runtime_metadata or {}), **dict(response.runtime_metadata or {})}
        if response.status == "completed" and not run.cancel_requested:
            await self._runs.mark_completed(
                run,
                result_payload=response.result if isinstance(response.result, dict) else {"result": response.result},
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
                    "event_type": "dispatch_finished",
                    "payload": {
                        "event": "dispatch_finished",
                        "name": "dispatch_finished",
                        "data": {
                            "status": response.status,
                            "worker_id": response.worker_id,
                            "dispatch_request_id": dispatch_request_id,
                            "duration_ms": response.duration_ms,
                        },
                    },
                }
            ]
            + list(response.events or []),
        )
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
            try:
                await CloudflareDispatchClient().cancel(run.sandbox_session_id)
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
    ):
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
