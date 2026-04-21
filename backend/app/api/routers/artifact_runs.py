from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_scopes
from app.api.schemas.artifacts import ArtifactRunEventSchema, ArtifactRunSchema, ArtifactRuntimeQueueStatusSchema
from app.db.postgres.models.artifact_runtime import ArtifactRunStatus
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.policy_service import ArtifactRuntimePolicyService
from app.services.artifact_runtime.run_service import ArtifactRunService

from .artifacts import get_artifact_context


router = APIRouter(prefix="/admin/artifact-runs", tags=["artifacts"])


def _serialize_run(run) -> ArtifactRunSchema:
    return ArtifactRunSchema(
        id=str(run.id),
        artifact_id=str(run.artifact_id) if run.artifact_id else None,
        revision_id=str(run.revision_id),
        domain=run.domain.value if hasattr(run.domain, "value") else str(run.domain),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        queue_class=run.queue_class,
        result_payload=run.result_payload,
        error_payload=run.error_payload,
        stdout_excerpt=run.stdout_excerpt,
        stderr_excerpt=run.stderr_excerpt,
        duration_ms=run.duration_ms,
        runtime_metadata=dict(run.runtime_metadata or {}),
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/runtime-status", response_model=ArtifactRuntimeQueueStatusSchema)
async def get_artifact_runtime_status(
    organization_id: Optional[str] = None,
    queue_class: str = "artifact_test",
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    if organization is None:
        raise HTTPException(status_code=400, detail="Organization context required")
    status = await ArtifactRuntimePolicyService(db).get_queue_status(
        organization_id=organization.id,
        queue_class=queue_class,
    )
    return ArtifactRuntimeQueueStatusSchema(
        queue_class=status.queue_class,
        active_count=status.active_count,
        concurrency_limit=status.concurrency_limit,
    )


@router.get("/{run_id}", response_model=ArtifactRunSchema)
async def get_artifact_run(
    run_id: UUID,
    organization_id: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    run = await ArtifactRunService(db).get_run(run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Artifact run not found")
    if organization is not None and str(run.organization_id) != str(organization.id):
        raise HTTPException(status_code=403, detail="Organization mismatch")
    return _serialize_run(run)


@router.get("/{run_id}/events")
async def get_artifact_run_events(
    run_id: UUID,
    organization_id: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    run_service = ArtifactRunService(db)
    run = await run_service.get_run(run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Artifact run not found")
    if organization is not None and str(run.organization_id) != str(organization.id):
        raise HTTPException(status_code=403, detail="Organization mismatch")
    events = await run_service.list_events(run_id=run_id)
    return {
        "run_id": str(run_id),
        "event_count": len(events),
        "events": [
            ArtifactRunEventSchema(
                id=str(event.id),
                sequence=event.sequence,
                timestamp=event.timestamp,
                event_type=event.event_type,
                payload=dict(event.payload or {}),
            ).model_dump() if hasattr(ArtifactRunEventSchema, "model_dump") else ArtifactRunEventSchema(
                id=str(event.id),
                sequence=event.sequence,
                timestamp=event.timestamp,
                event_type=event.event_type,
                payload=dict(event.payload or {}),
            ).dict()
            for event in events
        ],
    }


@router.post("/{run_id}/cancel")
async def cancel_artifact_run(
    run_id: UUID,
    organization_id: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    if organization is None:
        raise HTTPException(status_code=400, detail="Organization context required")
    service = ArtifactExecutionService(db)
    try:
        run = await service.cancel_run(run_id=run_id, organization_id=organization.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    status_value = run.status.value if hasattr(run.status, "value") else str(run.status)
    return {"run_id": str(run.id), "status": status_value}
