from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException, Header
from pydantic import BaseModel
from .routers.auth import get_current_user
from app.db.postgres.models.identity import Tenant, User, OrgUnit, OrgMembership
from app.db.postgres.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import jwt
from app.core.security import SECRET_KEY, ALGORITHM

class AuthContext(BaseModel):
    user: User
    tenant: Tenant
    org_unit: Optional[OrgUnit] = None

    class Config:
        arbitrary_types_allowed = True

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
