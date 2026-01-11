from typing import Optional, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager
from bson import ObjectId
from fastapi import Request

from app.db.models.audit import AuditLog, AuditResult
from app.db.models.rbac import Action, ResourceType, ActorType, Permission
from app.db.connection import MongoDatabase


class AuditContext:
    def __init__(
        self,
        tenant_id: ObjectId,
        org_unit_id: Optional[ObjectId],
        actor_id: ObjectId,
        actor_type: ActorType,
        actor_email: str,
        action: Action,
        resource_type: ResourceType,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        request: Optional[Request] = None,
    ):
        self.tenant_id = tenant_id
        self.org_unit_id = org_unit_id
        self.actor_id = actor_id
        self.actor_type = actor_type
        self.actor_email = actor_email
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.resource_name = resource_name
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


@asynccontextmanager
async def audit_action(
    tenant_id: ObjectId,
    org_unit_id: Optional[ObjectId],
    actor_id: ObjectId,
    actor_type: ActorType,
    actor_email: str,
    action: Action,
    resource_type: ResourceType,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    request: Optional[Request] = None,
):
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
        request=request,
    )

    try:
        yield ctx
    except Exception as e:
        ctx.set_failure(str(e))
        raise
    finally:
        await _save_audit_log(ctx)


async def _save_audit_log(ctx: AuditContext):
    db = MongoDatabase.get_db()

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

    await db.audit_logs.insert_one(log_entry.model_dump(by_alias=True))


async def log_permission_denied(
    tenant_id: ObjectId,
    org_unit_id: Optional[ObjectId],
    actor_id: ObjectId,
    actor_type: ActorType,
    actor_email: str,
    permission: Permission,
    resource_id: Optional[str] = None,
    request: Optional[Request] = None,
):
    db = MongoDatabase.get_db()

    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    log_entry = AuditLog(
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        actor_id=actor_id,
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

    await db.audit_logs.insert_one(log_entry.model_dump(by_alias=True))


async def log_simple_action(
    tenant_id: ObjectId,
    org_unit_id: Optional[ObjectId],
    actor_id: ObjectId,
    actor_type: ActorType,
    actor_email: str,
    action: Action,
    resource_type: ResourceType,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    result: AuditResult = AuditResult.SUCCESS,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
):
    db = MongoDatabase.get_db()

    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    log_entry = AuditLog(
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        result=result,
        request_params=details,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=datetime.utcnow(),
    )

    await db.audit_logs.insert_one(log_entry.model_dump(by_alias=True))
