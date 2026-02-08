"""
Audit logging module - PostgreSQL implementation.

Provides async context managers and helper functions for logging
audit events to the PostgreSQL database.
"""
from typing import Optional, Dict, Any, Union
from datetime import datetime
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import Request

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.postgres.models.audit import AuditLog, AuditResult
from app.db.postgres.models.rbac import Action, ResourceType, ActorType
from app.db.postgres.engine import sessionmaker as async_sessionmaker

# Pydantic model for permission checks used in log_permission_denied
from pydantic import BaseModel

class Permission(BaseModel):
    """Permission model for audit logging."""
    resource_type: ResourceType
    action: Action


def _to_uuid(value: Any) -> Optional[UUID]:
    """Convert any ID-like value to UUID, returning None if invalid."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except (ValueError, AttributeError):
            return None
    return None


class AuditContext:
    """Context for building and saving an audit log entry."""
    
    def __init__(
        self,
        tenant_id: Union[UUID, str, None],
        org_unit_id: Union[UUID, str, None],
        actor_id: Union[UUID, str, None],
        actor_type: ActorType,
        actor_email: str,
        action: Action,
        resource_type: ResourceType,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        initiator_user_id: Union[UUID, str, None] = None,
        workload_principal_id: Union[UUID, str, None] = None,
        delegation_grant_id: Union[UUID, str, None] = None,
        token_jti: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        request: Optional[Request] = None,
    ):
        self.tenant_id = _to_uuid(tenant_id)
        self.org_unit_id = _to_uuid(org_unit_id)
        self.actor_id = _to_uuid(actor_id)
        self.actor_type = actor_type
        self.actor_email = actor_email
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.resource_name = resource_name
        self.initiator_user_id = _to_uuid(initiator_user_id)
        self.workload_principal_id = _to_uuid(workload_principal_id)
        self.delegation_grant_id = _to_uuid(delegation_grant_id)
        self.token_jti = token_jti
        self.scopes = scopes or []
        self.request = request
        self.start_time = datetime.utcnow()
        self.before_state: Optional[Dict[str, Any]] = None
        self.after_state: Optional[Dict[str, Any]] = None
        self.request_params: Optional[Dict[str, Any]] = None
        self.result: AuditResult = AuditResult.SUCCESS
        self.failure_reason: Optional[str] = None

    def set_before_state(self, state: Dict[str, Any]):
        self.before_state = state

    def set_after_state(self, state: Dict[str, Any]):
        self.after_state = state

    def set_request_params(self, params: Dict[str, Any]):
        self.request_params = params

    def set_failure(self, reason: str):
        self.result = AuditResult.FAILURE
        self.failure_reason = reason

    def set_denied(self, reason: str):
        self.result = AuditResult.DENIED
        self.failure_reason = reason


async def _save_audit_log_with_session(ctx: AuditContext, db: AsyncSession):
    """Save audit log entry using provided session."""
    if not ctx.tenant_id or not ctx.actor_id:
        # Skip logging if essential IDs are missing
        return
        
    end_time = datetime.utcnow()
    duration_ms = int((end_time - ctx.start_time).total_seconds() * 1000)

    ip_address = None
    user_agent = None
    if ctx.request:
        ip_address = ctx.request.client.host if ctx.request.client else None
        user_agent = ctx.request.headers.get("user-agent")

    log_entry = AuditLog(
        tenant_id=ctx.tenant_id,
        org_unit_id=ctx.org_unit_id,
        actor_id=ctx.actor_id,
        actor_type=ctx.actor_type,
        actor_email=ctx.actor_email,
        action=ctx.action,
        resource_type=ctx.resource_type,
        resource_id=ctx.resource_id,
        resource_name=ctx.resource_name,
        initiator_user_id=ctx.initiator_user_id,
        workload_principal_id=ctx.workload_principal_id,
        delegation_grant_id=ctx.delegation_grant_id,
        token_jti=ctx.token_jti,
        scopes=ctx.scopes,
        result=ctx.result,
        failure_reason=ctx.failure_reason,
        before_state=ctx.before_state,
        after_state=ctx.after_state,
        request_params=ctx.request_params,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=ctx.start_time,
        duration_ms=duration_ms,
    )

    db.add(log_entry)
    await db.commit()


async def _save_audit_log(ctx: AuditContext):
    """Save audit log entry, creating a new session."""
    async with async_sessionmaker() as db:
        await _save_audit_log_with_session(ctx, db)


@asynccontextmanager
async def audit_action(
    tenant_id: Union[UUID, str, None],
    org_unit_id: Union[UUID, str, None],
    actor_id: Union[UUID, str, None],
    actor_type: ActorType,
    actor_email: str,
    action: Action,
    resource_type: ResourceType,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    initiator_user_id: Union[UUID, str, None] = None,
    workload_principal_id: Union[UUID, str, None] = None,
    delegation_grant_id: Union[UUID, str, None] = None,
    token_jti: Optional[str] = None,
    scopes: Optional[list[str]] = None,
    request: Optional[Request] = None,
):
    """Context manager for audit logging with automatic success/failure tracking."""
    ctx = AuditContext(
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        initiator_user_id=initiator_user_id,
        workload_principal_id=workload_principal_id,
        delegation_grant_id=delegation_grant_id,
        token_jti=token_jti,
        scopes=scopes,
        request=request,
    )

    try:
        yield ctx
    except Exception as e:
        ctx.set_failure(str(e))
        raise
    finally:
        await _save_audit_log(ctx)


async def log_permission_denied(
    tenant_id: Union[UUID, str, None],
    org_unit_id: Union[UUID, str, None],
    actor_id: Union[UUID, str, None],
    actor_type: ActorType,
    actor_email: str,
    permission: Permission,
    resource_id: Optional[str] = None,
    request: Optional[Request] = None,
):
    """Log a permission denied event."""
    tenant_uuid = _to_uuid(tenant_id)
    actor_uuid = _to_uuid(actor_id)
    org_unit_uuid = _to_uuid(org_unit_id)
    
    if not tenant_uuid or not actor_uuid:
        return

    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    async with async_sessionmaker() as db:
        log_entry = AuditLog(
            tenant_id=tenant_uuid,
            org_unit_id=org_unit_uuid,
            actor_id=actor_uuid,
            actor_type=actor_type,
            actor_email=actor_email,
            action=permission.action,
            resource_type=permission.resource_type,
            resource_id=resource_id,
            result=AuditResult.DENIED,
            failure_reason=f"Permission denied: {permission.resource_type.value}:{permission.action.value}",
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
        )
        db.add(log_entry)
        await db.commit()


async def log_simple_action(
    tenant_id: Union[UUID, str, None],
    org_unit_id: Union[UUID, str, None],
    actor_id: Union[UUID, str, None],
    actor_type: ActorType,
    actor_email: str,
    action: Action,
    resource_type: ResourceType,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    result: AuditResult = AuditResult.SUCCESS,
    details: Optional[Dict[str, Any]] = None,
    initiator_user_id: Union[UUID, str, None] = None,
    workload_principal_id: Union[UUID, str, None] = None,
    delegation_grant_id: Union[UUID, str, None] = None,
    token_jti: Optional[str] = None,
    scopes: Optional[list[str]] = None,
    request: Optional[Request] = None,
):
    """Log a simple action without context manager overhead."""
    tenant_uuid = _to_uuid(tenant_id)
    actor_uuid = _to_uuid(actor_id)
    org_unit_uuid = _to_uuid(org_unit_id)
    
    if not tenant_uuid or not actor_uuid:
        return

    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    async with async_sessionmaker() as db:
        log_entry = AuditLog(
            tenant_id=tenant_uuid,
            org_unit_id=org_unit_uuid,
            actor_id=actor_uuid,
            actor_type=actor_type,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            initiator_user_id=_to_uuid(initiator_user_id),
            workload_principal_id=_to_uuid(workload_principal_id),
            delegation_grant_id=_to_uuid(delegation_grant_id),
            token_jti=token_jti,
            scopes=scopes or [],
            result=result,
            request_params=details,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
        )
        db.add(log_entry)
        await db.commit()
