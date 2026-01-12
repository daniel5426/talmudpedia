from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException, Header
from .routers.auth import get_current_user
from app.db.postgres.models.identity import Tenant
from app.db.postgres.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

async def get_tenant_context(
    db: AsyncSession = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
) -> Dict[str, Any]:
    """
    Dependency to get the current tenant context.
    For now, it returns the first tenant if no header is provided, 
    matching the placeholder logic in agents router.
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
        # If no tenant exists in DB, this might be a fresh setup
        # For now, return a placeholder if we can't find one, 
        # or raise an error if strict mode is needed.
        raise HTTPException(status_code=500, detail="No tenant configured in database")
        
    return {"tenant_id": str(tenant.id), "tenant": tenant}
