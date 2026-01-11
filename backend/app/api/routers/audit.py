from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel

from app.db.models.rbac import Action, ResourceType, Permission
from app.db.models.audit import AuditResult
from app.db.connection import MongoDatabase
from app.core.rbac import get_tenant_context, check_permission


router = APIRouter()


class AuditLogResponse(BaseModel):
    id: str
    tenant_id: str
    org_unit_id: Optional[str]
    actor_id: str
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
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    query = {"tenant_id": tenant.id}

    if actor_id:
        query["actor_id"] = ObjectId(actor_id)
    if action:
        query["action"] = action.value
    if resource_type:
        query["resource_type"] = resource_type.value
    if resource_id:
        query["resource_id"] = resource_id
    if result:
        query["result"] = result.value
    if org_unit_id:
        query["org_unit_id"] = ObjectId(org_unit_id)

    if start_date or end_date:
        query["timestamp"] = {}
        if start_date:
            query["timestamp"]["$gte"] = start_date
        if end_date:
            query["timestamp"]["$lte"] = end_date

    cursor = db.audit_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit)

    logs = []
    async for doc in cursor:
        logs.append(AuditLogResponse(
            id=str(doc["_id"]),
            tenant_id=str(doc["tenant_id"]),
            org_unit_id=str(doc["org_unit_id"]) if doc.get("org_unit_id") else None,
            actor_id=str(doc["actor_id"]),
            actor_type=doc["actor_type"],
            actor_email=doc["actor_email"],
            action=doc["action"],
            resource_type=doc["resource_type"],
            resource_id=doc.get("resource_id"),
            resource_name=doc.get("resource_name"),
            result=doc["result"],
            failure_reason=doc.get("failure_reason"),
            ip_address=doc.get("ip_address"),
            user_agent=doc.get("user_agent"),
            timestamp=doc["timestamp"],
            duration_ms=doc.get("duration_ms"),
        ))

    return logs


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
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    query = {"tenant_id": tenant.id}

    if actor_id:
        query["actor_id"] = ObjectId(actor_id)
    if action:
        query["action"] = action.value
    if resource_type:
        query["resource_type"] = resource_type.value
    if result:
        query["result"] = result.value

    if start_date or end_date:
        query["timestamp"] = {}
        if start_date:
            query["timestamp"]["$gte"] = start_date
        if end_date:
            query["timestamp"]["$lte"] = end_date

    count = await db.audit_logs.count_documents(query)

    return {"count": count}


@router.get("/tenants/{tenant_slug}/audit-logs/{log_id}", response_model=AuditLogDetailResponse)
async def get_audit_log(
    tenant_slug: str,
    log_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    doc = await db.audit_logs.find_one({"_id": ObjectId(log_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Audit log not found")

    return AuditLogDetailResponse(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        org_unit_id=str(doc["org_unit_id"]) if doc.get("org_unit_id") else None,
        actor_id=str(doc["actor_id"]),
        actor_type=doc["actor_type"],
        actor_email=doc["actor_email"],
        action=doc["action"],
        resource_type=doc["resource_type"],
        resource_id=doc.get("resource_id"),
        resource_name=doc.get("resource_name"),
        result=doc["result"],
        failure_reason=doc.get("failure_reason"),
        ip_address=doc.get("ip_address"),
        user_agent=doc.get("user_agent"),
        timestamp=doc["timestamp"],
        duration_ms=doc.get("duration_ms"),
        before_state=doc.get("before_state"),
        after_state=doc.get("after_state"),
        request_params=doc.get("request_params"),
    )


@router.get("/tenants/{tenant_slug}/audit-logs/stats/actions")
async def get_action_stats(
    tenant_slug: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    match_stage = {"tenant_id": tenant.id}
    if start_date or end_date:
        match_stage["timestamp"] = {}
        if start_date:
            match_stage["timestamp"]["$gte"] = start_date
        if end_date:
            match_stage["timestamp"]["$lte"] = end_date

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": {"action": "$action", "result": "$result"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]

    results = await db.audit_logs.aggregate(pipeline).to_list(length=100)

    stats = {}
    for r in results:
        action = r["_id"]["action"]
        result = r["_id"]["result"]
        if action not in stats:
            stats[action] = {"success": 0, "failure": 0, "denied": 0}
        stats[action][result] = r["count"]

    return {"stats": stats}


@router.get("/tenants/{tenant_slug}/audit-logs/stats/actors")
async def get_actor_stats(
    tenant_slug: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(10, ge=1, le=50),
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.AUDIT, action=Action.READ),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    match_stage = {"tenant_id": tenant.id}
    if start_date or end_date:
        match_stage["timestamp"] = {}
        if start_date:
            match_stage["timestamp"]["$gte"] = start_date
        if end_date:
            match_stage["timestamp"]["$lte"] = end_date

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": "$actor_email",
            "count": {"$sum": 1},
            "last_action": {"$max": "$timestamp"}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]

    results = await db.audit_logs.aggregate(pipeline).to_list(length=limit)

    return {"actors": [
        {"email": r["_id"], "action_count": r["count"], "last_action": r["last_action"]}
        for r in results
    ]}
