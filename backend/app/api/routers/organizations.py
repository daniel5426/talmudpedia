from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import OrgMembership, OrgRole, Tenant, User
from app.db.postgres.models.workspace import Project, ProjectStatus
from app.db.postgres.session import get_db
from app.services.auth_context_service import (
    list_organization_projects,
    list_user_organizations,
    serialize_organization_summary,
    serialize_project_summary,
    serialize_user_summary,
)
from app.services.organization_bootstrap_service import OrganizationBootstrapService
from app.services.workos_auth_service import WorkOSAuthService

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None


class CreateProjectRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
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


async def _get_org_or_404(db: AsyncSession, organization_slug: str) -> Tenant:
    organization = (await db.execute(select(Tenant).where(Tenant.slug == organization_slug))).scalar_one_or_none()
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
    existing = (await db.execute(select(Tenant).where(Tenant.slug == payload.slug))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Organization slug already exists")
    if not current_user.workos_user_id:
        raise HTTPException(status_code=400, detail="Current user is not linked to WorkOS")
    bundle = await WorkOSAuthService(db).create_organization_for_user(
        local_user=current_user,
        name=payload.name,
        slug=payload.slug,
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


@router.get("/{organization_slug}")
async def get_organization(
    organization_slug: str,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    organization = await _get_org_or_404(db, organization_slug)
    if str(organization.id) != str(principal.get("organization_id")) and "*" not in set(principal.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Organization is outside active session context")
    return serialize_organization_summary(organization)


@router.patch("/{organization_slug}")
async def update_organization(
    organization_slug: str,
    payload: UpdateOrganizationRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organizations.write")
    organization = await _get_org_or_404(db, organization_slug)
    if payload.name is not None:
        organization.name = payload.name
    if payload.slug is not None:
        organization.slug = payload.slug
    await db.commit()
    return serialize_organization_summary(organization)


@router.get("/{organization_slug}/projects")
async def list_projects(
    organization_slug: str,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "projects.read", "organizations.read")
    organization = await _get_org_or_404(db, organization_slug)
    projects = await list_organization_projects(db=db, organization_id=organization.id)
    return [serialize_project_summary(item) for item in projects]


@router.post("/{organization_slug}/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    organization_slug: str,
    payload: CreateProjectRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "projects.write")
    organization = await _get_org_or_404(db, organization_slug)
    existing = (
        await db.execute(
            select(Project).where(
                and_(Project.organization_id == organization.id, Project.slug == payload.slug)
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Project slug already exists in organization")
    actor_user_id = UUID(str(principal["user_id"])) if principal.get("user_id") else None
    project = await OrganizationBootstrapService(db).create_project(
        organization=organization,
        created_by=actor_user_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        owner_user_id=actor_user_id,
    )
    await db.commit()
    return serialize_project_summary(project)


@router.patch("/{organization_slug}/projects/{project_slug}")
async def update_project(
    organization_slug: str,
    project_slug: str,
    payload: UpdateProjectRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "projects.write")
    organization = await _get_org_or_404(db, organization_slug)
    project = (
        await db.execute(
            select(Project).where(
                and_(Project.organization_id == organization.id, Project.slug == project_slug)
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.name is not None:
        project.name = payload.name
    if payload.slug is not None:
        project.slug = payload.slug
    if payload.description is not None:
        project.description = payload.description
    if payload.status is not None:
        project.status = payload.status
    await db.commit()
    return serialize_project_summary(project)


@router.get("/{organization_slug}/members")
async def list_members(
    organization_slug: str,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_members.read")
    organization = await _get_org_or_404(db, organization_slug)
    memberships = (
        await db.execute(select(OrgMembership).where(OrgMembership.tenant_id == organization.id))
    ).scalars().all()
    users = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_([item.user_id for item in memberships] or [UUID(int=0)])))
        ).scalars().all()
    }
    return [
        {
            "membership_id": str(item.id),
            "user": serialize_user_summary(users[item.user_id]),
            "organization_role": item.role.value if hasattr(item.role, "value") else str(item.role),
            "joined_at": item.joined_at,
        }
        for item in memberships
        if item.user_id in users
    ]


@router.get("/{organization_slug}/invites")
async def list_invites(
    organization_slug: str,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.read")
    organization = await _get_org_or_404(db, organization_slug)
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


@router.post("/{organization_slug}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    organization_slug: str,
    payload: CreateInviteRequest,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.write")
    organization = await _get_org_or_404(db, organization_slug)
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


@router.delete("/{organization_slug}/invites/{invite_id}")
async def revoke_invite(
    organization_slug: str,
    invite_id: str,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.delete")
    organization = await _get_org_or_404(db, organization_slug)
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")
    WorkOSAuthService(db).client.user_management.revoke_invitation(invite_id)
    return {"status": "deleted"}


@router.post("/{organization_slug}/workos/admin-portal-link")
async def create_workos_admin_portal_link(
    organization_slug: str,
    payload: WorkOSAdminPortalLinkRequest,
    principal: dict = Depends(require_scopes("organizations.write")),
    db: AsyncSession = Depends(get_db),
):
    del principal
    organization = await _get_org_or_404(db, organization_slug)
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
