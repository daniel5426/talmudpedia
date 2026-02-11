import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.identity import OrgMembership, OrgRole, User
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppStatus
from app.db.postgres.session import get_db


router = APIRouter(prefix="/admin/apps", tags=["published-apps-admin"])

APP_SLUG_PATTERN = re.compile(r"^[a-z0-9-]{3,64}$")


class PublishedAppResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    name: str
    slug: str
    status: str
    auth_enabled: bool
    auth_providers: List[str]
    published_url: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class CreatePublishedAppRequest(BaseModel):
    name: str
    slug: str
    agent_id: UUID
    auth_enabled: bool = True
    auth_providers: List[str] = Field(default_factory=lambda: ["password"])


class UpdatePublishedAppRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    agent_id: Optional[UUID] = None
    auth_enabled: Optional[bool] = None
    auth_providers: Optional[List[str]] = None
    status: Optional[str] = None


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost")


def _build_published_url(slug: str) -> str:
    return f"https://{slug}.{_apps_base_domain()}"


def _validate_providers(providers: List[str]) -> List[str]:
    normalized = [p.strip().lower() for p in providers if p and p.strip()]
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one auth provider must be configured")
    allowed = {"password", "google"}
    invalid = [p for p in normalized if p not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported auth providers: {', '.join(invalid)}")
    return sorted(set(normalized))


def _app_to_response(app: PublishedApp) -> PublishedAppResponse:
    return PublishedAppResponse(
        id=str(app.id),
        tenant_id=str(app.tenant_id),
        agent_id=str(app.agent_id),
        name=app.name,
        slug=app.slug,
        status=app.status.value if hasattr(app.status, "value") else str(app.status),
        auth_enabled=bool(app.auth_enabled),
        auth_providers=list(app.auth_providers or []),
        published_url=app.published_url,
        created_by=str(app.created_by) if app.created_by else None,
        created_at=app.created_at,
        updated_at=app.updated_at,
        published_at=app.published_at,
    )


async def _resolve_tenant_admin_context(
    request: Request,
    principal: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    if principal.get("type") == "workload":
        tenant_id = principal.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        return {
            "tenant_id": UUID(str(tenant_id)),
            "user": None,
            "is_system_admin": False,
            "org_role": None,
        }

    user = principal.get("user")
    if user is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    header_tenant = request.headers.get("X-Tenant-ID")
    if header_tenant:
        try:
            tenant_uuid = UUID(str(header_tenant))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID header")
        membership_result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.tenant_id == tenant_uuid,
            ).limit(1)
        )
        membership = membership_result.scalar_one_or_none()
        if membership is None and user.role != "admin":
            raise HTTPException(status_code=403, detail="Not a member of the requested tenant")
        org_role = (
            str(getattr(membership.role, "value", membership.role))
            if membership
            else OrgRole.owner.value
        )
        return {
            "tenant_id": tenant_uuid,
            "user": user,
            "is_system_admin": user.role == "admin",
            "org_role": org_role,
        }

    membership_result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user.id).limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is not None:
        return {
            "tenant_id": membership.tenant_id,
            "user": user,
            "is_system_admin": user.role == "admin",
            "org_role": str(getattr(membership.role, "value", membership.role)),
        }

    tenant_id = principal.get("tenant_id")
    if user.role == "admin" and tenant_id:
        return {
            "tenant_id": UUID(str(tenant_id)),
            "user": user,
            "is_system_admin": True,
            "org_role": OrgRole.owner.value,
        }
    raise HTTPException(status_code=403, detail="Tenant context required")


def _assert_can_manage_apps(ctx: Dict[str, Any]) -> None:
    if ctx.get("is_system_admin"):
        return
    role = str(ctx.get("org_role") or "")
    if role not in {OrgRole.owner.value, OrgRole.admin.value}:
        raise HTTPException(status_code=403, detail="Insufficient permissions for apps management")


async def _validate_agent(db: AsyncSession, tenant_id: UUID, agent_id: UUID) -> Agent:
    result = await db.execute(
        select(Agent).where(and_(Agent.id == agent_id, Agent.tenant_id == tenant_id)).limit(1)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != AgentStatus.published:
        raise HTTPException(status_code=400, detail="Only published agents can be attached to apps")
    return agent


@router.get("", response_model=List[PublishedAppResponse])
async def list_published_apps(
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp)
        .where(PublishedApp.tenant_id == ctx["tenant_id"])
        .order_by(PublishedApp.updated_at.desc())
    )
    return [_app_to_response(app) for app in result.scalars().all()]


@router.post("", response_model=PublishedAppResponse)
async def create_published_app(
    payload: CreatePublishedAppRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    slug = payload.slug.strip().lower()
    if not APP_SLUG_PATTERN.match(slug):
        raise HTTPException(status_code=400, detail="Slug must be lowercase, 3-64 chars, and contain only letters, numbers, hyphens")

    providers = _validate_providers(payload.auth_providers)
    await _validate_agent(db, ctx["tenant_id"], payload.agent_id)

    app = PublishedApp(
        tenant_id=ctx["tenant_id"],
        agent_id=payload.agent_id,
        name=payload.name.strip(),
        slug=slug,
        auth_enabled=payload.auth_enabled,
        auth_providers=providers,
        created_by=ctx["user"].id if ctx["user"] else None,
        status=PublishedAppStatus.draft,
    )
    db.add(app)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Published app slug or name already exists")
    await db.refresh(app)
    return _app_to_response(app)


@router.get("/{app_id}", response_model=PublishedAppResponse)
async def get_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == ctx["tenant_id"])
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    return _app_to_response(app)


@router.patch("/{app_id}", response_model=PublishedAppResponse)
async def update_published_app(
    app_id: UUID,
    payload: UpdatePublishedAppRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == ctx["tenant_id"])
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")

    if payload.name is not None:
        app.name = payload.name.strip()
    if payload.slug is not None:
        next_slug = payload.slug.strip().lower()
        if not APP_SLUG_PATTERN.match(next_slug):
            raise HTTPException(status_code=400, detail="Slug must be lowercase, 3-64 chars, and contain only letters, numbers, hyphens")
        app.slug = next_slug
        if app.status == PublishedAppStatus.published:
            app.published_url = _build_published_url(next_slug)
    if payload.agent_id is not None:
        await _validate_agent(db, ctx["tenant_id"], payload.agent_id)
        app.agent_id = payload.agent_id
    if payload.auth_enabled is not None:
        app.auth_enabled = payload.auth_enabled
    if payload.auth_providers is not None:
        app.auth_providers = _validate_providers(payload.auth_providers)
    if payload.status is not None:
        try:
            app.status = PublishedAppStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Published app slug or name already exists")
    await db.refresh(app)
    return _app_to_response(app)


@router.post("/{app_id}/publish", response_model=PublishedAppResponse)
async def publish_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == ctx["tenant_id"])
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")

    await _validate_agent(db, ctx["tenant_id"], app.agent_id)

    app.status = PublishedAppStatus.published
    app.published_at = datetime.now(timezone.utc)
    app.published_url = _build_published_url(app.slug)
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.post("/{app_id}/unpublish", response_model=PublishedAppResponse)
async def unpublish_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == ctx["tenant_id"])
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    app.status = PublishedAppStatus.draft
    app.published_url = None
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.delete("/{app_id}")
async def delete_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == ctx["tenant_id"])
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    await db.delete(app)
    await db.commit()
    return {"status": "deleted", "id": str(app_id)}


@router.get("/{app_id}/runtime-preview")
async def runtime_preview(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == ctx["tenant_id"])
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    return {
        "app_id": str(app.id),
        "slug": app.slug,
        "status": app.status.value if hasattr(app.status, "value") else str(app.status),
        "runtime_url": app.published_url or _build_published_url(app.slug),
    }
