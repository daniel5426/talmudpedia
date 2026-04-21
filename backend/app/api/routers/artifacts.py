from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ensure_sensitive_action_approved, get_current_principal, require_scopes
from app.api.schemas.artifacts import (
    ArtifactConvertKindRequest,
    ArtifactCreate,
    ArtifactImportResponse,
    ArtifactTransferFile,
    ArtifactTransferPayload,
    ArtifactDependencyAnalysisRequest,
    ArtifactDependencyAnalysisResponse,
    ArtifactPublishResponse,
    ArtifactRunCreateResponse,
    ArtifactSourceValidationRequest,
    ArtifactSourceValidationResponse,
    ArtifactSchema,
    ArtifactTestRequest,
    ArtifactType,
    ArtifactUpdate,
    ArtifactVersionListItem,
    ArtifactVersionSchema,
    ArtifactWorkingDraftResponse,
    ArtifactWorkingDraftUpdateRequest,
    PythonPackageVerificationRequest,
    PythonPackageVerificationResponse,
)
from app.services.artifact_coding_agent_tools import _initial_snapshot_for_kind, _serialize_form_state
from app.services.artifact_coding_chat_history_service import ArtifactCodingChatHistoryService
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.db.postgres.models.artifact_runtime import Artifact as ArtifactModel
from app.db.postgres.models.artifact_runtime import ArtifactKind, ArtifactOwnerType, ArtifactRevision as ArtifactRevisionModel, ArtifactRunStatus, ArtifactStatus
from app.db.postgres.models.identity import OrgMembership, Organization
from app.db.postgres.session import get_db
from app.services.artifact_runtime.deployment_service import ArtifactDeploymentService
from app.services.artifact_runtime.dependency_registry import analyze_artifact_dependencies, verify_python_package_exists
from app.services.artifact_runtime.entrypoint_contract import ArtifactEntrypointContractError
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.policy_service import ArtifactConcurrencyLimitExceeded
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.artifact_runtime.runtime_secret_service import validate_source_files_for_editor
from app.services.artifact_runtime.tool_contracts import ToolContractValidationError, parse_tool_contract_json
from app.services.control_plane.artifact_admin_service import (
    ArtifactAdminService,
    ArtifactRuntimeInput as ControlPlaneArtifactRuntimeInput,
    CreateArtifactInput as ControlPlaneCreateArtifactInput,
    UpdateArtifactInput as ControlPlaneUpdateArtifactInput,
)
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError
from app.services.tool_binding_service import ToolBindingService

router = APIRouter(prefix="/admin/artifacts", tags=["artifacts"])
_DUPLICATE_NAME_SUFFIX_RE = re.compile(r"^(?P<base>.*?)(?: \((?P<index>\d+)\))?$")


def _artifact_control_plane_context(*, organization: Organization | None, user: Any | None, context: Dict[str, Any] | None = None) -> ControlPlaneContext:
    if organization is None:
        raise HTTPException(status_code=400, detail="Organization context required")
    principal = context or {}
    return ControlPlaneContext(
        organization_id=organization.id,
        project_id=UUID(str(principal["project_id"])) if principal.get("project_id") else None,
        user=user,
        user_id=getattr(user, "id", None),
        auth_token=principal.get("auth_token"),
        scopes=tuple(principal.get("scopes") or ()),
        is_service=bool(principal.get("type") == "workload"),
    )


def _principal_project_id(principal: Dict[str, Any] | None) -> UUID | None:
    raw_project_id = (principal or {}).get("project_id")
    try:
        return UUID(str(raw_project_id)) if raw_project_id else None
    except Exception:
        return None


async def _resolve_organization_from_artifact_if_missing(
    *,
    organization,
    user,
    db: AsyncSession,
    artifact_id: str | None,
):
    if organization is not None or not artifact_id:
        return organization
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        return organization
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(artifact_id=artifact_uuid, organization_id=None)
    if artifact is None or artifact.organization_id is None:
        return organization
    resolved_tenant = await db.scalar(select(Organization).where(Organization.id == artifact.organization_id))
    if resolved_tenant is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if user is not None and getattr(user, "role", None) != "admin":
        membership = await db.scalar(
            select(OrgMembership).where(
                OrgMembership.organization_id == resolved_tenant.id,
                OrgMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
    return resolved_tenant


async def get_artifact_context(
    organization_id: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if context.get("type") == "workload":
        organization_id= context.get("organization_id")
        if not organization_id:
            raise HTTPException(status_code=403, detail="Organization context required")
        try:
            organization_uuid = UUID(str(organization_id))
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid organization context")
        organization = await db.scalar(select(Organization).where(Organization.id == organization_uuid))
        if organization is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return organization, None, db

    current_user = context.get("user")
    if current_user is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    principal_organization_id = context.get("organization_id")
    if principal_organization_id:
        try:
            principal_organization_uuid = UUID(str(principal_organization_id))
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid organization context")
        principal_tenant = await db.scalar(select(Organization).where(Organization.id == principal_organization_uuid))
        if principal_tenant is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        if organization_id and str(principal_tenant.id) != organization_id:
            membership = await db.scalar(
                select(OrgMembership).where(
                    OrgMembership.organization_id == principal_tenant.id,
                    OrgMembership.user_id == current_user.id,
                )
            )
            if membership is None and getattr(current_user, "role", None) != "admin":
                raise HTTPException(status_code=403, detail="Not a member of this organization")
        if not organization_id or str(principal_tenant.id) == organization_id:
            return principal_tenant, current_user, db

    if not organization_id:
        if getattr(current_user, "role", None) != "admin":
            raise HTTPException(status_code=403, detail="Organization context required")
        return None, current_user, db

    organization = await db.scalar(select(Organization).where(Organization.id == UUID(str(organization_id))))
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    membership = await db.scalar(
        select(OrgMembership).where(
            OrgMembership.organization_id == organization.id,
            OrgMembership.user_id == current_user.id,
        )
    )
    if membership is None and getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return organization, current_user, db


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


def _normalize_working_draft_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized = _serialize_form_state(dict(snapshot or {}))
        if normalized.get("kind") == ArtifactKind.TOOL_IMPL.value:
            tool_contract = parse_tool_contract_json(
                normalized.get("tool_contract"),
                source="draft_snapshot.tool_contract",
            )
            normalized["tool_contract"] = json.dumps(tool_contract, indent=2, sort_keys=False)
        return normalized
    except (ToolContractValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _duplicate_name_base(display_name: str) -> str:
    raw = str(display_name or "").strip()
    if not raw:
        return "Untitled Artifact"
    match = _DUPLICATE_NAME_SUFFIX_RE.match(raw)
    base = str(match.group("base") if match else raw).strip()
    return base or raw


def _next_duplicate_display_name(display_name: str, existing_names: list[str]) -> str:
    base = _duplicate_name_base(display_name)
    taken_indexes: set[int] = set()
    for candidate in existing_names:
        candidate_raw = str(candidate or "").strip()
        if not candidate_raw:
            continue
        match = _DUPLICATE_NAME_SUFFIX_RE.match(candidate_raw)
        if not match:
            continue
        candidate_base = str(match.group("base") or "").strip()
        if candidate_base != base:
            continue
        suffix = match.group("index")
        taken_indexes.add(int(suffix) if suffix is not None else 0)
    next_index = 1
    while next_index in taken_indexes:
        next_index += 1
    return f"{base} ({next_index})"


def _artifact_to_schema(artifact: ArtifactModel, *, include_code: bool = False) -> ArtifactSchema:
    active_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if active_revision is None:
        raise ValueError("Artifact is missing a current revision")
    artifact_type = ArtifactType.PUBLISHED if (
        artifact.status == ArtifactStatus.PUBLISHED and active_revision.is_published
    ) else ArtifactType.DRAFT
    runtime = {
        "language": str(getattr(active_revision.language, "value", active_revision.language) or "python"),
        "source_files": list(active_revision.source_files or []) if include_code else [],
        "entry_module_path": active_revision.entry_module_path,
        "dependencies": list(active_revision.python_dependencies or []),
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


async def _link_artifact_coding_scope_to_saved_artifact(
    *,
    db: AsyncSession,
    organization_id: UUID,
    project_id: UUID | None,
    artifact_id: UUID,
    draft_key: str | None,
) -> None:
    normalized_draft_key = str(draft_key or "").strip() or None
    if normalized_draft_key is None:
        return
    await ArtifactCodingSharedDraftService(db).link_scope_to_artifact(
        organization_id=organization_id,
        project_id=project_id,
        draft_key=normalized_draft_key,
        artifact_id=artifact_id,
    )
    await ArtifactCodingChatHistoryService(db).link_sessions_to_artifact(
        organization_id=organization_id,
        project_id=project_id,
        draft_key=normalized_draft_key,
        artifact_id=artifact_id,
    )


def _artifact_revision_to_version_schema(
    artifact: ArtifactModel,
    revision: ArtifactRevisionModel,
    *,
    include_code: bool = False,
) -> ArtifactVersionSchema:
    runtime = {
        "language": str(getattr(revision.language, "value", revision.language) or "python"),
        "source_files": list(revision.source_files or []) if include_code else [],
        "entry_module_path": revision.entry_module_path,
        "dependencies": list(revision.python_dependencies or []),
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


def _artifact_revision_to_version_list_item(
    artifact: ArtifactModel,
    revision: ArtifactRevisionModel,
) -> ArtifactVersionListItem:
    return ArtifactVersionListItem(
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
    )


def _artifact_transfer_payload_from_artifact(artifact: ArtifactModel) -> ArtifactTransferPayload:
    active_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if active_revision is None:
        raise HTTPException(status_code=409, detail="Artifact is missing a current revision")
    return ArtifactTransferPayload(
        display_name=artifact.display_name,
        description=artifact.description,
        kind=getattr(artifact.kind, "value", artifact.kind),
        runtime={
            "language": str(getattr(active_revision.language, "value", active_revision.language) or "python"),
            "source_files": list(active_revision.source_files or []),
            "entry_module_path": active_revision.entry_module_path,
            "dependencies": list(active_revision.python_dependencies or []),
            "runtime_target": str(active_revision.runtime_target or "cloudflare_workers"),
        },
        capabilities=dict(active_revision.capabilities or {}),
        config_schema=dict(active_revision.config_schema or {}),
        agent_contract=dict(active_revision.agent_contract or {}) if active_revision.agent_contract is not None else None,
        rag_contract=dict(active_revision.rag_contract or {}) if active_revision.rag_contract is not None else None,
        tool_contract=dict(active_revision.tool_contract or {}) if active_revision.tool_contract is not None else None,
        published=bool(
            artifact.status == ArtifactStatus.PUBLISHED
            and artifact.latest_published_revision_id is not None
        ),
    )


@router.get("", response_model=dict[str, Any])
async def list_artifacts(
    organization_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    view: str = "summary",
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    query = ListQuery.from_payload({"skip": skip, "limit": limit, "view": view})
    page = await ArtifactAdminService(db).list_artifacts(
        ctx=_artifact_control_plane_context(organization=organization, user=user, context=principal),
        query=query,
    )
    return page.to_payload()


@router.get("/{artifact_id}", response_model=ArtifactSchema)
async def get_artifact(
    artifact_id: str,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    project_id = _principal_project_id(principal)
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization is not None else None,
        project_id=project_id,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _artifact_to_schema(artifact, include_code=True)


@router.get("/{artifact_id}/export", response_model=ArtifactTransferFile)
async def export_artifact(
    artifact_id: str,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    project_id = _principal_project_id(principal)
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization is not None else None,
        project_id=project_id,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactTransferFile(
        exported_at=artifact.updated_at,
        artifact=_artifact_transfer_payload_from_artifact(artifact),
    )


@router.post("/import", response_model=ArtifactImportResponse)
async def import_artifact(
    request: ArtifactTransferFile,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    if organization is None:
        raise HTTPException(status_code=400, detail="Organization context required")
    project_id = _principal_project_id(principal)
    if project_id is None:
        raise HTTPException(status_code=422, detail="Active project context is required")
    registry = ArtifactRegistryService(db)
    accessible_artifacts = await registry.list_accessible_artifacts(organization_id=organization.id, project_id=project_id)
    imported_payload = request.artifact
    display_name = imported_payload.display_name
    if any(artifact.display_name == display_name for artifact in accessible_artifacts):
        display_name = _next_duplicate_display_name(
            imported_payload.display_name,
            [artifact.display_name for artifact in accessible_artifacts],
        )
    created = await ArtifactRevisionService(db).create_artifact(
        organization_id=organization.id,
        created_by=user.id if user else None,
        display_name=display_name,
        description=imported_payload.description,
        kind=getattr(imported_payload.kind, "value", imported_payload.kind),
        owner_type=ArtifactOwnerType.TENANT.value,
        source_files=[_model_dump(item) for item in imported_payload.runtime.source_files],
        entry_module_path=imported_payload.runtime.entry_module_path,
        language=getattr(imported_payload.runtime.language, "value", imported_payload.runtime.language),
        dependencies=list(imported_payload.runtime.dependencies or []),
        runtime_target=str(imported_payload.runtime.runtime_target or "cloudflare_workers"),
        capabilities=_model_dump(imported_payload.capabilities),
        config_schema=dict(imported_payload.config_schema or {}),
        agent_contract=_model_dump(imported_payload.agent_contract) if imported_payload.agent_contract is not None else None,
        rag_contract=_model_dump(imported_payload.rag_contract) if imported_payload.rag_contract is not None else None,
        tool_contract=_model_dump(imported_payload.tool_contract) if imported_payload.tool_contract is not None else None,
    )
    created.project_id = project_id
    try:
        await ToolBindingService(db).sync_artifact_tool_binding(created)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    imported_artifact = await registry.get_organization_artifact(
        artifact_id=created.id,
        organization_id=organization.id,
        project_id=project_id,
    )
    if imported_artifact is None:
        raise HTTPException(status_code=500, detail="Imported artifact could not be loaded")
    return ArtifactImportResponse(
        artifact=_artifact_to_schema(imported_artifact, include_code=True),
        source_published=bool(imported_payload.published),
    )


@router.post("/validate-source", response_model=ArtifactSourceValidationResponse)
async def validate_artifact_source(
    request: ArtifactSourceValidationRequest,
    organization_id: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    _tenant, _user, _db = artifact_ctx
    diagnostics = validate_source_files_for_editor(
        language=getattr(request.language, "value", request.language),
        source_files=[_model_dump(item) for item in request.source_files],
        dependencies=list(request.dependencies or []),
    )
    return ArtifactSourceValidationResponse(diagnostics=diagnostics)


@router.post("/analyze-dependencies", response_model=ArtifactDependencyAnalysisResponse)
async def analyze_artifact_dependencies_route(
    request: ArtifactDependencyAnalysisRequest,
    organization_id: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    _tenant, _user, _db = artifact_ctx
    rows = analyze_artifact_dependencies(
        language=getattr(request.language, "value", request.language),
        source_files=[_model_dump(item) for item in request.source_files],
        dependencies=list(request.dependencies or []),
    )
    return ArtifactDependencyAnalysisResponse(rows=rows)


@router.post("/verify-python-package", response_model=PythonPackageVerificationResponse)
async def verify_python_package_route(
    request: PythonPackageVerificationRequest,
    organization_id: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    _tenant, _user, _db = artifact_ctx
    result = await verify_python_package_exists(request.package_name)
    return PythonPackageVerificationResponse(**result)


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
            "language": str(getattr(active_revision.language, "value", active_revision.language) or "python"),
            "dependencies": ", ".join(list(active_revision.python_dependencies or [])),
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
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    project_id = _principal_project_id(principal)
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization is not None else None,
        project_id=project_id,
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
        versions.append(_artifact_revision_to_version_list_item(artifact, revision))
    return versions


@router.get("/{artifact_id}/versions/{revision_id}", response_model=ArtifactVersionSchema)
async def get_artifact_version(
    artifact_id: str,
    revision_id: str,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    project_id = _principal_project_id(principal)
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    revision_uuid = _parse_artifact_uuid(revision_id)
    if artifact_uuid is None or revision_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization is not None else None,
        project_id=project_id,
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
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.read")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    project_id = _principal_project_id(principal)
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_accessible_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization is not None else None,
        project_id=project_id,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    initial_snapshot = _artifact_form_snapshot(artifact)
    shared = await ArtifactCodingSharedDraftService(db).get_or_create_for_scope(
        organization_id=organization.id if organization is not None else artifact.organization_id,
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
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    project_id = _principal_project_id(principal)
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_organization_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id,
        project_id=project_id,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    shared_service = ArtifactCodingSharedDraftService(db)
    shared = await shared_service.get_or_create_for_scope(
        organization_id=organization.id,
        artifact_id=artifact.id,
        draft_key=None,
        initial_snapshot=_artifact_form_snapshot(artifact),
    )
    normalized_snapshot = _normalize_working_draft_snapshot(dict(request.draft_snapshot or {}))
    await shared_service.update_snapshot(
        shared_draft=shared,
        draft_snapshot=normalized_snapshot,
        artifact_id=artifact.id,
        draft_key=None,
    )
    await db.commit()
    return ArtifactWorkingDraftResponse(
        artifact_id=str(artifact.id),
        draft_key=None,
        draft_snapshot=dict(shared.working_draft_snapshot or normalized_snapshot),
        updated_at=shared.updated_at,
    )

@router.post("", response_model=ArtifactSchema)
async def create_artifact_draft(
    request: ArtifactCreate,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    try:
        payload = await ArtifactAdminService(db).create_artifact(
            ctx=_artifact_control_plane_context(organization=organization, user=user, context=principal),
            params=ControlPlaneCreateArtifactInput(
                display_name=request.display_name,
                description=request.description,
                kind=request.kind.value,
                runtime=ControlPlaneArtifactRuntimeInput(
                    language=getattr(request.runtime.language, "value", request.runtime.language),
                    source_files=[_model_dump(item) for item in request.runtime.source_files],
                    entry_module_path=request.runtime.entry_module_path,
                    dependencies=list(request.runtime.dependencies or []),
                    runtime_target=request.runtime.runtime_target,
                ),
                capabilities=_model_dump(request.capabilities),
                config_schema=dict(request.config_schema or {}),
                agent_contract=_model_dump(request.agent_contract) if request.agent_contract is not None else None,
                rag_contract=_model_dump(request.rag_contract) if request.rag_contract is not None else None,
                tool_contract=_model_dump(request.tool_contract) if request.tool_contract is not None else None,
            ),
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    await _link_artifact_coding_scope_to_saved_artifact(
        db=db,
        organization_id=organization.id,
        project_id=_principal_project_id(principal),
        artifact_id=UUID(str(payload["id"])),
        draft_key=request.draft_key,
    )
    await db.commit()
    return ArtifactSchema(**payload)


@router.put("/{artifact_id}", response_model=ArtifactSchema)
async def update_artifact(
    artifact_id: str,
    update_data: ArtifactUpdate,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    payload = _model_dump(update_data, exclude_unset=True)
    runtime = payload.get("runtime") or {}
    try:
        response_payload = await ArtifactAdminService(db).update_artifact(
            ctx=_artifact_control_plane_context(organization=organization, user=user, context=principal),
            artifact_id=artifact_uuid,
            params=ControlPlaneUpdateArtifactInput(
                display_name=payload.get("display_name"),
                description=payload.get("description"),
                runtime=ControlPlaneArtifactRuntimeInput(
                    language=str(runtime.get("language", "python")),
                    source_files=list(runtime.get("source_files") or []),
                    entry_module_path=str(runtime.get("entry_module_path") or "main.py"),
                    dependencies=list(runtime.get("dependencies") or []),
                    runtime_target=str(runtime.get("runtime_target") or "cloudflare_workers"),
                ) if runtime else None,
                capabilities=dict(payload.get("capabilities")) if isinstance(payload.get("capabilities"), dict) else None,
                config_schema=dict(payload.get("config_schema")) if isinstance(payload.get("config_schema"), dict) else None,
                agent_contract=payload.get("agent_contract") if isinstance(payload.get("agent_contract"), dict) else None,
                rag_contract=payload.get("rag_contract") if isinstance(payload.get("rag_contract"), dict) else None,
                tool_contract=payload.get("tool_contract") if isinstance(payload.get("tool_contract"), dict) else None,
            ),
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    await _link_artifact_coding_scope_to_saved_artifact(
        db=db,
        organization_id=organization.id,
        project_id=_principal_project_id(principal),
        artifact_id=artifact_uuid,
        draft_key=update_data.draft_key,
    )
    await db.commit()
    return ArtifactSchema(**response_payload)


@router.post("/{artifact_id}/publish", response_model=ArtifactPublishResponse)
async def publish_artifact(
    artifact_id: str,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.publish")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_organization_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization else None,
        project_id=_principal_project_id(principal),
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await ensure_sensitive_action_approved(
        principal=principal,
        organization_id=organization.id,
        subject_type="artifact",
        subject_id=str(artifact.id),
        action_scope="artifacts.publish",
        db=db,
    )
    try:
        payload = await ArtifactAdminService(db).publish_artifact(
            ctx=_artifact_control_plane_context(organization=organization, user=_user, context=principal),
            artifact_id=artifact_uuid,
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    return ArtifactPublishResponse(**payload)


@router.post("/{artifact_id}/convert-kind", response_model=ArtifactSchema)
async def convert_artifact_kind(
    artifact_id: str,
    request: ArtifactConvertKindRequest,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        payload = await ArtifactAdminService(db).convert_kind(
            ctx=_artifact_control_plane_context(organization=organization, user=user, context=principal),
            artifact_id=artifact_uuid,
            kind=request.kind.value,
            agent_contract=_model_dump(request.agent_contract) if request.agent_contract is not None else None,
            rag_contract=_model_dump(request.rag_contract) if request.rag_contract is not None else None,
            tool_contract=_model_dump(request.tool_contract) if request.tool_contract is not None else None,
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    return ArtifactSchema(**payload)


@router.post("/{artifact_id}/duplicate", response_model=ArtifactSchema)
async def duplicate_artifact(
    artifact_id: str,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    if organization is None:
        raise HTTPException(status_code=400, detail="Organization context required")
    project_id = _principal_project_id(principal)
    if project_id is None:
        raise HTTPException(status_code=422, detail="Active project context is required")
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    registry = ArtifactRegistryService(db)
    source_artifact = await registry.get_accessible_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id,
        project_id=project_id,
    )
    if source_artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    source_revision = source_artifact.latest_draft_revision or source_artifact.latest_published_revision
    if source_revision is None:
        raise HTTPException(status_code=409, detail="Artifact is missing a current revision")
    accessible_artifacts = await registry.list_accessible_artifacts(organization_id=organization.id, project_id=project_id)
    duplicate_name = _next_duplicate_display_name(
        source_artifact.display_name,
        [artifact.display_name for artifact in accessible_artifacts],
    )
    duplicated = await ArtifactRevisionService(db).create_artifact(
        organization_id=organization.id,
        created_by=user.id if user else None,
        display_name=duplicate_name,
        description=source_artifact.description,
        kind=getattr(source_artifact.kind, "value", source_artifact.kind),
        owner_type=ArtifactOwnerType.TENANT.value,
        source_files=list(source_revision.source_files or []),
        entry_module_path=source_revision.entry_module_path,
        language=getattr(source_revision.language, "value", source_revision.language),
        dependencies=list(source_revision.python_dependencies or []),
        runtime_target=str(source_revision.runtime_target or "cloudflare_workers"),
        capabilities=dict(source_revision.capabilities or {}),
        config_schema=dict(source_revision.config_schema or {}),
        agent_contract=dict(source_revision.agent_contract or {}) if source_revision.agent_contract is not None else None,
        rag_contract=dict(source_revision.rag_contract or {}) if source_revision.rag_contract is not None else None,
        tool_contract=dict(source_revision.tool_contract or {}) if source_revision.tool_contract is not None else None,
    )
    duplicated.project_id = project_id
    try:
        await ToolBindingService(db).sync_artifact_tool_binding(duplicated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    refreshed = await registry.get_organization_artifact(
        artifact_id=duplicated.id,
        organization_id=organization.id,
        project_id=project_id,
    )
    return _artifact_to_schema(refreshed, include_code=True)


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, _user, db = artifact_ctx
    artifact_uuid = _parse_artifact_uuid(artifact_id)
    if artifact_uuid is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = await ArtifactRegistryService(db).get_organization_artifact(
        artifact_id=artifact_uuid,
        organization_id=organization.id if organization else None,
        project_id=_principal_project_id(principal),
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await ensure_sensitive_action_approved(
        principal=principal,
        organization_id=organization.id,
        subject_type="artifact",
        subject_id=str(artifact.id),
        action_scope="artifacts.delete",
        db=db,
    )
    try:
        return await ArtifactAdminService(db).delete_artifact(
            ctx=_artifact_control_plane_context(organization=organization, user=_user, context=principal),
            artifact_id=artifact_uuid,
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/test-runs", response_model=ArtifactRunCreateResponse)
async def create_unsaved_test_run(
    request: ArtifactTestRequest,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    organization, user, db = artifact_ctx
    organization = await _resolve_organization_from_artifact_if_missing(
        organization=organization,
        user=user,
        db=db,
        artifact_id=request.artifact_id,
    )
    try:
        operation = await ArtifactAdminService(db).create_test_run(
            ctx=_artifact_control_plane_context(organization=organization, user=user, context=principal),
            artifact_id=_parse_artifact_uuid(request.artifact_id),
            source_files=[_model_dump(item) for item in request.source_files],
            entry_module_path=request.entry_module_path,
            input_data=request.input_data,
            config=request.config or {},
            dependencies=list(request.dependencies or []),
            language=getattr(request.language, "value", request.language) if getattr(request, "language", None) else None,
            kind=getattr(request.kind, "value", request.kind) if getattr(request, "kind", None) else None,
            runtime_target=getattr(request, "runtime_target", None),
            capabilities=dict(getattr(request, "capabilities", None) or {}),
            config_schema=dict(getattr(request, "config_schema", None) or {}),
            agent_contract=_model_dump(request.agent_contract) if getattr(request, "agent_contract", None) is not None else None,
            rag_contract=_model_dump(request.rag_contract) if getattr(request, "rag_contract", None) is not None else None,
            tool_contract=_model_dump(request.tool_contract) if getattr(request, "tool_contract", None) is not None else None,
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    return ArtifactRunCreateResponse(
        run_id=operation["operation"]["id"],
        status=operation["operation"]["status"],
    )


@router.post("/{artifact_id}/test-runs", response_model=ArtifactRunCreateResponse)
async def create_saved_artifact_test_run(
    artifact_id: str,
    request: ArtifactTestRequest,
    organization_id: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    request.artifact_id = artifact_id
    return await create_unsaved_test_run(
        request,
        organization_id=organization_id,
        principal=principal,
        artifact_ctx=artifact_ctx,
    )
