from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_scopes
from app.db.postgres.models.audit import AuditLog, AuditResult
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.rbac import Action, ResourceType
from app.db.postgres.session import get_db

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: UUID
    organization_id: UUID
    org_unit_id: Optional[UUID]
    actor_id: UUID
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


async def _organization_for_principal(*, db: AsyncSession, organization_id: UUID, principal: dict) -> tuple[Organization, User]:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    scopes = set(principal.get("scopes") or [])
    if "*" not in scopes and str(organization.id) != str(principal.get("organization_id")):
        raise HTTPException(status_code=403, detail="Active organization does not match requested organization")
    user = await db.get(User, UUID(str(principal["user_id"])))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return organization, user


def _parse_uuid(value: Optional[str], *, field: str) -> Optional[UUID]:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field}") from exc


@router.get("/organizations/{organization_id}/audit-logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    organization_id: UUID,
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
    principal: dict = Depends(require_scopes("audit.read")),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = await _organization_for_principal(db=db, organization_id=organization_id, principal=principal)
    conditions = [AuditLog.organization_id == organization.id]

    if actor_id:
        conditions.append(AuditLog.actor_id == _parse_uuid(actor_id, field="actor_id"))
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLog.resource_id == resource_id)
    if result:
        conditions.append(AuditLog.result == result)
    if org_unit_id:
        conditions.append(AuditLog.org_unit_id == _parse_uuid(org_unit_id, field="org_unit_id"))
    if start_date:
        conditions.append(AuditLog.timestamp >= start_date)
    if end_date:
        conditions.append(AuditLog.timestamp <= end_date)

    rows = (
        await db.execute(
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()

    return [
        AuditLogResponse(
            id=log.id,
            organization_id=log.organization_id,
            org_unit_id=log.org_unit_id,
            actor_id=log.actor_id,
            actor_type=log.actor_type.value if hasattr(log.actor_type, "value") else log.actor_type,
            actor_email=log.actor_email,
            action=log.action.value if hasattr(log.action, "value") else log.action,
            resource_type=log.resource_type.value if hasattr(log.resource_type, "value") else log.resource_type,
            resource_id=log.resource_id,
            resource_name=log.resource_name,
            result=log.result.value if hasattr(log.result, "value") else log.result,
            failure_reason=log.failure_reason,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            timestamp=log.timestamp,
            duration_ms=log.duration_ms,
        )
        for log in rows
    ]


@router.get("/organizations/{organization_id}/audit-logs/count")
async def count_audit_logs(
    organization_id: UUID,
    actor_id: Optional[str] = None,
    action: Optional[Action] = None,
    resource_type: Optional[ResourceType] = None,
    result: Optional[AuditResult] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    principal: dict = Depends(require_scopes("audit.read")),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = await _organization_for_principal(db=db, organization_id=organization_id, principal=principal)
    conditions = [AuditLog.organization_id == organization.id]
    if actor_id:
        conditions.append(AuditLog.actor_id == _parse_uuid(actor_id, field="actor_id"))
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
    count = (await db.execute(select(func.count(AuditLog.id)).where(and_(*conditions)))).scalar()
    return {"count": count}


@router.get("/organizations/{organization_id}/audit-logs/{log_id}", response_model=AuditLogDetailResponse)
async def get_audit_log(
    organization_id: UUID,
    log_id: str,
    principal: dict = Depends(require_scopes("audit.read")),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = await _organization_for_principal(db=db, organization_id=organization_id, principal=principal)
    audit_log_id = _parse_uuid(log_id, field="log_id")
    log = (
        await db.execute(
            select(AuditLog).where(and_(AuditLog.id == audit_log_id, AuditLog.organization_id == organization.id))
        )
    ).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="Audit log not found")

    return AuditLogDetailResponse(
        id=log.id,
        organization_id=log.organization_id,
        org_unit_id=log.org_unit_id,
        actor_id=log.actor_id,
        actor_type=log.actor_type.value if hasattr(log.actor_type, "value") else log.actor_type,
        actor_email=log.actor_email,
        action=log.action.value if hasattr(log.action, "value") else log.action,
        resource_type=log.resource_type.value if hasattr(log.resource_type, "value") else log.resource_type,
        resource_id=log.resource_id,
        resource_name=log.resource_name,
        result=log.result.value if hasattr(log.result, "value") else log.result,
        failure_reason=log.failure_reason,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        timestamp=log.timestamp,
        duration_ms=log.duration_ms,
        before_state=log.before_state,
        after_state=log.after_state,
        request_params=log.request_params,
    )
