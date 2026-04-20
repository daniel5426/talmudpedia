from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.api.routers.auth import get_current_user
from app.api.routers.org_units import _normalize_tenant_settings, _validate_default_model_id
from app.api.routers.rbac import _role_permissions
from app.core.scope_registry import (
    ORGANIZATION_READER_ROLE,
    PROJECT_MEMBER_ROLE,
    ROLE_FAMILY_ORGANIZATION,
    ROLE_FAMILY_PROJECT,
    allowed_scopes_for_role_family,
    is_preset_role,
    normalize_scope_list,
)
from app.db.postgres.models.audit import AuditLog, AuditResult
from app.db.postgres.models.identity import MembershipStatus, OrgInvite, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, TenantStatus, User
from app.db.postgres.models.registry import ModelCapabilityType
from app.db.postgres.models.rbac import Action, ActorType, ResourceType, Role, RoleAssignment, RolePermission
from app.db.postgres.models.security import ProjectAPIKey, ProjectAPIKeyStatus, TenantAPIKey, TenantAPIKeyStatus
from app.db.postgres.models.usage_quota import UsageQuotaPolicy, UsageQuotaScopeType
from app.db.postgres.models.workspace import Project, ProjectStatus
from app.db.postgres.session import get_db
from app.services.auth_context_service import serialize_project_summary, serialize_user_summary
from app.services.project_api_key_service import ProjectAPIKeyNotFoundError, ProjectAPIKeyService
from app.services.tenant_api_key_service import TenantAPIKeyNotFoundError, TenantAPIKeyService
from app.services.workos_auth_service import WorkOSAuthService

router = APIRouter(prefix="/api/settings", tags=["settings-governance"])


class ProfileResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    avatar: str | None = None
    role: str


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    avatar: str | None = None


class OrganizationSettingsResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    default_chat_model_id: str | None = None
    default_embedding_model_id: str | None = None
    default_retrieval_policy: str | None = None


class UpdateOrganizationSettingsRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    status: str | None = None
    default_chat_model_id: str | None = None
    default_embedding_model_id: str | None = None
    default_retrieval_policy: str | None = None


class MemberResponse(BaseModel):
    membership_id: str
    user_id: str
    email: str
    full_name: str | None = None
    avatar: str | None = None
    organization_role: str
    org_unit_id: str
    org_unit_name: str
    joined_at: datetime


class InviteResponse(BaseModel):
    id: str
    email: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    organization_role: str = ORGANIZATION_READER_ROLE
    project_role: str | None = None
    accepted_at: datetime | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None


class CreateInviteRequest(BaseModel):
    email: EmailStr
    project_ids: list[str] = Field(default_factory=list)


class GroupResponse(BaseModel):
    id: str
    tenant_id: str
    parent_id: str | None = None
    name: str
    slug: str
    type: str
    created_at: datetime


class CreateGroupRequest(BaseModel):
    name: str
    slug: str
    type: OrgUnitType
    parent_id: str | None = None


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    parent_id: str | None = None


class RoleResponse(BaseModel):
    id: str
    family: str
    name: str
    description: str | None = None
    permissions: list[str]
    is_system: bool
    is_preset: bool
    created_at: datetime


class RoleAssignmentResponse(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    role_id: str
    role_family: str
    role_name: str
    scope_id: str
    scope_type: str
    assigned_at: datetime


class CreateRoleRequest(BaseModel):
    family: str
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    family: str | None = None
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class CreateRoleAssignmentRequest(BaseModel):
    user_id: str
    role_id: str
    scope_id: str
    scope_type: str
    actor_type: ActorType = ActorType.USER


class ProjectSummaryResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    slug: str
    description: str | None = None
    status: str
    is_default: bool
    created_at: datetime
    member_count: int


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class SettingsApiKeyResponse(BaseModel):
    id: str
    owner_scope: str
    owner_scope_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    status: str
    created_by: str | None = None
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class CreateSettingsApiKeyRequest(BaseModel):
    owner_scope: str
    project_slug: str | None = None
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["agents.embed"])


class LimitResponse(BaseModel):
    owner_scope: str
    owner_scope_id: str
    monthly_token_limit: int | None = None
    inherited_monthly_token_limit: int | None = None
    effective_monthly_token_limit: int | None = None


class UpdateLimitRequest(BaseModel):
    monthly_token_limit: int | None = None


class AuditLogResponse(BaseModel):
    id: str
    actor_email: str
    action: str
    resource_type: str
    resource_id: str | None = None
    resource_name: str | None = None
    result: str
    failure_reason: str | None = None
    timestamp: datetime
    duration_ms: int | None = None


class AuditLogDetailResponse(AuditLogResponse):
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    request_params: dict[str, Any] | None = None


def _require_scope(principal: dict[str, Any], *required_scopes: str) -> None:
    scopes = set(principal.get("scopes") or [])
    if "*" in scopes:
        return
    for scope in required_scopes:
        if scope in scopes:
            return
    raise HTTPException(status_code=403, detail=f"Missing required scope: {' or '.join(required_scopes)}")


def _normalize_role_family(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {ROLE_FAMILY_ORGANIZATION, ROLE_FAMILY_PROJECT}:
        raise HTTPException(status_code=400, detail="Role family must be organization or project")
    return normalized


def _normalize_assignment_scope_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"organization", "tenant", "org", "org_unit"}:
        return ROLE_FAMILY_ORGANIZATION
    if normalized == "project":
        return ROLE_FAMILY_PROJECT
    raise HTTPException(status_code=400, detail="Role assignments must target organization or project scope")


def _validate_role_permissions(*, family: str, permissions: list[str]) -> list[str]:
    normalized = normalize_scope_list(permissions)
    allowed = allowed_scopes_for_role_family(family)
    invalid = [scope for scope in normalized if scope not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid {family} role scopes: {', '.join(invalid)}")
    return normalized


async def _active_organization(db: AsyncSession, principal: dict[str, Any]) -> Tenant:
    organization_id = principal.get("organization_id") or principal.get("tenant_id")
    if not organization_id:
        raise HTTPException(status_code=400, detail="Active organization context is required")
    organization = await db.get(Tenant, UUID(str(organization_id)))
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


async def _project_or_404(db: AsyncSession, organization_id: UUID, project_slug: str) -> Project:
    project = (
        await db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.slug == project_slug,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _serialize_group(group: OrgUnit) -> GroupResponse:
    return GroupResponse(
        id=str(group.id),
        tenant_id=str(group.tenant_id),
        parent_id=str(group.parent_id) if group.parent_id else None,
        name=group.name,
        slug=group.slug,
        type=group.type.value if hasattr(group.type, "value") else str(group.type),
        created_at=group.created_at,
    )


def _serialize_api_key_row(
    row: TenantAPIKey | ProjectAPIKey,
    *,
    owner_scope: str,
    owner_scope_id: UUID,
) -> SettingsApiKeyResponse:
    return SettingsApiKeyResponse(
        id=str(row.id),
        owner_scope=owner_scope,
        owner_scope_id=str(owner_scope_id),
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=list(row.scopes or []),
        status=row.status.value if hasattr(row.status, "value") else str(row.status),
        created_by=str(row.created_by) if row.created_by else None,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
    )


async def _tenant_usage_quota_policy(db: AsyncSession, tenant_id: UUID) -> UsageQuotaPolicy | None:
    return (
        await db.execute(
            select(UsageQuotaPolicy)
            .where(
                UsageQuotaPolicy.tenant_id == tenant_id,
                UsageQuotaPolicy.user_id.is_(None),
                UsageQuotaPolicy.scope_type == UsageQuotaScopeType.tenant,
                UsageQuotaPolicy.is_active.is_(True),
            )
            .order_by(UsageQuotaPolicy.updated_at.desc(), UsageQuotaPolicy.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _project_member_count(db: AsyncSession, tenant_id: UUID, project_id: UUID) -> int:
    result = await db.execute(
        select(func.count(sa.distinct(RoleAssignment.user_id)))
        .where(
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.scope_type == "project",
            RoleAssignment.scope_id == project_id,
        )
    )
    return int(result.scalar() or 0)


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user)) -> ProfileResponse:
    return ProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        avatar=current_user.avatar,
        role=str(current_user.role),
    )


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    if "full_name" in payload.model_fields_set:
        current_user.full_name = payload.full_name
    if "avatar" in payload.model_fields_set:
        current_user.avatar = payload.avatar
    await db.commit()
    await db.refresh(current_user)
    return await get_profile(current_user=current_user)


@router.get("/organization", response_model=OrganizationSettingsResponse)
async def get_organization_settings(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSettingsResponse:
    _require_scope(principal, "organizations.read", "organizations.write")
    organization = await _active_organization(db, principal)
    defaults = _normalize_tenant_settings(organization.settings)
    return OrganizationSettingsResponse(
        id=str(organization.id),
        name=organization.name,
        slug=organization.slug,
        status=organization.status.value if hasattr(organization.status, "value") else str(organization.status),
        default_chat_model_id=defaults.default_chat_model_id,
        default_embedding_model_id=defaults.default_embedding_model_id,
        default_retrieval_policy=(
            defaults.default_retrieval_policy.value
            if hasattr(defaults.default_retrieval_policy, "value")
            else defaults.default_retrieval_policy
        ),
    )


@router.patch("/organization", response_model=OrganizationSettingsResponse)
async def update_organization_settings(
    payload: UpdateOrganizationSettingsRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSettingsResponse:
    _require_scope(principal, "organizations.write")
    organization = await _active_organization(db, principal)

    if "name" in payload.model_fields_set and payload.name is not None:
        organization.name = payload.name
    if "slug" in payload.model_fields_set and payload.slug and payload.slug != organization.slug:
        duplicate = (
            await db.execute(
                select(Tenant).where(Tenant.slug == payload.slug, Tenant.id != organization.id)
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="Organization slug already exists")
        organization.slug = payload.slug
    if "status" in payload.model_fields_set and payload.status is not None:
        organization.status = TenantStatus(payload.status)

    settings = dict(organization.settings or {})
    if "default_chat_model_id" in payload.model_fields_set:
        settings["default_chat_model_id"] = await _validate_default_model_id(
            model_id=payload.default_chat_model_id,
            capability=ModelCapabilityType.CHAT,
            tenant=organization,
            db=db,
        )
    if "default_embedding_model_id" in payload.model_fields_set:
        settings["default_embedding_model_id"] = await _validate_default_model_id(
            model_id=payload.default_embedding_model_id,
            capability=ModelCapabilityType.EMBEDDING,
            tenant=organization,
            db=db,
        )
    if "default_retrieval_policy" in payload.model_fields_set:
        settings["default_retrieval_policy"] = payload.default_retrieval_policy
    organization.settings = settings

    await db.commit()
    await db.refresh(organization)
    return await get_organization_settings(principal=principal, db=db)


@router.get("/people/members", response_model=list[MemberResponse])
async def list_members(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    _require_scope(principal, "organization_members.read")
    organization = await _active_organization(db, principal)

    memberships = (
        await db.execute(
            select(OrgMembership, User, OrgUnit)
            .join(User, User.id == OrgMembership.user_id)
            .join(OrgUnit, OrgUnit.id == OrgMembership.org_unit_id)
            .where(
                OrgMembership.tenant_id == organization.id,
                OrgMembership.status == MembershipStatus.active,
            )
            .order_by(User.email.asc())
        )
    ).all()
    return [
        MemberResponse(
            membership_id=str(membership.id),
            user_id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            avatar=user.avatar,
            organization_role=membership.role.value if hasattr(membership.role, "value") else str(membership.role),
            org_unit_id=str(org_unit.id),
            org_unit_name=org_unit.name,
            joined_at=membership.joined_at,
        )
        for membership, user, org_unit in memberships
    ]


@router.delete("/people/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    membership_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_scope(principal, "organization_members.delete")
    organization = await _active_organization(db, principal)
    membership = (
        await db.execute(
            select(OrgMembership).where(
                OrgMembership.id == membership_id,
                OrgMembership.tenant_id == organization.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    await db.delete(membership)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/people/invitations", response_model=list[InviteResponse])
async def list_invitations(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[InviteResponse]:
    _require_scope(principal, "organization_invites.read")
    organization = await _active_organization(db, principal)
    if not organization.workos_organization_id:
        return []
    local_invites = (
        await db.execute(select(OrgInvite).where(OrgInvite.tenant_id == organization.id, OrgInvite.accepted_at.is_(None)))
    ).scalars().all()
    local_by_token = {invite.token: invite for invite in local_invites}
    invites = WorkOSAuthService(db).client.user_management.list_invitations(
        organization_id=organization.workos_organization_id,
    )
    return [
        InviteResponse(
            id=str(getattr(invite, "id", "")),
            email=getattr(invite, "email", None),
            project_ids=list(local_by_token.get(str(getattr(invite, "id", "")), None).project_ids if local_by_token.get(str(getattr(invite, "id", "")), None) else []),
            organization_role=ORGANIZATION_READER_ROLE,
            project_role=PROJECT_MEMBER_ROLE if local_by_token.get(str(getattr(invite, "id", "")), None) and local_by_token.get(str(getattr(invite, "id", "")), None).project_ids else None,
            accepted_at=getattr(invite, "accepted_at", None) or getattr(invite, "acceptedAt", None),
            created_at=getattr(invite, "created_at", None) or getattr(invite, "createdAt", None),
            expires_at=getattr(invite, "expires_at", None) or getattr(invite, "expiresAt", None),
        )
        for invite in invites
    ]


@router.post("/people/invitations", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: CreateInviteRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    _require_scope(principal, "organization_invites.write")
    organization = await _active_organization(db, principal)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")

    if payload.project_ids:
        allowed_ids = {
            str(project.id)
            for project in (
                await db.execute(select(Project).where(Project.organization_id == organization.id))
            ).scalars().all()
        }
        invalid = [project_id for project_id in payload.project_ids if project_id not in allowed_ids]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown project ids: {', '.join(invalid)}")

    current_user = await db.get(User, UUID(str(principal["user_id"])))
    invite = WorkOSAuthService(db).client.user_management.send_invitation(
        email=str(payload.email),
        organization_id=organization.workos_organization_id,
        inviter_user_id=current_user.workos_user_id if current_user and current_user.workos_user_id else None,
    )
    db.add(
        OrgInvite(
            email=str(payload.email),
            tenant_id=organization.id,
            role=OrgRole.member,
            project_ids=payload.project_ids,
            token=str(getattr(invite, "id", "")),
            expires_at=(getattr(invite, "expires_at", None) or getattr(invite, "expiresAt", None) or datetime.now(timezone.utc)),
            created_by=UUID(str(principal["user_id"])),
        )
    )
    await db.commit()
    return InviteResponse(
        id=str(getattr(invite, "id", "")),
        email=getattr(invite, "email", None),
        project_ids=payload.project_ids,
        organization_role=ORGANIZATION_READER_ROLE,
        project_role=PROJECT_MEMBER_ROLE if payload.project_ids else None,
        accepted_at=getattr(invite, "accepted_at", None) or getattr(invite, "acceptedAt", None),
        created_at=getattr(invite, "created_at", None) or getattr(invite, "createdAt", None),
        expires_at=getattr(invite, "expires_at", None) or getattr(invite, "expiresAt", None),
    )


@router.delete("/people/invitations/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invite_id: str,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_scope(principal, "organization_invites.delete")
    organization = await _active_organization(db, principal)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")
    WorkOSAuthService(db).client.user_management.revoke_invitation(invite_id)
    local_invite = (
        await db.execute(
            select(OrgInvite).where(
                OrgInvite.tenant_id == organization.id,
                OrgInvite.token == invite_id,
                OrgInvite.accepted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if local_invite is not None:
        await db.delete(local_invite)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/people/groups", response_model=list[GroupResponse])
async def list_groups(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[GroupResponse]:
    _require_scope(principal, "organization_units.read")
    organization = await _active_organization(db, principal)
    groups = (
        await db.execute(select(OrgUnit).where(OrgUnit.tenant_id == organization.id).order_by(OrgUnit.created_at.asc()))
    ).scalars().all()
    return [_serialize_group(group) for group in groups]


@router.post("/people/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: CreateGroupRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> GroupResponse:
    _require_scope(principal, "organization_units.write")
    organization = await _active_organization(db, principal)
    parent_id = UUID(payload.parent_id) if payload.parent_id else None
    if parent_id:
        parent = await db.get(OrgUnit, parent_id)
        if parent is None or parent.tenant_id != organization.id:
            raise HTTPException(status_code=404, detail="Parent group not found")
    group = OrgUnit(
        tenant_id=organization.id,
        parent_id=parent_id,
        name=payload.name,
        slug=payload.slug,
        type=payload.type,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return _serialize_group(group)


@router.patch("/people/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: UUID,
    payload: UpdateGroupRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> GroupResponse:
    _require_scope(principal, "organization_units.write")
    organization = await _active_organization(db, principal)
    group = (
        await db.execute(select(OrgUnit).where(OrgUnit.id == group_id, OrgUnit.tenant_id == organization.id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    if "name" in payload.model_fields_set and payload.name is not None:
        group.name = payload.name
    if "slug" in payload.model_fields_set and payload.slug is not None:
        group.slug = payload.slug
    if "parent_id" in payload.model_fields_set:
        group.parent_id = UUID(payload.parent_id) if payload.parent_id else None
    await db.commit()
    await db.refresh(group)
    return _serialize_group(group)


@router.delete("/people/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_scope(principal, "organization_units.delete")
    organization = await _active_organization(db, principal)
    group = (
        await db.execute(select(OrgUnit).where(OrgUnit.id == group_id, OrgUnit.tenant_id == organization.id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.parent_id is None or group.type == OrgUnitType.org:
        raise HTTPException(status_code=400, detail="Root organization group cannot be deleted")
    child = (await db.execute(select(OrgUnit).where(OrgUnit.parent_id == group.id).limit(1))).scalar_one_or_none()
    if child is not None:
        raise HTTPException(status_code=400, detail="Group with child groups cannot be deleted")
    membership = (
        await db.execute(select(OrgMembership).where(OrgMembership.org_unit_id == group.id).limit(1))
    ).scalar_one_or_none()
    if membership is not None:
        raise HTTPException(status_code=400, detail="Group with active members cannot be deleted")
    await db.delete(group)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/people/roles", response_model=list[RoleResponse])
async def list_roles(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[RoleResponse]:
    _require_scope(principal, "roles.read")
    organization = await _active_organization(db, principal)
    roles = (
        await db.execute(select(Role).where(Role.tenant_id == organization.id).order_by(Role.name.asc()))
    ).scalars().all()
    return [
        RoleResponse(
            id=str(role.id),
            family=role.family,
            name=role.name,
            description=role.description,
            permissions=await _role_permissions(db, role.id),
            is_system=role.is_system,
            is_preset=is_preset_role(family=role.family, name=role.name),
            created_at=role.created_at,
        )
        for role in roles
    ]


@router.post("/people/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: CreateRoleRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> RoleResponse:
    _require_scope(principal, "roles.write")
    organization = await _active_organization(db, principal)
    family = _normalize_role_family(payload.family)
    permissions = _validate_role_permissions(family=family, permissions=payload.permissions)
    existing = (
        await db.execute(
            select(Role).where(
                Role.tenant_id == organization.id,
                Role.family == family,
                Role.name == payload.name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Role with this name already exists")
    role = Role(
        tenant_id=organization.id,
        family=family,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    for scope_key in permissions:
        db.add(RolePermission(role_id=role.id, scope_key=scope_key))
    await db.commit()
    await db.refresh(role)
    return RoleResponse(
        id=str(role.id),
        family=role.family,
        name=role.name,
        description=role.description,
        permissions=await _role_permissions(db, role.id),
        is_system=role.is_system,
        is_preset=False,
        created_at=role.created_at,
    )


@router.patch("/people/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    payload: UpdateRoleRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> RoleResponse:
    _require_scope(principal, "roles.write")
    organization = await _active_organization(db, principal)
    role = (
        await db.execute(select(Role).where(Role.id == role_id, Role.tenant_id == organization.id))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")
    if "family" in payload.model_fields_set and payload.family is not None:
        next_family = _normalize_role_family(payload.family)
        if next_family != role.family:
            raise HTTPException(status_code=400, detail="Role family cannot be changed")
    if "name" in payload.model_fields_set and payload.name is not None:
        role.name = payload.name
    if "description" in payload.model_fields_set:
        role.description = payload.description
    if payload.permissions is not None:
        permissions = _validate_role_permissions(family=role.family, permissions=payload.permissions)
        await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for scope_key in permissions:
            db.add(RolePermission(role_id=role.id, scope_key=scope_key))
    await db.commit()
    await db.refresh(role)
    return RoleResponse(
        id=str(role.id),
        family=role.family,
        name=role.name,
        description=role.description,
        permissions=await _role_permissions(db, role.id),
        is_system=role.is_system,
        is_preset=False,
        created_at=role.created_at,
    )


@router.delete("/people/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_scope(principal, "roles.write")
    organization = await _active_organization(db, principal)
    role = (
        await db.execute(select(Role).where(Role.id == role_id, Role.tenant_id == organization.id))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")
    active_assignment = (
        await db.execute(select(RoleAssignment).where(RoleAssignment.role_id == role.id).limit(1))
    ).scalar_one_or_none()
    if active_assignment is not None:
        raise HTTPException(status_code=400, detail="Cannot delete role with active assignments")
    await db.delete(role)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/people/role-assignments", response_model=list[RoleAssignmentResponse])
async def list_role_assignments(
    scope_type: str | None = None,
    scope_id: str | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[RoleAssignmentResponse]:
    _require_scope(principal, "roles.read")
    organization = await _active_organization(db, principal)
    conditions: list[Any] = [RoleAssignment.tenant_id == organization.id]
    if scope_type:
        conditions.append(RoleAssignment.scope_type == scope_type)
    if scope_id:
        conditions.append(RoleAssignment.scope_id == UUID(scope_id))

    rows = (
        await db.execute(
            select(RoleAssignment, Role, User)
            .join(Role, Role.id == RoleAssignment.role_id)
            .join(User, User.id == RoleAssignment.user_id)
            .where(*conditions)
            .order_by(User.email.asc(), Role.name.asc())
        )
    ).all()
    return [
        RoleAssignmentResponse(
            id=str(assignment.id),
            user_id=str(user.id),
            user_email=user.email,
            role_id=str(role.id),
            role_family=role.family,
            role_name=role.name,
            scope_id=str(assignment.scope_id),
            scope_type=assignment.scope_type,
            assigned_at=assignment.assigned_at,
        )
        for assignment, role, user in rows
    ]


@router.post("/people/role-assignments", response_model=RoleAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_role_assignment(
    payload: CreateRoleAssignmentRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> RoleAssignmentResponse:
    _require_scope(principal, "roles.assign")
    organization = await _active_organization(db, principal)
    role_id = UUID(payload.role_id)
    user_id = UUID(payload.user_id)
    scope_id = UUID(payload.scope_id)
    scope_type = _normalize_assignment_scope_type(payload.scope_type)
    role = (
        await db.execute(select(Role).where(Role.id == role_id, Role.tenant_id == organization.id))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.family != scope_type:
        raise HTTPException(status_code=400, detail="Role family does not match assignment scope")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    replacements = (
        await db.execute(
            select(RoleAssignment).where(
                RoleAssignment.tenant_id == organization.id,
                RoleAssignment.user_id == user_id,
                RoleAssignment.scope_id == scope_id,
                RoleAssignment.scope_type == scope_type,
            )
        )
    ).scalars().all()
    for existing in replacements:
        existing_role = await db.get(Role, existing.role_id)
        if existing_role is None or existing_role.family != role.family:
            continue
        if existing.role_id == role_id:
            return RoleAssignmentResponse(
                id=str(existing.id),
                user_id=str(user.id),
                user_email=user.email,
                role_id=str(role.id),
                role_family=role.family,
                role_name=role.name,
                scope_id=str(existing.scope_id),
                scope_type=existing.scope_type,
                assigned_at=existing.assigned_at,
            )
        await db.delete(existing)
    assignment = RoleAssignment(
        tenant_id=organization.id,
        user_id=user_id,
        role_id=role_id,
        scope_id=scope_id,
        scope_type=scope_type,
        actor_type=payload.actor_type,
        assigned_by=UUID(str(principal["user_id"])),
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return RoleAssignmentResponse(
        id=str(assignment.id),
        user_id=str(user.id),
        user_email=user.email,
        role_id=str(role.id),
        role_family=role.family,
        role_name=role.name,
        scope_id=str(assignment.scope_id),
        scope_type=assignment.scope_type,
        assigned_at=assignment.assigned_at,
    )


@router.delete("/people/role-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role_assignment(
    assignment_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_scope(principal, "roles.assign")
    organization = await _active_organization(db, principal)
    assignment = (
        await db.execute(
            select(RoleAssignment).where(
                RoleAssignment.id == assignment_id,
                RoleAssignment.tenant_id == organization.id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    await db.delete(assignment)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects", response_model=list[ProjectSummaryResponse])
async def list_projects(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectSummaryResponse]:
    _require_scope(principal, "projects.read", "organizations.read")
    organization = await _active_organization(db, principal)
    projects = (
        await db.execute(
            select(Project).where(Project.organization_id == organization.id).order_by(Project.is_default.desc(), Project.created_at.asc())
        )
    ).scalars().all()
    return [
        ProjectSummaryResponse(
            id=str(project.id),
            organization_id=str(project.organization_id),
            name=project.name,
            slug=project.slug,
            description=project.description,
            status=project.status.value if hasattr(project.status, "value") else str(project.status),
            is_default=bool(project.is_default),
            created_at=project.created_at,
            member_count=await _project_member_count(db, organization.id, project.id),
        )
        for project in projects
    ]


@router.get("/projects/{project_slug}", response_model=ProjectSummaryResponse)
async def get_project(
    project_slug: str,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ProjectSummaryResponse:
    _require_scope(principal, "projects.read", "organizations.read")
    organization = await _active_organization(db, principal)
    project = await _project_or_404(db, organization.id, project_slug)
    return ProjectSummaryResponse(
        id=str(project.id),
        organization_id=str(project.organization_id),
        name=project.name,
        slug=project.slug,
        description=project.description,
        status=project.status.value if hasattr(project.status, "value") else str(project.status),
        is_default=bool(project.is_default),
        created_at=project.created_at,
        member_count=await _project_member_count(db, organization.id, project.id),
    )


@router.patch("/projects/{project_slug}", response_model=ProjectSummaryResponse)
async def update_project(
    project_slug: str,
    payload: UpdateProjectRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ProjectSummaryResponse:
    _require_scope(principal, "projects.write")
    organization = await _active_organization(db, principal)
    project = await _project_or_404(db, organization.id, project_slug)
    if "name" in payload.model_fields_set and payload.name is not None:
        project.name = payload.name
    if "slug" in payload.model_fields_set and payload.slug is not None:
        duplicate = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization.id,
                    Project.slug == payload.slug,
                    Project.id != project.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="Project slug already exists in organization")
        project.slug = payload.slug
    if "description" in payload.model_fields_set:
        project.description = payload.description
    if "status" in payload.model_fields_set and payload.status is not None:
        project.status = payload.status
    await db.commit()
    await db.refresh(project)
    return await get_project(project.slug, principal=principal, db=db)


@router.get("/projects/{project_slug}/members", response_model=list[MemberResponse])
async def list_project_members(
    project_slug: str,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    _require_scope(principal, "projects.read", "roles.read")
    organization = await _active_organization(db, principal)
    project = await _project_or_404(db, organization.id, project_slug)
    rows = (
        await db.execute(
            select(RoleAssignment, User, OrgMembership, OrgUnit)
            .join(User, User.id == RoleAssignment.user_id)
            .outerjoin(
                OrgMembership,
                and_(OrgMembership.user_id == User.id, OrgMembership.tenant_id == organization.id),
            )
            .outerjoin(OrgUnit, OrgUnit.id == OrgMembership.org_unit_id)
            .where(
                RoleAssignment.tenant_id == organization.id,
                RoleAssignment.scope_type == "project",
                RoleAssignment.scope_id == project.id,
            )
            .order_by(User.email.asc())
        )
    ).all()
    seen: set[str] = set()
    members: list[MemberResponse] = []
    for _, user, membership, org_unit in rows:
        if str(user.id) in seen:
            continue
        seen.add(str(user.id))
        members.append(
            MemberResponse(
                membership_id=str(membership.id) if membership else "",
                user_id=str(user.id),
                email=user.email,
                full_name=user.full_name,
                avatar=user.avatar,
                organization_role=(
                    membership.role.value if membership and hasattr(membership.role, "value") else str(membership.role) if membership else "member"
                ),
                org_unit_id=str(org_unit.id) if org_unit else "",
                org_unit_name=org_unit.name if org_unit else "",
                joined_at=membership.joined_at if membership else project.created_at,
            )
        )
    return members


@router.get("/api-keys", response_model=list[SettingsApiKeyResponse])
async def list_api_keys(
    owner_scope: str = Query(...),
    project_slug: str | None = Query(None),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[SettingsApiKeyResponse]:
    _require_scope(principal, "api_keys.read")
    organization = await _active_organization(db, principal)
    if owner_scope == "organization":
        rows = await TenantAPIKeyService(db).list_api_keys(tenant_id=organization.id)
        return [_serialize_api_key_row(row, owner_scope="organization", owner_scope_id=organization.id) for row in rows]
    if owner_scope == "project":
        if not project_slug:
            raise HTTPException(status_code=400, detail="project_slug is required for project API keys")
        project = await _project_or_404(db, organization.id, project_slug)
        rows = await ProjectAPIKeyService(db).list_api_keys(tenant_id=organization.id, project_id=project.id)
        return [_serialize_api_key_row(row, owner_scope="project", owner_scope_id=project.id) for row in rows]
    raise HTTPException(status_code=400, detail="owner_scope must be 'organization' or 'project'")


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: CreateSettingsApiKeyRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_scope(principal, "api_keys.write")
    organization = await _active_organization(db, principal)
    created_by = UUID(str(principal["user_id"])) if principal.get("user_id") else None
    if payload.owner_scope == "organization":
        api_key, token = await TenantAPIKeyService(db).create_api_key(
            tenant_id=organization.id,
            name=payload.name,
            scopes=payload.scopes,
            created_by=created_by,
        )
        await db.commit()
        return {
            "api_key": _serialize_api_key_row(api_key, owner_scope="organization", owner_scope_id=organization.id),
            "token": token,
            "token_type": "bearer",
        }
    if payload.owner_scope == "project":
        if not payload.project_slug:
            raise HTTPException(status_code=400, detail="project_slug is required for project API keys")
        project = await _project_or_404(db, organization.id, payload.project_slug)
        api_key, token = await ProjectAPIKeyService(db).create_api_key(
            tenant_id=organization.id,
            project_id=project.id,
            name=payload.name,
            scopes=payload.scopes,
            created_by=created_by,
        )
        await db.commit()
        return {
            "api_key": _serialize_api_key_row(api_key, owner_scope="project", owner_scope_id=project.id),
            "token": token,
            "token_type": "bearer",
        }
    raise HTTPException(status_code=400, detail="owner_scope must be 'organization' or 'project'")


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: UUID,
    owner_scope: str = Query(...),
    project_slug: str | None = Query(None),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_scope(principal, "api_keys.write")
    organization = await _active_organization(db, principal)
    if owner_scope == "organization":
        try:
            api_key = await TenantAPIKeyService(db).revoke_api_key(tenant_id=organization.id, key_id=key_id)
        except TenantAPIKeyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await db.commit()
        return {"api_key": _serialize_api_key_row(api_key, owner_scope="organization", owner_scope_id=organization.id)}
    if owner_scope == "project":
        if not project_slug:
            raise HTTPException(status_code=400, detail="project_slug is required for project API keys")
        project = await _project_or_404(db, organization.id, project_slug)
        try:
            api_key = await ProjectAPIKeyService(db).revoke_api_key(
                tenant_id=organization.id,
                project_id=project.id,
                key_id=key_id,
            )
        except ProjectAPIKeyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await db.commit()
        return {"api_key": _serialize_api_key_row(api_key, owner_scope="project", owner_scope_id=project.id)}
    raise HTTPException(status_code=400, detail="owner_scope must be 'organization' or 'project'")


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    owner_scope: str = Query(...),
    project_slug: str | None = Query(None),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_scope(principal, "api_keys.write")
    organization = await _active_organization(db, principal)
    if owner_scope == "organization":
        try:
            await TenantAPIKeyService(db).delete_api_key(tenant_id=organization.id, key_id=key_id)
        except TenantAPIKeyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if owner_scope == "project":
        if not project_slug:
            raise HTTPException(status_code=400, detail="project_slug is required for project API keys")
        project = await _project_or_404(db, organization.id, project_slug)
        try:
            await ProjectAPIKeyService(db).delete_api_key(
                tenant_id=organization.id,
                project_id=project.id,
                key_id=key_id,
            )
        except ProjectAPIKeyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=400, detail="owner_scope must be 'organization' or 'project'")


@router.get("/limits/organization", response_model=LimitResponse)
async def get_organization_limits(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> LimitResponse:
    _require_scope(principal, "organizations.read", "organizations.write")
    organization = await _active_organization(db, principal)
    policy = await _tenant_usage_quota_policy(db, organization.id)
    limit_tokens = int(policy.limit_tokens) if policy is not None else None
    return LimitResponse(
        owner_scope="organization",
        owner_scope_id=str(organization.id),
        monthly_token_limit=limit_tokens,
        inherited_monthly_token_limit=None,
        effective_monthly_token_limit=limit_tokens,
    )


@router.patch("/limits/organization", response_model=LimitResponse)
async def update_organization_limits(
    payload: UpdateLimitRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> LimitResponse:
    _require_scope(principal, "organizations.write")
    organization = await _active_organization(db, principal)
    policy = await _tenant_usage_quota_policy(db, organization.id)
    if payload.monthly_token_limit is None:
        if policy is not None:
            policy.is_active = False
    else:
        if payload.monthly_token_limit <= 0:
            raise HTTPException(status_code=400, detail="monthly_token_limit must be positive")
        if policy is None:
            policy = UsageQuotaPolicy(
                tenant_id=organization.id,
                user_id=None,
                scope_type=UsageQuotaScopeType.tenant,
                limit_tokens=payload.monthly_token_limit,
                timezone="UTC",
                is_active=True,
            )
            db.add(policy)
        else:
            policy.limit_tokens = payload.monthly_token_limit
            policy.is_active = True
    await db.commit()
    return await get_organization_limits(principal=principal, db=db)


@router.get("/limits/projects/{project_slug}", response_model=LimitResponse)
async def get_project_limits(
    project_slug: str,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> LimitResponse:
    _require_scope(principal, "projects.read", "organizations.read")
    organization = await _active_organization(db, principal)
    project = await _project_or_404(db, organization.id, project_slug)
    policy = await _tenant_usage_quota_policy(db, organization.id)
    inherited = int(policy.limit_tokens) if policy is not None else None
    monthly_token_limit = (project.settings or {}).get("monthly_token_limit")
    effective = monthly_token_limit if monthly_token_limit is not None else inherited
    return LimitResponse(
        owner_scope="project",
        owner_scope_id=str(project.id),
        monthly_token_limit=monthly_token_limit,
        inherited_monthly_token_limit=inherited,
        effective_monthly_token_limit=effective,
    )


@router.patch("/limits/projects/{project_slug}", response_model=LimitResponse)
async def update_project_limits(
    project_slug: str,
    payload: UpdateLimitRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> LimitResponse:
    _require_scope(principal, "projects.write")
    organization = await _active_organization(db, principal)
    project = await _project_or_404(db, organization.id, project_slug)
    settings = dict(project.settings or {})
    if payload.monthly_token_limit is not None and payload.monthly_token_limit <= 0:
        raise HTTPException(status_code=400, detail="monthly_token_limit must be positive")
    settings["monthly_token_limit"] = payload.monthly_token_limit
    project.settings = settings
    await db.commit()
    await db.refresh(project)
    return await get_project_limits(project_slug=project.slug, principal=principal, db=db)


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    actor_email: str | None = None,
    action: Action | None = None,
    resource_type: ResourceType | None = None,
    resource_id: str | None = None,
    result: AuditResult | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    _require_scope(principal, "audit.read")
    organization = await _active_organization(db, principal)
    conditions: list[Any] = [AuditLog.tenant_id == organization.id]
    if actor_email:
        conditions.append(AuditLog.actor_email.ilike(f"%{actor_email}%"))
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLog.resource_id == resource_id)
    if result:
        conditions.append(AuditLog.result == result)

    rows = (
        await db.execute(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return [
        AuditLogResponse(
            id=str(row.id),
            actor_email=row.actor_email,
            action=row.action.value if hasattr(row.action, "value") else str(row.action),
            resource_type=row.resource_type.value if hasattr(row.resource_type, "value") else str(row.resource_type),
            resource_id=row.resource_id,
            resource_name=row.resource_name,
            result=row.result.value if hasattr(row.result, "value") else str(row.result),
            failure_reason=row.failure_reason,
            timestamp=row.timestamp,
            duration_ms=row.duration_ms,
        )
        for row in rows
    ]


@router.get("/audit-logs/count")
async def count_audit_logs(
    actor_email: str | None = None,
    action: Action | None = None,
    resource_type: ResourceType | None = None,
    result: AuditResult | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    _require_scope(principal, "audit.read")
    organization = await _active_organization(db, principal)
    conditions: list[Any] = [AuditLog.tenant_id == organization.id]
    if actor_email:
        conditions.append(AuditLog.actor_email.ilike(f"%{actor_email}%"))
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if result:
        conditions.append(AuditLog.result == result)
    count = (
        await db.execute(select(func.count(AuditLog.id)).where(*conditions))
    ).scalar()
    return {"count": int(count or 0)}


@router.get("/audit-logs/{log_id}", response_model=AuditLogDetailResponse)
async def get_audit_log(
    log_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> AuditLogDetailResponse:
    _require_scope(principal, "audit.read")
    organization = await _active_organization(db, principal)
    row = (
        await db.execute(select(AuditLog).where(AuditLog.id == log_id, AuditLog.tenant_id == organization.id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return AuditLogDetailResponse(
        id=str(row.id),
        actor_email=row.actor_email,
        action=row.action.value if hasattr(row.action, "value") else str(row.action),
        resource_type=row.resource_type.value if hasattr(row.resource_type, "value") else str(row.resource_type),
        resource_id=row.resource_id,
        resource_name=row.resource_name,
        result=row.result.value if hasattr(row.result, "value") else str(row.result),
        failure_reason=row.failure_reason,
        timestamp=row.timestamp,
        duration_ms=row.duration_ms,
        before_state=row.before_state,
        after_state=row.after_state,
        request_params=row.request_params,
    )
