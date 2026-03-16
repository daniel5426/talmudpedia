from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ensure_sensitive_action_approved, get_current_principal, require_scopes
from app.api.schemas.artifacts import (
    ArtifactConvertKindRequest,
    ArtifactCreate,
    ArtifactPublishResponse,
    ArtifactRunCreateResponse,
    ArtifactSchema,
    ArtifactTestRequest,
    ArtifactType,
    ArtifactUpdate,
    ArtifactVersionListItem,
    ArtifactVersionSchema,
    ArtifactWorkingDraftResponse,
    ArtifactWorkingDraftUpdateRequest,
)
from app.services.artifact_coding_agent_tools import _initial_snapshot_for_kind, _serialize_form_state
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.db.postgres.models.artifact_runtime import Artifact as ArtifactModel
from app.db.postgres.models.artifact_runtime import ArtifactKind, ArtifactOwnerType, ArtifactRevision as ArtifactRevisionModel, ArtifactRunStatus, ArtifactStatus
from app.db.postgres.models.identity import OrgMembership, Tenant
from app.db.postgres.session import get_db
from app.services.artifact_runtime.deployment_service import ArtifactDeploymentService
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.tool_binding_service import ToolBindingService

router = APIRouter(prefix="/admin/artifacts", tags=["artifacts"])


async def _resolve_tenant_from_artifact_if_missing(
    *,
    tenant,
    user,
    db: AsyncSession,
    artifact_id: str | None,
):
    if tenant is not None or not artifact_id:
        return tenant
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        return tenant
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(artifact_id=artifact_uuid, tenant_id=None)
    if artifact is None or artifact.tenant_id is None:
        return tenant
    resolved_tenant = await db.scalar(select(Tenant).where(Tenant.id == artifact.tenant_id))
    if resolved_tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if user is not None and getattr(user, "role", None) != "admin":
        membership = await db.scalar(
            select(OrgMembership).where(
                OrgMembership.tenant_id == resolved_tenant.id,
                OrgMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="Not a member of this tenant")
    return resolved_tenant


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

    principal_tenant_id = context.get("tenant_id")
    if principal_tenant_id:
        try:
            principal_tenant_uuid = UUID(str(principal_tenant_id))
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid tenant context")
        principal_tenant = await db.scalar(select(Tenant).where(Tenant.id == principal_tenant_uuid))
        if principal_tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        if tenant_slug and principal_tenant.slug != tenant_slug:
            membership = await db.scalar(
                select(OrgMembership).where(
                    OrgMembership.tenant_id == principal_tenant.id,
                    OrgMembership.user_id == current_user.id,
                )
            )
            if membership is None and getattr(current_user, "role", None) != "admin":
                raise HTTPException(status_code=403, detail="Not a member of this tenant")
        if not tenant_slug or principal_tenant.slug == tenant_slug:
            return principal_tenant, current_user, db

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


def _model_dump(model: Any, **kwargs):
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def _parse_artifact_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except Exception:
        return None


def _artifact_to_schema(artifact: ArtifactModel, *, include_code: bool = False) -> ArtifactSchema:
    active_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if active_revision is None:
        raise ValueError("Artifact is missing a current revision")
    artifact_type = ArtifactType.PUBLISHED if (
        artifact.status == ArtifactStatus.PUBLISHED and active_revision.is_published
    ) else ArtifactType.DRAFT
    runtime = {
        "source_files": list(active_revision.source_files or []) if include_code else [],
        "entry_module_path": active_revision.entry_module_path,
        "python_dependencies": list(active_revision.python_dependencies or []),
        "runtime_target": str(active_revision.runtime_target or "cloudflare_workers"),
    }
    return ArtifactSchema(
        id=str(artifact.id),
        display_name=artifact.display_name,
        description=artifact.description,
        kind=getattr(artifact.kind, "value", artifact.kind),
        owner_type=getattr(artifact.owner_type, "value", artifact.owner_type),
        type=artifact_type,
        version=str(active_revision.version_label or "draft"),
        config_schema=dict(active_revision.config_schema or {}),
        runtime=runtime,
        capabilities=dict(active_revision.capabilities or {}),
        agent_contract=dict(active_revision.agent_contract or {}) if active_revision.agent_contract is not None else None,
        rag_contract=dict(active_revision.rag_contract or {}) if active_revision.rag_contract is not None else None,
        tool_contract=dict(active_revision.tool_contract or {}) if active_revision.tool_contract is not None else None,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        system_key=artifact.system_key,
        tags=["published"] if artifact.status == ArtifactStatus.PUBLISHED else ["draft"],
    )


def _artifact_revision_to_version_schema(
    artifact: ArtifactModel,
    revision: ArtifactRevisionModel,
    *,
    include_code: bool = False,
) -> ArtifactVersionSchema:
    runtime = {
        "source_files": list(revision.source_files or []) if include_code else [],
        "entry_module_path": revision.entry_module_path,
        "python_dependencies": list(revision.python_dependencies or []),
        "runtime_target": str(revision.runtime_target or "cloudflare_workers"),
    }
    return ArtifactVersionSchema(
        id=str(revision.id),
        artifact_id=str(artifact.id),
        revision_number=int(revision.revision_number or 0),
        version_label=str(revision.version_label or f"v{int(revision.revision_number or 0)}"),
        is_published=bool(revision.is_published),
        is_current_draft=artifact.latest_draft_revision_id == revision.id,
        is_current_published=artifact.latest_published_revision_id == revision.id,
        source_file_count=len(list(revision.source_files or [])),
        created_at=revision.created_at,
        created_by=None,
        display_name=revision.display_name,
        description=revision.description,
        kind=getattr(revision.kind, "value", revision.kind),
        config_schema=dict(revision.config_schema or {}),
        runtime=runtime,
        capabilities=dict(revision.capabilities or {}),
        agent_contract=dict(revision.agent_contract or {}) if revision.agent_contract is not None else None,
        rag_contract=dict(revision.rag_contract or {}) if revision.rag_contract is not None else None,
        tool_contract=dict(revision.tool_contract or {}) if revision.tool_contract is not None else None,
    )


@router.get("", response_model=List[ArtifactSchema])
async def list_artifacts(
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    registry = ArtifactRegistryService(db)
    artifacts = await registry.list_accessible_artifacts(tenant_id=tenant.id if tenant is not None else None)
    return [_artifact_to_schema(artifact) for artifact in artifacts]


@router.get("/{artifact_id}", response_model=ArtifactSchema)
async def get_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        tenant_id=tenant.id if tenant is not None else None,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _artifact_to_schema(artifact, include_code=True)


def _artifact_form_snapshot(artifact: ArtifactModel) -> dict[str, Any]:
    active_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if active_revision is None:
        return _initial_snapshot_for_kind(getattr(artifact.kind, "value", artifact.kind))
    return _serialize_form_state(
        {
            "display_name": artifact.display_name,
            "description": artifact.description or "",
            "kind": getattr(artifact.kind, "value", artifact.kind),
            "source_files": list(active_revision.source_files or []),
            "entry_module_path": active_revision.entry_module_path,
            "python_dependencies": ", ".join(list(active_revision.python_dependencies or [])),
            "runtime_target": active_revision.runtime_target,
            "capabilities": dict(active_revision.capabilities or {}),
            "config_schema": dict(active_revision.config_schema or {}),
            "agent_contract": dict(active_revision.agent_contract or {}) if active_revision.agent_contract is not None else None,
            "rag_contract": dict(active_revision.rag_contract or {}) if active_revision.rag_contract is not None else None,
            "tool_contract": dict(active_revision.tool_contract or {}) if active_revision.tool_contract is not None else None,
        }
    )


@router.get("/{artifact_id}/versions", response_model=List[ArtifactVersionListItem])
async def list_artifact_versions(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        tenant_id=tenant.id if tenant is not None else None,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    result = await db.execute(
        select(ArtifactRevisionModel)
        .where(ArtifactRevisionModel.artifact_id == artifact.id)
        .order_by(desc(ArtifactRevisionModel.revision_number), desc(ArtifactRevisionModel.created_at))
    )
    versions = []
    for revision in result.scalars().all():
        version = _artifact_revision_to_version_schema(artifact, revision, include_code=False)
        versions.append(ArtifactVersionListItem(**version.model_dump()))
    return versions


@router.get("/{artifact_id}/versions/{revision_id}", response_model=ArtifactVersionSchema)
async def get_artifact_version(
    artifact_id: str,
    revision_id: str,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    revision_uuid = _parse_artifact_uuid(revision_id)
    if artifact_uuid is None or revision_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        tenant_id=tenant.id if tenant is not None else None,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    revision = await db.get(ArtifactRevisionModel, revision_uuid)
    if revision is None or revision.artifact_id != artifact.id:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    return _artifact_revision_to_version_schema(artifact, revision, include_code=True)


@router.get("/{artifact_id}/working-draft", response_model=ArtifactWorkingDraftResponse)
async def get_artifact_working_draft(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        tenant_id=tenant.id if tenant is not None else None,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    initial_snapshot = _artifact_form_snapshot(artifact)
    shared = await ArtifactCodingSharedDraftService(db).get_or_create_for_scope(
        tenant_id=tenant.id if tenant is not None else artifact.tenant_id,
        artifact_id=artifact.id,
        draft_key=None,
        initial_snapshot=initial_snapshot,
    )
    return ArtifactWorkingDraftResponse(
        artifact_id=str(artifact.id),
        draft_snapshot=dict(shared.working_draft_snapshot or initial_snapshot),
        updated_at=shared.updated_at,
    )


@router.put("/{artifact_id}/working-draft", response_model=ArtifactWorkingDraftResponse)
async def update_artifact_working_draft(
    artifact_id: str,
    request: ArtifactWorkingDraftUpdateRequest,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    shared_service = ArtifactCodingSharedDraftService(db)
    shared = await shared_service.get_or_create_for_scope(
        tenant_id=tenant.id,
        artifact_id=artifact.id,
        draft_key=str(request.draft_key or "").strip() or None,
        initial_snapshot=_artifact_form_snapshot(artifact),
    )
    normalized_snapshot = _serialize_form_state(dict(request.draft_snapshot or {}))
    await shared_service.update_snapshot(
        shared_draft=shared,
        draft_snapshot=normalized_snapshot,
        artifact_id=artifact.id,
        draft_key=str(request.draft_key or "").strip() or None,
    )
    await db.commit()
    return ArtifactWorkingDraftResponse(
        artifact_id=str(artifact.id),
        draft_key=str(request.draft_key or "").strip() or None,
        draft_snapshot=dict(shared.working_draft_snapshot or normalized_snapshot),
        updated_at=shared.updated_at,
    )


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
    artifact = await ArtifactRevisionService(db).create_artifact(
        tenant_id=tenant.id,
        created_by=user.id if user else None,
        display_name=request.display_name,
        description=request.description,
        kind=request.kind.value,
        owner_type=ArtifactOwnerType.TENANT.value,
        source_files=[_model_dump(item) for item in request.runtime.source_files],
        entry_module_path=request.runtime.entry_module_path,
        python_dependencies=list(request.runtime.python_dependencies or []),
        runtime_target=request.runtime.runtime_target,
        capabilities=_model_dump(request.capabilities),
        config_schema=dict(request.config_schema or {}),
        agent_contract=_model_dump(request.agent_contract) if request.agent_contract is not None else None,
        rag_contract=_model_dump(request.rag_contract) if request.rag_contract is not None else None,
        tool_contract=_model_dump(request.tool_contract) if request.tool_contract is not None else None,
    )
    try:
        await ToolBindingService(db).sync_artifact_tool_binding(artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    refreshed = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)
    return _artifact_to_schema(refreshed, include_code=True)


@router.put("/{artifact_id}", response_model=ArtifactSchema)
async def update_artifact(
    artifact_id: str,
    update_data: ArtifactUpdate,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    current_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if current_revision is None:
        raise HTTPException(status_code=409, detail="Artifact is missing a current revision")
    payload = _model_dump(update_data, exclude_unset=True)
    runtime = payload.get("runtime") or {}
    await ArtifactRevisionService(db).update_artifact(
        artifact,
        updated_by=user.id if user else None,
        display_name=payload.get("display_name", artifact.display_name),
        description=payload.get("description", artifact.description),
        source_files=runtime.get("source_files", current_revision.source_files),
        entry_module_path=runtime.get("entry_module_path", current_revision.entry_module_path),
        python_dependencies=list(runtime.get("python_dependencies", current_revision.python_dependencies or [])),
        runtime_target=runtime.get("runtime_target", current_revision.runtime_target),
        capabilities=dict(payload.get("capabilities", current_revision.capabilities or {})),
        config_schema=dict(payload.get("config_schema", current_revision.config_schema or {})),
        agent_contract=payload.get("agent_contract", dict(current_revision.agent_contract or {}) if current_revision.agent_contract is not None else None),
        rag_contract=payload.get("rag_contract", dict(current_revision.rag_contract or {}) if current_revision.rag_contract is not None else None),
        tool_contract=payload.get("tool_contract", dict(current_revision.tool_contract or {}) if current_revision.tool_contract is not None else None),
    )
    try:
        await ToolBindingService(db).sync_artifact_tool_binding(artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    refreshed = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)
    return _artifact_to_schema(refreshed, include_code=True)


@router.post("/{artifact_id}/publish", response_model=ArtifactPublishResponse)
async def publish_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tenant.id,
        subject_type="artifact",
        subject_id=str(artifact.id),
        action_scope="artifacts.publish",
        db=db,
    )
    revision = await ArtifactRevisionService(db).publish_latest_draft(artifact)
    await ArtifactDeploymentService(db).ensure_deployment(
        revision=revision,
        namespace="production",
        tenant_id=tenant.id,
    )
    try:
        await ToolBindingService(db).publish_artifact_tool_binding(
            artifact=artifact,
            revision=revision,
            created_by=getattr(_user, "id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return ArtifactPublishResponse(
        artifact_id=str(artifact.id),
        revision_id=str(revision.id),
        version=revision.version_label,
    )


@router.post("/{artifact_id}/convert-kind", response_model=ArtifactSchema)
async def convert_artifact_kind(
    artifact_id: str,
    request: ArtifactConvertKindRequest,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=tenant.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if artifact.latest_published_revision_id is not None:
        raise HTTPException(status_code=409, detail="Published artifacts cannot change kind in place")
    binding_service = ToolBindingService(db)
    if artifact.kind == ArtifactKind.TOOL_IMPL and request.kind.value != ArtifactKind.TOOL_IMPL.value:
        await binding_service.delete_artifact_tool_binding(artifact.id)
    await ArtifactRevisionService(db).convert_kind(
        artifact,
        updated_by=user.id if user else None,
        kind=request.kind.value,
        agent_contract=_model_dump(request.agent_contract) if request.agent_contract is not None else None,
        rag_contract=_model_dump(request.rag_contract) if request.rag_contract is not None else None,
        tool_contract=_model_dump(request.tool_contract) if request.tool_contract is not None else None,
    )
    try:
        await binding_service.sync_artifact_tool_binding(artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    refreshed = await ArtifactRegistryService(db).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)
    return _artifact_to_schema(refreshed, include_code=True)


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, _user, db = artifact_ctx
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
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
    await ToolBindingService(db).delete_artifact_tool_binding(artifact.id)
    await db.delete(artifact)
    await db.commit()
    return {"status": "deleted"}


@router.post("/test-runs", response_model=ArtifactRunCreateResponse)
async def create_unsaved_test_run(
    request: ArtifactTestRequest,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    tenant, user, db = artifact_ctx
    tenant = await _resolve_tenant_from_artifact_if_missing(
        tenant=tenant,
        user=user,
        db=db,
        artifact_id=request.artifact_id,
    )
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant context required")
    run = await ArtifactExecutionService(db).start_test_run(
        tenant_id=tenant.id,
        created_by=user.id if user else None,
        artifact_id=_parse_artifact_uuid(request.artifact_id),
        source_files=[_model_dump(item) for item in request.source_files],
        entry_module_path=request.entry_module_path,
        input_data=request.input_data,
        config=request.config or {},
        dependencies=list(request.dependencies or []),
        kind=getattr(request.kind, "value", request.kind) if getattr(request, "kind", None) else None,
        runtime_target=getattr(request, "runtime_target", None),
        capabilities=dict(getattr(request, "capabilities", None) or {}),
        config_schema=dict(getattr(request, "config_schema", None) or {}),
        agent_contract=_model_dump(request.agent_contract) if getattr(request, "agent_contract", None) is not None else None,
        rag_contract=_model_dump(request.rag_contract) if getattr(request, "rag_contract", None) is not None else None,
        tool_contract=_model_dump(request.tool_contract) if getattr(request, "tool_contract", None) is not None else None,
    )
    return ArtifactRunCreateResponse(run_id=str(run.id), status=str(getattr(run.status, "value", run.status)))


@router.post("/{artifact_id}/test-runs", response_model=ArtifactRunCreateResponse)
async def create_saved_artifact_test_run(
    artifact_id: str,
    request: ArtifactTestRequest,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    request.artifact_id = artifact_id
    return await create_unsaved_test_run(request, tenant_slug=tenant_slug, artifact_ctx=artifact_ctx)
