from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from .routers.auth import get_current_user
from app.db.postgres.models.identity import Tenant, User, OrgUnit
from app.services.tenant_api_key_service import TenantAPIKeyAuthError, TenantAPIKeyService
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppAccount,
    PublishedAppAccountStatus,
    PublishedAppSession,
)
from app.db.postgres.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select
from uuid import UUID
import jwt
from app.core.security import SECRET_KEY, ALGORITHM
from app.core.scope_registry import is_platform_admin_role
from app.core.security import decode_published_app_preview_token, decode_published_app_session_token
from app.db.postgres.models.workspace import Project
from app.services.auth_context_service import list_organization_projects, resolve_effective_scopes
from app.services.browser_session_service import SESSION_COOKIE_NAME, BrowserSessionService

class AuthContext(BaseModel):
    user: User
    tenant: Tenant
    org_unit: Optional[OrgUnit] = None
    project: Optional[Project] = None

    class Config:
        arbitrary_types_allowed = True


bearer_scheme = HTTPBearer(auto_error=False)

async def get_tenant_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    """
    Dependency to get the current tenant context.
    Matches the placeholder logic but uses Postgres effectively.
    """
    tenant_uuid: UUID | None = None
    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID header") from exc
    else:
        cookie_token = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
        if cookie_token:
            session = await BrowserSessionService(db).resolve_session(cookie_token)
            if session is not None:
                tenant_uuid = session.organization_id
    if tenant_uuid is None:
        raise HTTPException(status_code=400, detail="Active organization context is required")
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "tenant_id": str(tenant.id),
        "organization_id": str(tenant.id),
        "tenant": tenant,
        "organization": tenant,
    }

async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AuthContext:
    """
    Unified dependency for full auth context including tenant and org unit.
    """
    cookie_token = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if cookie_token:
        session = await BrowserSessionService(db).resolve_session(cookie_token)
        if session is not None:
            tenant = await db.get(Tenant, session.organization_id)
            project = await db.get(Project, session.project_id)
            if tenant is not None:
                return AuthContext(user=user, tenant=tenant, org_unit=None, project=project)
    if _is_platform_admin(user):
        tenant = (await db.execute(select(Tenant).limit(1))).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=500, detail="No organization configured")
        projects = await list_organization_projects(db=db, organization_id=tenant.id)
        return AuthContext(user=user, tenant=tenant, org_unit=None, project=projects[0] if projects else None)
    raise HTTPException(status_code=403, detail="No active organization session")


def _is_platform_admin(user: User) -> bool:
    return is_platform_admin_role(getattr(user, "role", None))


async def get_current_principal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Unified principal resolver for migrated secure endpoints.
    Supports authenticated user principals.
    """
    try:
        raw_cookie = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
        if raw_cookie:
            session = await BrowserSessionService(db).resolve_session(raw_cookie)
            if session is not None:
                user = await db.get(User, session.user_id)
                organization = await db.get(Tenant, session.organization_id)
                project = await db.get(Project, session.project_id)
                if user is not None and organization is not None and project is not None:
                    scopes = await resolve_effective_scopes(
                        db=db,
                        user=user,
                        organization_id=organization.id,
                        project_id=project.id,
                    )
                    return {
                        "type": "user",
                        "auth_mode": "browser_session",
                        "user": user,
                        "user_id": str(user.id),
                        "tenant_id": str(organization.id),
                        "organization_id": str(organization.id),
                        "organization_slug": organization.slug,
                        "project_id": str(project.id),
                        "project_slug": project.slug,
                        "scopes": sorted(scopes),
                        "auth_token": raw_cookie,
                    }

        token = credentials.credentials if credentials is not None and credentials.credentials else None
        if token is None:
            raise HTTPException(status_code=401, detail="Could not validate principal token")

        user = await get_current_user(request=request, token=token, db=db)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Organization context required")
        project_id = payload.get("project_id")
        scopes = set(str(s) for s in (payload.get("scope") or []) if str(s).strip())
        return {
            "type": "user",
            "auth_mode": "bearer_token",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "organization_id": str(tenant_id),
            "project_id": str(project_id) if project_id else None,
            "scopes": sorted(scopes),
            "auth_token": token,
        }
    except HTTPException:
        pass
    except Exception:
        pass

    raise HTTPException(status_code=401, detail="Could not validate principal token")


async def get_current_tenant_api_key_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    token = credentials.credentials if credentials is not None and credentials.credentials else None
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    service = TenantAPIKeyService(db)
    try:
        api_key = await service.authenticate_token(token)
    except TenantAPIKeyAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "type": "tenant_api_key",
        "tenant_id": str(api_key.tenant_id),
        "api_key_id": str(api_key.id),
        "key_prefix": api_key.key_prefix,
        "name": api_key.name,
        "scopes": list(api_key.scopes or []),
        "auth_token": token,
    }


def require_scopes(*required_scopes: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    async def _dep(principal: Dict[str, Any] = Depends(get_current_principal)) -> Dict[str, Any]:
        scopes = set(principal.get("scopes") or [])
        if "*" in scopes:
            return principal
        missing = [scope for scope in required_scopes if scope not in scopes]
        if missing:
            raise HTTPException(status_code=403, detail=f"Missing required scopes: {', '.join(missing)}")
        return principal

    return _dep


def require_tenant_api_key_scopes(*required_scopes: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    async def _dep(
        principal: Dict[str, Any] = Depends(get_current_tenant_api_key_principal),
    ) -> Dict[str, Any]:
        scopes = set(principal.get("scopes") or [])
        missing = [scope for scope in required_scopes if scope not in scopes]
        if missing:
            raise HTTPException(status_code=403, detail=f"Missing required scopes: {', '.join(missing)}")
        return principal

    return _dep

async def ensure_sensitive_action_approved(
    *,
    principal: Dict[str, Any],
    tenant_id: UUID | str | None,
    subject_type: str,
    subject_id: str,
    action_scope: str,
    db: AsyncSession,
) -> None:
    del principal, tenant_id, subject_type, subject_id, action_scope, db
    return None


async def get_optional_published_app_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    if credentials is None or not credentials.credentials:
        return None

    token = credentials.credentials
    try:
        payload = decode_published_app_session_token(token)
        session_id = UUID(str(payload["session_id"]))
        app_id = UUID(str(payload["app_id"]))
        app_account_id = UUID(str(payload["app_account_id"]))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid published app session token")

    result = await db.execute(
        select(PublishedAppSession).where(PublishedAppSession.id == session_id).limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=401, detail="Published app session not found")
    if str(session.published_app_id) != str(app_id) or str(session.app_account_id) != str(app_account_id):
        raise HTTPException(status_code=401, detail="Published app session mismatch")
    if session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Published app session revoked")
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Published app session expired")

    app_result = await db.execute(select(PublishedApp).where(PublishedApp.id == app_id).limit(1))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=401, detail="Published app not found")

    account_result = await db.execute(
        select(PublishedAppAccount).where(
            and_(
                PublishedAppAccount.id == app_account_id,
                PublishedAppAccount.published_app_id == app_id,
            )
        ).limit(1)
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=401, detail="Published app account not found")
    if account.status == PublishedAppAccountStatus.blocked:
        raise HTTPException(status_code=403, detail="Published app account is blocked")

    return {
        "type": "published_app_user",
        "tenant_id": str(app.tenant_id),
        "app_id": str(app.id),
        "app_slug": app.slug,
        "session_id": str(session.id),
        "app_account_id": str(account.id),
        "global_user_id": str(account.global_user_id) if account.global_user_id else None,
        "user": account,
        "provider": payload.get("provider", "password"),
        "account_status": account.status.value if hasattr(account.status, "value") else str(account.status),
        "scopes": payload.get("scope", []),
        "auth_token": token,
    }


async def get_current_published_app_principal(
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
) -> Dict[str, Any]:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


async def get_optional_published_app_preview_principal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[Dict[str, Any]]:
    token_candidates: list[str] = []
    if credentials is not None and credentials.credentials:
        bearer_token = credentials.credentials.strip()
        if bearer_token:
            token_candidates.append(bearer_token)

    query_token = (request.query_params.get("runtime_token") or "").strip()
    if query_token and query_token not in token_candidates:
        token_candidates.append(query_token)

    cookie_names = (
        "published_app_public_preview_token",
        "published_app_preview_token",
    )
    for cookie_name in cookie_names:
        cookie_token = (request.cookies.get(cookie_name) or "").strip()
        if cookie_token and cookie_token not in token_candidates:
            token_candidates.append(cookie_token)

    if not token_candidates:
        return None

    payload: Optional[Dict[str, Any]] = None
    chosen_token: Optional[str] = None
    for candidate in token_candidates:
        try:
            payload = decode_published_app_preview_token(candidate)
            chosen_token = candidate
            break
        except Exception:
            continue

    if payload is None or chosen_token is None:
        raise HTTPException(status_code=401, detail="Invalid published app preview token")

    return {
        "type": "published_app_preview",
        "tenant_id": str(payload["tenant_id"]),
        "app_id": str(payload["app_id"]),
        "revision_id": str(payload["revision_id"]),
        "user_id": str(payload.get("sub")),
        "scopes": payload.get("scope", []),
        "auth_token": chosen_token,
    }


async def get_current_published_app_preview_principal(
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_preview_principal),
) -> Dict[str, Any]:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Preview authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal
