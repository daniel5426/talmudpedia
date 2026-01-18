from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
import uuid
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.postgres.models.audit import AuditLog, AuditResult
from app.db.postgres.models.rbac import Action, ResourceType
from app.db.postgres.session import get_db
from app.core.rbac import get_tenant_context, check_permission, Permission, parse_id

router = APIRouter()

class AuditLogResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    org_unit_id: Optional[uuid.UUID]
    actor_id: uuid.UUID
    actor_type: str
    actor_email: str
    action: str
    resource_type: str
    resource_id: Optional[str]
    resource_name: Optional[str]
    result: str
    failure_reason: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    timestamp: datetime
    duration_ms: Optional[int]

class AuditLogDetailResponse(AuditLogResponse):
    before_state: Optional[dict]
    after_state: Optional[dict]
    request_params: Optional[dict]

@router.get("/tenants/{tenant_slug}/audit-logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    tenant_slug: str,
    actor_id: Optional[str] = None,
    action: Optional[Action] = None,
    resource_type: Optional[ResourceType] = None,
    resource_id: Optional[str] = None,
    result: Optional[AuditResult] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    org_unit_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    conditions = [AuditLog.tenant_id == tenant.id]

    if actor_id:
        conditions.append(AuditLog.actor_id == parse_id(actor_id))
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLog.resource_id == resource_id)
    if result:
        conditions.append(AuditLog.result == result)
    if org_unit_id:
        conditions.append(AuditLog.org_unit_id == parse_id(org_unit_id))
    if start_date:
        conditions.append(AuditLog.timestamp >= start_date)
    if end_date:
        conditions.append(AuditLog.timestamp <= end_date)

    stmt = select(AuditLog).where(and_(*conditions)).order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    res = await db.execute(stmt)
    logs = res.scalars().all()

    return [AuditLogResponse(
        id=log.id,
        tenant_id=log.tenant_id,
        org_unit_id=log.org_unit_id,
        actor_id=log.actor_id,
        actor_type=log.actor_type.value if hasattr(log.actor_type, 'value') else log.actor_type,
        actor_email=log.actor_email,
        action=log.action.value if hasattr(log.action, 'value') else log.action,
        resource_type=log.resource_type.value if hasattr(log.resource_type, 'value') else log.resource_type,
        resource_id=log.resource_id,
        resource_name=log.resource_name,
        result=log.result.value if hasattr(log.result, 'value') else log.result,
        failure_reason=log.failure_reason,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        timestamp=log.timestamp,
        duration_ms=log.duration_ms
    ) for log in logs]

@router.get("/tenants/{tenant_slug}/audit-logs/count")
async def count_audit_logs(
    tenant_slug: str,
    actor_id: Optional[str] = None,
    action: Optional[Action] = None,
    resource_type: Optional[ResourceType] = None,
    result: Optional[AuditResult] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    conditions = [AuditLog.tenant_id == tenant.id]

    if actor_id:
        conditions.append(AuditLog.actor_id == parse_id(actor_id))
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if result:
        conditions.append(AuditLog.result == result)
    if start_date:
        conditions.append(AuditLog.timestamp >= start_date)
    if end_date:
        conditions.append(AuditLog.timestamp <= end_date)

    stmt = select(func.count(AuditLog.id)).where(and_(*conditions))
    count = (await db.execute(stmt)).scalar()

    return {"count": count}

@router.get("/tenants/{tenant_slug}/audit-logs/{log_id}", response_model=AuditLogDetailResponse)
async def get_audit_log(
    tenant_slug: str,
    log_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    lid = parse_id(log_id)
    stmt = select(AuditLog).where(and_(AuditLog.id == lid, AuditLog.tenant_id == tenant.id))
    res = await db.execute(stmt)
    log = res.scalar_one_or_none()
    
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")

    return AuditLogDetailResponse(
        id=log.id,
        tenant_id=log.tenant_id,
        org_unit_id=log.org_unit_id,
        actor_id=log.actor_id,
        actor_type=log.actor_type.value if hasattr(log.actor_type, 'value') else log.actor_type,
        actor_email=log.actor_email,
        action=log.action.value if hasattr(log.action, 'value') else log.action,
        resource_type=log.resource_type.value if hasattr(log.resource_type, 'value') else log.resource_type,
        resource_id=log.resource_id,
        resource_name=log.resource_name,
        result=log.result.value if hasattr(log.result, 'value') else log.result,
        failure_reason=log.failure_reason,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        timestamp=log.timestamp,
        duration_ms=log.duration_ms,
        before_state=log.before_state,
        after_state=log.after_state,
        request_params=log.request_params,
    )
