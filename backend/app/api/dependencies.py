from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.auth import get_current_user
from app.core.scope_registry import is_platform_admin_role
from app.core.security import (
    ALGORITHM,
    SECRET_KEY,
    decode_published_app_preview_token,
    decode_published_app_session_token,
)
from app.db.postgres.models.identity import OrgUnit, Organization, User
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppAccount,
    PublishedAppAccountStatus,
    PublishedAppSession,
)
from app.db.postgres.models.workspace import Project
from app.db.postgres.session import get_db
from app.services.auth_context_service import list_organization_projects, resolve_effective_scopes
from app.services.organization_api_key_service import OrganizationAPIKeyAuthError, OrganizationAPIKeyService
from app.services.workos_auth_service import WorkOSAuthService


class AuthContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user: User
    organization: Organization
    org_unit: Optional[OrgUnit] = None
    project: Optional[Project] = None


bearer_scheme = HTTPBearer(auto_error=False)


async def get_organization_context(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
) -> Dict[str, Any]:
    organization_uuid: UUID | None = None
    project_uuid: UUID | None = None

    if x_organization_id:
        try:
            organization_uuid = UUID(x_organization_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-Organization-ID header") from exc
    elif WorkOSAuthService.is_enabled():
        service = WorkOSAuthService(db)
        auth_response = await service.authenticate_request(request, response)
        if auth_response is not None and service.current_organization_id(auth_response):
            bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
            organization_uuid = bundle.organization.id
            project_uuid = bundle.project.id

    if organization_uuid is None:
        raise HTTPException(status_code=400, detail="Active organization context is required")

    organization = await db.get(Organization, organization_uuid)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    return {
        "organization_id": str(organization.id),
        "organization": organization,
        "project_id": str(project_uuid) if project_uuid else None,
    }


async def get_auth_context(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AuthContext:
    if WorkOSAuthService.is_enabled():
        service = WorkOSAuthService(db)
        auth_response = await service.authenticate_request(request, response)
        if auth_response is not None and service.current_organization_id(auth_response):
            bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
            if bundle.user.id == user.id:
                return AuthContext(user=user, organization=bundle.organization, org_unit=None, project=bundle.project)

    if _is_platform_admin(user):
        organization = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if organization is None:
            raise HTTPException(status_code=500, detail="No organization configured")
        projects = await list_organization_projects(db=db, organization_id=organization.id)
        return AuthContext(user=user, organization=organization, org_unit=None, project=projects[0] if projects else None)

    raise HTTPException(status_code=403, detail="No active organization session")


def _is_platform_admin(user: User) -> bool:
    return is_platform_admin_role(getattr(user, "role", None))


async def get_current_principal(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if credentials is None and WorkOSAuthService.is_enabled():
        try:
            service = WorkOSAuthService(db)
            auth_response = await service.authenticate_request(request, response)
            if auth_response is not None and service.current_organization_id(auth_response):
                bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
                scopes = await resolve_effective_scopes(
                    db=db,
                    user=bundle.user,
                    organization_id=bundle.organization.id,
                    project_id=bundle.project.id,
                )
                return {
                    "type": "user",
                    "auth_mode": "workos_session",
                    "user": bundle.user,
                    "user_id": str(bundle.user.id),
                    "organization_id": str(bundle.organization.id),
                    "project_id": str(bundle.project.id),
                    "scopes": sorted(scopes),
                    "auth_token": request.cookies.get("wos_session"),
                }
        except HTTPException:
            pass
        except Exception:
            pass

    token = credentials.credentials if credentials is not None and credentials.credentials else None
    if token is None:
        raise HTTPException(status_code=401, detail="Could not validate principal token")

    user = await get_current_user(request=request, response=response, token=token, db=db)
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    organization_id = payload.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    project_id = payload.get("project_id")
    scopes = set(str(s) for s in (payload.get("scope") or []) if str(s).strip())
    return {
        "type": "user",
        "auth_mode": "bearer_token",
        "user": user,
        "user_id": str(user.id),
        "organization_id": str(organization_id),
        "project_id": str(project_id) if project_id else None,
        "scopes": sorted(scopes),
        "auth_token": token,
    }


async def get_current_organization_api_key_principal(
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
    service = OrganizationAPIKeyService(db)
    try:
        api_key = await service.authenticate_token(token)
    except OrganizationAPIKeyAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "type": "organization_api_key",
        "organization_id": str(api_key.organization_id),
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


def require_organization_api_key_scopes(*required_scopes: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    async def _dep(
        principal: Dict[str, Any] = Depends(get_current_organization_api_key_principal),
    ) -> Dict[str, Any]:
        scopes = set(principal.get("scopes") or [])
        missing = [scope for scope in required_scopes if scope not in scopes]
        if missing:
            raise HTTPException(status_code=403, detail=f"Missing required scopes: {', '.join(missing)}")
        return principal

    return _dep


def ensure_published_app_principal_access(
    principal: Optional[Dict[str, Any]],
    *,
    app_id: UUID | str,
    required_scopes: tuple[str, ...] = (),
    require_authenticated: bool = True,
) -> Optional[Dict[str, Any]]:
    if principal is None:
        if require_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    if principal.get("type") != "published_app_user":
        raise HTTPException(status_code=403, detail="Published app principal required")

    if str(principal.get("app_id")) != str(app_id):
        raise HTTPException(status_code=403, detail="Token does not belong to this app")

    if required_scopes:
        scopes = {str(scope).strip() for scope in (principal.get("scopes") or []) if str(scope).strip()}
        if "*" not in scopes:
            missing = [scope for scope in required_scopes if scope not in scopes]
            if missing:
                raise HTTPException(status_code=403, detail=f"Missing required scopes: {', '.join(missing)}")

    return principal


async def ensure_sensitive_action_approved(
    *,
    principal: Dict[str, Any],
    organization_id: UUID | str | None,
    subject_type: str,
    subject_id: str,
    action_scope: str,
    db: AsyncSession,
) -> None:
    del principal, organization_id, subject_type, subject_id, action_scope, db
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
        "organization_id": str(app.organization_id),
        "app_id": str(app.id),
        "app_public_id": app.public_id,
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

    cookie_names = ("published_app_public_preview_token",)
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
        "organization_id": str(payload["organization_id"]),
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
