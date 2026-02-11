from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from .routers.auth import get_current_user
from app.db.postgres.models.identity import Tenant, User, OrgUnit, OrgMembership
from app.db.postgres.models.security import ApprovalDecision, ApprovalStatus
from app.db.postgres.models.published_apps import PublishedAppSession, PublishedApp
from app.db.postgres.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import jwt
from app.core.security import SECRET_KEY, ALGORITHM
from app.core.workload_jwt import decode_workload_token
from app.core.security import decode_published_app_session_token
from app.services.token_broker_service import TokenBrokerService

class AuthContext(BaseModel):
    user: User
    tenant: Tenant
    org_unit: Optional[OrgUnit] = None

    class Config:
        arbitrary_types_allowed = True


SECURITY_SCOPES_ADMIN = {
    "pipelines.catalog.read",
    "pipelines.write",
    "agents.write",
    "tools.write",
    "artifacts.write",
    "agents.execute",
    "agents.run_tests",
    "apps.read",
    "apps.write",
}
SECURITY_SCOPES_MEMBER = {
    "pipelines.catalog.read",
    "agents.execute",
}
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
    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
            result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
            tenant = result.scalar_one_or_none()
            if tenant:
                return {"tenant_id": str(tenant.id), "tenant": tenant}
        except ValueError:
            pass

    # Fallback to first tenant for development/demo
    result = await db.execute(select(Tenant).limit(1))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=500, detail="No tenant configured in database")
        
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
        if user.role == "admin":
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


def _derive_user_scopes(payload: Dict[str, Any], user: User) -> set[str]:
    user_role = str(getattr(user, "role", "")).lower()
    if user_role == "admin":
        return {"*"}

    org_role = str(payload.get("org_role") or "").lower()
    if org_role in {"owner", "admin"}:
        return set(SECURITY_SCOPES_ADMIN)
    return set(SECURITY_SCOPES_MEMBER)


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
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        scopes = _derive_user_scopes(payload, user)
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
        user_id = UUID(str(payload["sub"]))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid published app session token")

    result = await db.execute(
        select(PublishedAppSession).where(PublishedAppSession.id == session_id).limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=401, detail="Published app session not found")
    if str(session.published_app_id) != str(app_id) or str(session.user_id) != str(user_id):
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

    user_result = await db.execute(select(User).where(User.id == user_id).limit(1))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "type": "published_app_user",
        "tenant_id": str(app.tenant_id),
        "app_id": str(app.id),
        "app_slug": app.slug,
        "session_id": str(session.id),
        "user_id": str(user.id),
        "user": user,
        "provider": payload.get("provider", "password"),
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
