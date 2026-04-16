from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.routers.auth import get_current_user, _session_cookie_samesite
from app.core.security import get_password_hash
from app.db.postgres.models.identity import OrgInvite, OrgMembership, OrgRole, Tenant, User
from app.db.postgres.models.workspace import Project, ProjectStatus
from app.db.postgres.session import get_db
from app.services.auth_context_service import (
    list_organization_projects,
    list_user_organizations,
    serialize_organization_summary,
    serialize_project_summary,
    serialize_user_summary,
)
from app.services.browser_session_service import BrowserSessionService, SESSION_COOKIE_NAME
from app.services.organization_bootstrap_service import OrganizationBootstrapService

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


class AcceptInviteRequest(BaseModel):
    token: str
    password: Optional[str] = None
    full_name: Optional[str] = None


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(Tenant).where(Tenant.slug == payload.slug))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Organization slug already exists")
    organization, project = await OrganizationBootstrapService(db).create_organization_with_default_project(
        owner=current_user,
        name=payload.name,
        slug=payload.slug,
    )
    await db.commit()
    return {
        "organization": serialize_organization_summary(organization),
        "default_project": serialize_project_summary(project),
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
    invites = (
        await db.execute(select(OrgInvite).where(OrgInvite.tenant_id == organization.id).order_by(OrgInvite.created_at.desc()))
    ).scalars().all()
    return [
        {
            "id": str(invite.id),
            "email": invite.email,
            "project_ids": [str(item) for item in list(invite.project_ids or [])],
            "accepted_at": invite.accepted_at,
            "created_at": invite.created_at,
            "expires_at": invite.expires_at,
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
    invite = OrgInvite(
        email=payload.email,
        tenant_id=organization.id,
        role=OrgRole.member,
        project_ids=[str(item) for item in payload.project_ids],
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=UUID(str(principal["user_id"])),
    )
    db.add(invite)
    await db.commit()
    return {
        "id": str(invite.id),
        "token": invite.token,
        "email": invite.email,
        "project_ids": invite.project_ids,
        "expires_at": invite.expires_at,
    }


@router.delete("/{organization_slug}/invites/{invite_id}")
async def revoke_invite(
    organization_slug: str,
    invite_id: UUID,
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _require_org_scope(principal, "organization_invites.delete")
    organization = await _get_org_or_404(db, organization_slug)
    invite = (
        await db.execute(
            select(OrgInvite).where(and_(OrgInvite.id == invite_id, OrgInvite.tenant_id == organization.id))
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    await db.delete(invite)
    await db.commit()
    return {"status": "deleted"}


@router.post("/invites/accept")
async def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    invite = (
        await db.execute(select(OrgInvite).where(OrgInvite.token == payload.token).limit(1))
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    expiry = invite.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite has expired")

    existing_user = (await db.execute(select(User).where(User.email == invite.email))).scalar_one_or_none()
    current_user: User | None = None
    try:
        current_user = await get_current_user(request=request, token=None, db=db)
    except HTTPException:
        current_user = None

    if current_user is not None and current_user.email != invite.email:
        raise HTTPException(status_code=403, detail="Invite email does not match the current account")

    user = current_user or existing_user
    if user is None:
        if not payload.password:
            raise HTTPException(status_code=400, detail="Password is required to create a new account from invite")
        user = User(
            email=invite.email,
            hashed_password=get_password_hash(payload.password),
            full_name=payload.full_name,
            role="user",
            avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={payload.full_name or invite.email}",
        )
        db.add(user)
        await db.flush()

    organization, assigned_project = await OrganizationBootstrapService(db).accept_invite(invite=invite, user=user)
    session_project = assigned_project
    if session_project is None:
        projects = await list_organization_projects(db=db, organization_id=organization.id)
        session_project = projects[0] if projects else None
    if session_project is None:
        raise HTTPException(status_code=400, detail="Organization has no active project")

    browser_session, raw_token = await BrowserSessionService(db).create_session(
        user=user,
        organization=organization,
        project=session_project,
    )
    del browser_session
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite=_session_cookie_samesite(),
        path="/",
    )
    await db.commit()
    return {
        "organization": serialize_organization_summary(organization),
        "project": serialize_project_summary(session_project),
        "user": serialize_user_summary(user),
    }
