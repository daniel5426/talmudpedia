from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from .routers.auth import get_current_user
from app.db.postgres.models.identity import Tenant, User, OrgUnit, OrgMembership
from app.db.postgres.models.rbac import RoleAssignment, RolePermission
from app.db.postgres.models.security import ApprovalDecision, ApprovalStatus
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
from app.core.scope_registry import legacy_permission_to_scope, is_platform_admin_role
from app.core.workload_jwt import decode_workload_token
from app.core.security import decode_published_app_preview_token, decode_published_app_session_token
from app.services.token_broker_service import TokenBrokerService

class AuthContext(BaseModel):
    user: User
    tenant: Tenant
    org_unit: Optional[OrgUnit] = None

    class Config:
        arbitrary_types_allowed = True


WORKLOAD_JWT_AUDIENCE = "talmudpedia-internal-api"
bearer_scheme = HTTPBearer(auto_error=False)

async def get_tenant_context(
    db: AsyncSession = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
) -> Dict[str, Any]:
    """
    Dependency to get the current tenant context.
    Matches the placeholder logic but uses Postgres effectively.
    """
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    try:
        tenant_uuid = UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID header")
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"tenant_id": str(tenant.id), "tenant": tenant}

async def get_auth_context(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    # We could also inject the payload here if we wanted to get tenant/org from token
) -> AuthContext:
    """
    Unified dependency for full auth context including tenant and org unit.
    """
    # For now, we resolve the first membership of the user as default context
    # In a real enterprise app, we'd look at the JWT claims or a 'current context' session/cookie
    result = await db.execute(
        select(OrgMembership)
        .where(OrgMembership.user_id == user.id)
        .limit(1)
    )
    membership = result.scalar_one_or_none()
    
    if not membership:
        # Fallback to global tenant if user is a system admin without membership
        if _is_platform_admin(user):
            result = await db.execute(select(Tenant).limit(1))
            tenant = result.scalar_one_or_none()
            if not tenant:
                raise HTTPException(status_code=500, detail="No tenant configured")
            return AuthContext(user=user, tenant=tenant)
        
        raise HTTPException(status_code=403, detail="User is not a member of any organization")

    # Load full tenant and org unit
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == membership.tenant_id))
    tenant = tenant_result.scalar_one()
    
    org_unit_result = await db.execute(select(OrgUnit).where(OrgUnit.id == membership.org_unit_id))
    org_unit = org_unit_result.scalar_one_or_none()
    
    return AuthContext(user=user, tenant=tenant, org_unit=org_unit)


def _is_platform_admin(user: User) -> bool:
    return is_platform_admin_role(getattr(user, "role", None))


async def _derive_user_scopes(payload: Dict[str, Any], user: User, db: AsyncSession) -> set[str]:
    if _is_platform_admin(user):
        return {"*"}

    tenant_id_raw = payload.get("tenant_id")
    if not tenant_id_raw:
        return set()
    try:
        tenant_id = UUID(str(tenant_id_raw))
    except Exception:
        return set()

    scopes: set[str] = set()
    assignments_res = await db.execute(
        select(RoleAssignment).where(
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.user_id == user.id,
        )
    )
    assignments = list(assignments_res.scalars().all())
    if not assignments:
        return scopes

    role_ids = {a.role_id for a in assignments if a.role_id is not None}
    if not role_ids:
        return scopes

    perm_res = await db.execute(
        select(RolePermission).where(RolePermission.role_id.in_(list(role_ids)))
    )
    for perm in perm_res.scalars().all():
        scope_key = getattr(perm, "scope_key", None)
        if scope_key:
            scopes.add(str(scope_key))
            continue
        mapped = legacy_permission_to_scope(
            getattr(getattr(perm, "resource_type", None), "value", getattr(perm, "resource_type", None)),
            getattr(getattr(perm, "action", None), "value", getattr(perm, "action", None)),
        )
        if mapped:
            scopes.add(mapped)
    return scopes


async def _resolve_default_user_tenant_id(user: User, db: AsyncSession) -> Optional[str]:
    membership_res = await db.execute(
        select(OrgMembership)
        .where(OrgMembership.user_id == user.id)
        .order_by(OrgMembership.created_at.asc())
        .limit(1)
    )
    membership = membership_res.scalar_one_or_none()
    if membership is not None and membership.tenant_id is not None:
        return str(membership.tenant_id)
    if _is_platform_admin(user):
        tenant_res = await db.execute(select(Tenant.id).limit(1))
        tenant_id = tenant_res.scalar_one_or_none()
        if tenant_id is not None:
            return str(tenant_id)
    return None


async def _extract_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def get_current_principal(
    token: str = Depends(_extract_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Unified principal resolver for migrated secure endpoints.
    Supports:
    - user principals (existing JWT)
    - delegated workload principals (workload JWT with jti validation)
    """
    try:
        user = await get_current_user(token=token, db=db)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id = payload.get("tenant_id") or await _resolve_default_user_tenant_id(user, db)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        scopes = await _derive_user_scopes(payload, user, db)
        if isinstance(payload.get("scope"), list):
            scopes.update(str(s) for s in payload.get("scope"))
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "scopes": sorted(scopes),
            "auth_token": token,
        }
    except HTTPException:
        pass
    except Exception:
        pass

    try:
        payload = decode_workload_token(token, audience=WORKLOAD_JWT_AUDIENCE)
        broker = TokenBrokerService(db)
        if not await broker.is_jti_active(payload.get("jti")):
            raise HTTPException(status_code=401, detail="Revoked or expired workload token")
        return {
            "type": "workload",
            "principal_id": str(payload["sub"]).replace("wp:", "", 1),
            "tenant_id": str(payload["tenant_id"]),
            "grant_id": str(payload["grant_id"]),
            "initiator_user_id": str(payload.get("act", "")).replace("user:", "", 1) if payload.get("act") else None,
            "run_id": str(payload.get("run_id")) if payload.get("run_id") else None,
            "scopes": sorted(set(payload.get("scope", []))),
            "auth_token": token,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Could not validate principal token")


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

async def ensure_sensitive_action_approved(
    *,
    principal: Dict[str, Any],
    tenant_id: UUID | str | None,
    subject_type: str,
    subject_id: str,
    action_scope: str,
    db: AsyncSession,
) -> None:
    """
    Sensitive mutation guard:
    workload principals must have an explicit APPROVED decision record
    for (tenant, subject, action_scope). User principals are allowed directly.
    """
    if principal.get("type") != "workload":
        return

    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required for sensitive action")

    try:
        tenant_uuid = UUID(str(tenant_id))
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid tenant context for sensitive action")

    result = await db.execute(
        select(ApprovalDecision)
        .where(
            ApprovalDecision.tenant_id == tenant_uuid,
            ApprovalDecision.subject_type == subject_type,
            ApprovalDecision.subject_id == str(subject_id),
            ApprovalDecision.action_scope == action_scope,
        )
        .order_by(ApprovalDecision.created_at.desc())
        .limit(1)
    )
    decision = result.scalar_one_or_none()
    if decision is None or decision.status != ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=403,
            detail=f"Sensitive action '{action_scope}' requires explicit approval",
        )


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
