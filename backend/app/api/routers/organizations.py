from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import OrgMembership, Organization, User
from app.db.postgres.models.rbac import Role, RoleAssignment
from app.db.postgres.models.workspace import Project, ProjectStatus
from app.db.postgres.session import get_db
from app.services.auth_context_service import (
    list_organization_projects,
    list_user_organizations,
    resolve_effective_scopes,
    serialize_organization_summary,
    serialize_project_summary,
    serialize_user_summary,
)
from app.services.organization_bootstrap_service import OrganizationBootstrapService
from app.services.workos_auth_service import WorkOSAuthService

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class CreateOrganizationRequest(BaseModel):
    name: str


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = None


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class CreateInviteRequest(BaseModel):
    email: EmailStr
    project_ids: list[str] = []


class WorkOSAdminPortalLinkRequest(BaseModel):
    intent: str = "sso"
    return_url: Optional[str] = None


def _require_org_scope(principal: dict, *scopes: str) -> None:
    current_scopes = set(principal.get("scopes") or [])
    if "*" in current_scopes:
        return
    for scope in scopes:
        if scope in current_scopes:
            return
    raise HTTPException(status_code=403, detail=f"Missing required scope: {' or '.join(scopes)}")


async def _get_org_or_404(db: AsyncSession, organization_id: UUID) -> Organization:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.get("")
async def list_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    organizations = await list_user_organizations(db=db, user_id=current_user.id)
    return [serialize_organization_summary(item) for item in organizations]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: CreateOrganizationRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.workos_user_id:
        raise HTTPException(status_code=400, detail="Current user is not linked to WorkOS")
    bundle = await WorkOSAuthService(db).create_organization_for_user(
        local_user=current_user,
        name=payload.name,
        request=request,
        response=response,
    )
    if isinstance(bundle, dict):
        return bundle
    await db.commit()
    return {
        "organization": serialize_organization_summary(bundle.organization),
        "default_project": serialize_project_summary(bundle.project),
    }


@router.get("/{organization_id}")
async def get_organization(
    organization_id: UUID,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    organization = await _get_org_or_404(db, organization_id)
    if str(organization.id) != str(principal.get("organization_id")) and "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Organization is outside active session context")
    return serialize_organization_summary(organization)


@router.patch("/{organization_id}")
async def update_organization(
    organization_id: UUID,
    payload: UpdateOrganizationRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organizations.write")
    organization = await _get_org_or_404(db, organization_id)
    if payload.name is not None:
        organization.name = payload.name
    await db.commit()
    return serialize_organization_summary(organization)


@router.get("/{organization_id}/projects")
async def list_projects(
    organization_id: UUID,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "projects.read", "organizations.read")
    organization = await _get_org_or_404(db, organization_id)
    projects = await list_organization_projects(db=db, organization_id=organization.id)
    return [serialize_project_summary(item) for item in projects]


@router.post("/{organization_id}/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    organization_id: UUID,
    payload: CreateProjectRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "projects.write")
    organization = await _get_org_or_404(db, organization_id)
    actor_user_id = UUID(str(principal["user_id"])) if principal.get("user_id") else None
    project = await OrganizationBootstrapService(db).create_project(
        organization=organization,
        created_by=actor_user_id,
        name=payload.name,
        description=payload.description,
        owner_user_id=actor_user_id,
    )
    await db.commit()
    return serialize_project_summary(project)


@router.patch("/{organization_id}/projects/{project_id}")
async def update_project(
    organization_id: UUID,
    project_id: UUID,
    payload: UpdateProjectRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    organization = await _get_org_or_404(db, organization_id)
    project = (
        await db.execute(
            select(Project).where(
                and_(Project.organization_id == organization.id, Project.id == project_id)
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    current_scopes = set(principal.get("scopes") or [])
    if "*" not in current_scopes:
        current_user = principal.get("user")
        if current_user is None:
            raise HTTPException(status_code=403, detail="Missing required scope: project_settings.write")
        effective_scopes = await resolve_effective_scopes(
            db=db,
            user=current_user,
            organization_id=organization.id,
            project_id=project.id,
        )
        if "project_settings.write" not in set(effective_scopes):
            raise HTTPException(status_code=403, detail="Missing required scope: project_settings.write")
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.status is not None:
        project.status = payload.status
    await db.commit()
    return serialize_project_summary(project)


@router.get("/{organization_id}/members")
async def list_members(
    organization_id: UUID,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_members.read")
    organization = await _get_org_or_404(db, organization_id)
    memberships = (
        await db.execute(
            select(OrgMembership).where(
                OrgMembership.organization_id == organization.id,
                OrgMembership.status == "active",
            )
        )
    ).scalars().all()
    users = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_([item.user_id for item in memberships] or [UUID(int=0)])))
        ).scalars().all()
    }
    org_role_rows = await db.execute(
        select(RoleAssignment.user_id, Role.name)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            RoleAssignment.organization_id == organization.id,
            RoleAssignment.project_id.is_(None),
            Role.family == "organization",
            RoleAssignment.user_id.in_([item.user_id for item in memberships] or [UUID(int=0)]),
        )
    )
    org_role_names = {user_id: role_name for user_id, role_name in org_role_rows.all()}
    return [
        {
            "membership_id": str(item.id),
            "user": serialize_user_summary(users[item.user_id]),
            "organization_role": org_role_names.get(item.user_id, "Unassigned"),
            "joined_at": item.joined_at,
        }
        for item in memberships
        if item.user_id in users
    ]


@router.get("/{organization_id}/invites")
async def list_invites(
    organization_id: UUID,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.read")
    organization = await _get_org_or_404(db, organization_id)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")
    service = WorkOSAuthService(db)
    invites = service.client.user_management.list_invitations(
        organization_id=organization.workos_organization_id,
    )
    return [
        {
            "id": str(getattr(invite, "id", "")),
            "email": getattr(invite, "email", None),
            "project_ids": [],
            "accepted_at": getattr(invite, "accepted_at", None) or getattr(invite, "acceptedAt", None),
            "created_at": getattr(invite, "created_at", None) or getattr(invite, "createdAt", None),
            "expires_at": getattr(invite, "expires_at", None) or getattr(invite, "expiresAt", None),
        }
        for invite in invites
    ]


@router.post("/{organization_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    organization_id: UUID,
    payload: CreateInviteRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.write")
    organization = await _get_org_or_404(db, organization_id)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")
    service = WorkOSAuthService(db)
    current_user = await db.get(User, UUID(str(principal["user_id"])))
    invite = service.client.user_management.send_invitation(
        email=str(payload.email),
        organization_id=organization.workos_organization_id,
        inviter_user_id=current_user.workos_user_id if current_user and current_user.workos_user_id else None,
    )
    return {
        "id": str(getattr(invite, "id", "")),
        "token": getattr(invite, "token", None),
        "email": getattr(invite, "email", None),
        "project_ids": [],
        "expires_at": getattr(invite, "expires_at", None) or getattr(invite, "expiresAt", None),
    }


@router.delete("/{organization_id}/invites/{invite_id}")
async def revoke_invite(
    organization_id: UUID,
    invite_id: str,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.delete")
    organization = await _get_org_or_404(db, organization_id)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")
    WorkOSAuthService(db).client.user_management.revoke_invitation(invite_id)
    return {"status": "deleted"}


@router.post("/{organization_id}/workos/admin-portal-link")
async def create_workos_admin_portal_link(
    organization_id: UUID,
    payload: WorkOSAdminPortalLinkRequest,
    principal: dict = Depends(require_scopes("organizations.write")),
    db: AsyncSession = Depends(get_db),
):
    del principal
    organization = await _get_org_or_404(db, organization_id)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")
    service = WorkOSAuthService(db)
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="WorkOS auth is not configured")
    link = service.client.portal.generate_link(
        organization=organization.workos_organization_id,
        intent=payload.intent,
        return_url=payload.return_url,
    )
    return {"link": getattr(link, "link", None) or link["link"]}
