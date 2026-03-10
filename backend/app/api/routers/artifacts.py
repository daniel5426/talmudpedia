from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_principal, require_scopes, ensure_sensitive_action_approved
from app.api.schemas.artifacts import (
    ArtifactCreate,
    ArtifactPromoteRequest,
    ArtifactRunCreateResponse,
    ArtifactSchema,
    ArtifactScope as ArtifactScopeSchema,
    ArtifactTestRequest,
    ArtifactTestResponse,
    ArtifactType,
    ArtifactUpdate,
)
from app.db.postgres.models.artifact_runtime import Artifact as ArtifactModel
from app.db.postgres.models.artifact_runtime import ArtifactRunStatus, ArtifactStatus
from app.db.postgres.models.identity import OrgMembership, Tenant
from app.db.postgres.session import get_db
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService

router = APIRouter(prefix="/admin/artifacts", tags=["artifacts"])


async def get_artifact_context(
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if context.get("type") == "workload":
        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        try:
            tenant_uuid = UUID(str(tenant_id))
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid tenant context")
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_uuid))
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant, None, db

    current_user = context.get("user")
    if current_user is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not tenant_slug:
        if getattr(current_user, "role", None) != "admin":
            raise HTTPException(status_code=403, detail="Tenant context required")
        return None, current_user, db

    tenant = await db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    membership = await db.scalar(
        select(OrgMembership).where(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == current_user.id,
        )
    )
    if membership is None and getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this tenant")
    return tenant, current_user, db

def _scope_to_schema_value(raw: Any) -> ArtifactScopeSchema:
    value = getattr(raw, "value", raw)
    try:
        return ArtifactScopeSchema(str(value))
    except Exception:
        return ArtifactScopeSchema.RAG


def _model_dump(model: Any, **kwargs):
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def _repo_spec_to_schema(spec, *, path: Optional[str], code: Optional[str]) -> ArtifactSchema:
    scope = _scope_to_schema_value(getattr(spec, "scope", "rag"))
    config_schema = []
    for cfg in (getattr(spec, "required_config", []) + getattr(spec, "optional_config", [])):
        config_schema.append(
            {
                "name": cfg.name,
                "type": cfg.field_type.value if hasattr(cfg.field_type, "value") else str(cfg.field_type),
                "required": cfg.required,
                "default": cfg.default,
                "description": cfg.description,
                "options": cfg.options,
            }
        )
    artifact_type = ArtifactType.BUILTIN if str(getattr(spec, "operator_id", "")).startswith("builtin/") else ArtifactType.PROMOTED
    return ArtifactSchema(
        id=str(spec.operator_id),
        name=str(spec.operator_id).split("/")[-1],
        display_name=spec.display_name,
        description=spec.description,
        category=spec.category.value if hasattr(spec.category, "value") else str(spec.category),
        input_type=spec.input_type.value if hasattr(spec.input_type, "value") else str(spec.input_type),
        output_type=spec.output_type.value if hasattr(spec.output_type, "value") else str(spec.output_type),
        version=str(spec.version),
        type=artifact_type,
        scope=scope,
        author=getattr(spec, "author", None),
        tags=list(getattr(spec, "tags", []) or []),
        config_schema=config_schema,
        updated_at=datetime.utcnow(),
        python_code=code,
        dependencies=[],
        path=path,
        reads=list(getattr(spec, "reads", []) or []),
        writes=list(getattr(spec, "writes", []) or []),
        inputs=list(getattr(spec, "inputs", []) or []),
        outputs=list(getattr(spec, "outputs", []) or []),
    )


def _tenant_artifact_to_schema(artifact: ArtifactModel, *, include_code: bool = False) -> ArtifactSchema:
    active_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if active_revision is None:
        raise ValueError("Artifact is missing a current revision")
    artifact_type = ArtifactType.DRAFT
    if artifact.latest_published_revision_id and active_revision.is_published:
        artifact_type = ArtifactType.PROMOTED
    return ArtifactSchema(
        id=str(artifact.id),
        name=artifact.slug,
        display_name=artifact.display_name,
        description=artifact.description,
        category=artifact.category,
        input_type=artifact.input_type,
        output_type=artifact.output_type,
        version=str(active_revision.version_label or "draft"),
        type=artifact_type,
        scope=_scope_to_schema_value(artifact.scope),
        author=None,
        tags=["published"] if artifact.status == ArtifactStatus.PUBLISHED else ["draft"],
        config_schema=list(active_revision.config_schema or []),
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        python_code=active_revision.source_code if include_code else None,
        dependencies=list(active_revision.python_dependencies or []),
        reads=list(active_revision.reads or []),
        writes=list(active_revision.writes or []),
        inputs=list(active_revision.inputs or []),
        outputs=list(active_revision.outputs or []),
    )


def _parse_artifact_uuid(raw: str) -> UUID | None:
    try:
        return UUID(str(raw))
    except Exception:
        return None


@router.get("", response_model=List[ArtifactSchema])
async def list_artifacts(
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    registry = ArtifactRegistryService(db)
    results: list[ArtifactSchema] = []

    for artifact_id, spec in registry.list_repo_artifacts().items():
        path = registry.get_repo_artifact_path(artifact_id)
        results.append(_repo_spec_to_schema(spec, path=str(path) if path else None, code=None))

    if tenant is not None:
        tenant_artifacts = await registry.list_tenant_artifacts(tenant_id=tenant.id)
    else:
        tenant_artifacts = list(
            (
                await db.execute(
                    select(ArtifactModel).options(
                        selectinload(ArtifactModel.latest_draft_revision),
                        selectinload(ArtifactModel.latest_published_revision),
                    )
                )
            ).scalars().all()
        )
    for artifact in tenant_artifacts:
        results.append(_tenant_artifact_to_schema(artifact))
    return results

@router.get("/{artifact_id:path}", response_model=ArtifactSchema)
async def get_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    tenant_uuid = tenant.id if tenant is not None else None
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    registry = ArtifactRegistryService(db)

    if artifact_uuid is not None:
        artifact = await registry.get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant_uuid) if tenant_uuid else await db.scalar(
            select(ArtifactModel)
            .where(ArtifactModel.id == artifact_uuid)
            .options(
                selectinload(ArtifactModel.latest_draft_revision),
                selectinload(ArtifactModel.latest_published_revision),
            )
        )
        if artifact is not None:
            return _tenant_artifact_to_schema(artifact, include_code=True)

    spec = registry.get_repo_artifact(artifact_id)
    if spec is not None:
        path = registry.get_repo_artifact_path(artifact_id)
        code = registry.get_repo_artifact_code(artifact_id)
        return _repo_spec_to_schema(spec, path=str(path) if path else None, code=code)

    raise HTTPException(status_code=404, detail="Artifact not found")


@router.post("", response_model=ArtifactSchema)
async def create_artifact_draft(
    request: ArtifactCreate,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    existing = await db.scalar(select(ArtifactModel).where(ArtifactModel.tenant_id == tenant.id, ArtifactModel.slug == request.name))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Artifact with this slug already exists")

    service = ArtifactRevisionService(db)
    artifact = await service.create_artifact(
        tenant_id=tenant.id,
        created_by=user.id if user else None,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        category=request.category,
        scope=request.scope.value if request.scope else "rag",
        input_type=request.input_type,
        output_type=request.output_type,
        source_code=request.python_code,
        python_dependencies=list(request.dependencies or []),
        config_schema=list(request.config_schema or []),
        inputs=list(request.inputs or []),
        outputs=list(request.outputs or []),
        reads=list(request.reads or []),
        writes=list(request.writes or []),
    )
    await db.commit()
    await db.refresh(artifact)
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)
    return _tenant_artifact_to_schema(artifact, include_code=True)


@router.put("/{artifact_id:path}", response_model=ArtifactSchema)
async def update_artifact(
    artifact_id: str,
    update_data: ArtifactUpdate,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=403, detail="Repo-backed artifacts are read-only in runtime v1")

    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    current_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if current_revision is None:
        raise HTTPException(status_code=409, detail="Artifact is missing a current revision")
    payload = _model_dump(update_data, exclude_unset=True)
    revision_service = ArtifactRevisionService(db)
    await revision_service.update_artifact(
        artifact,
        updated_by=user.id if user else None,
        display_name=payload.get("display_name", artifact.display_name),
        description=payload.get("description", artifact.description),
        category=payload.get("category", artifact.category),
        scope=(payload.get("scope").value if hasattr(payload.get("scope"), "value") else payload.get("scope", getattr(artifact.scope, "value", artifact.scope))),
        input_type=payload.get("input_type", artifact.input_type),
        output_type=payload.get("output_type", artifact.output_type),
        source_code=payload.get("python_code", current_revision.source_code),
        python_dependencies=list(payload.get("dependencies", current_revision.python_dependencies or [])),
        config_schema=list(payload.get("config_schema", current_revision.config_schema or [])),
        inputs=list(payload.get("inputs", current_revision.inputs or [])),
        outputs=list(payload.get("outputs", current_revision.outputs or [])),
        reads=list(payload.get("reads", current_revision.reads or [])),
        writes=list(payload.get("writes", current_revision.writes or [])),
    )
    await db.commit()
    refreshed = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)
    return _tenant_artifact_to_schema(refreshed, include_code=True)


@router.delete("/{artifact_id:path}")
async def delete_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=403, detail="Repo-backed artifacts are read-only in runtime v1")
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tenant.id,
        subject_type="artifact",
        subject_id=str(artifact.id),
        action_scope="artifacts.delete",
        db=db,
    )
    await db.delete(artifact)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{artifact_id:path}/promote")
async def promote_artifact(
    artifact_id: str,
    request: ArtifactPromoteRequest,
    tenant_slug: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    _ = request
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=403, detail="Repo-backed artifacts are read-only in runtime v1")
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tenant.id,
        subject_type="artifact",
        subject_id=str(artifact.id),
        action_scope="artifacts.promote",
        db=db,
    )

    revision = await ArtifactRevisionService(db).publish_latest_draft(artifact)
    await db.commit()
    return {
        "status": "published",
        "artifact_id": str(artifact.id),
        "revision_id": str(revision.id),
        "version": revision.version_label,
    }


@router.post("/test-runs", response_model=ArtifactRunCreateResponse)
async def create_unsaved_test_run(
    request: ArtifactTestRequest,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact_uuid = _parse_artifact_uuid(request.artifact_id) if request.artifact_id else None
    service = ArtifactExecutionService(db)
    run = await service.start_test_run(
        tenant_id=tenant.id,
        created_by=user.id if user else None,
        artifact_id=artifact_uuid,
        python_code=request.python_code,
        input_data=request.input_data,
        config=request.config or {},
        dependencies=list(request.dependencies or []),
        input_type=request.input_type,
        output_type=request.output_type,
    )
    return ArtifactRunCreateResponse(run_id=str(run.id), status=str(getattr(run.status, "value", run.status)))


@router.post("/{artifact_id:path}/test-runs", response_model=ArtifactRunCreateResponse)
async def create_saved_artifact_test_run(
    artifact_id: str,
    request: ArtifactTestRequest,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    request.artifact_id = artifact_id
    return await create_unsaved_test_run(request, tenant_slug=tenant_slug, artifact_ctx=artifact_ctx)


@router.post("/test", response_model=ArtifactTestResponse)
async def test_artifact(
    request: ArtifactTestRequest,
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    service = ArtifactExecutionService(db)
    run = await service.start_test_run(
        tenant_id=tenant.id,
        created_by=user.id if user else None,
        artifact_id=_parse_artifact_uuid(request.artifact_id) if request.artifact_id else None,
        python_code=request.python_code,
        input_data=request.input_data,
        config=request.config or {},
        dependencies=list(request.dependencies or []),
        input_type=request.input_type,
        output_type=request.output_type,
    )
    terminal = await service.wait_for_terminal_state(run.id, timeout_seconds=30.0)
    if terminal is None:
        return ArtifactTestResponse(
            success=False,
            data=None,
            error_message="Timed out waiting for test run",
            execution_time_ms=0.0,
            run_id=str(run.id),
        )
    if terminal.status == ArtifactRunStatus.COMPLETED:
        return ArtifactTestResponse(
            success=True,
            data=terminal.result_payload,
            error_message=None,
            execution_time_ms=float(terminal.duration_ms or 0),
            run_id=str(terminal.id),
            stdout_excerpt=terminal.stdout_excerpt,
            stderr_excerpt=terminal.stderr_excerpt,
        )
    if terminal.status == ArtifactRunStatus.CANCELLED:
        return ArtifactTestResponse(
            success=False,
            data=None,
            error_message="Test run cancelled",
            execution_time_ms=float(terminal.duration_ms or 0),
            run_id=str(terminal.id),
            error_payload=terminal.error_payload,
            stdout_excerpt=terminal.stdout_excerpt,
            stderr_excerpt=terminal.stderr_excerpt,
        )
    message = (terminal.error_payload or {}).get("message") if isinstance(terminal.error_payload, dict) else None
    return ArtifactTestResponse(
        success=False,
        data=None,
        error_message=message or "Artifact test run failed",
        execution_time_ms=float(terminal.duration_ms or 0),
        run_id=str(terminal.id),
        error_payload=terminal.error_payload,
        stdout_excerpt=terminal.stdout_excerpt,
        stderr_excerpt=terminal.stderr_excerpt,
    )
