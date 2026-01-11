from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel

from app.db.models.user import User
from app.db.models.rbac import Role, RoleAssignment, Permission, Action, ResourceType, ActorType
from app.db.connection import MongoDatabase
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission


router = APIRouter()


class PermissionRequest(BaseModel):
    resource_type: ResourceType
    action: Action


class CreateRoleRequest(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[PermissionRequest]


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[PermissionRequest]] = None


class CreateRoleAssignmentRequest(BaseModel):
    user_id: str
    role_id: str
    scope_id: str
    scope_type: str
    actor_type: ActorType = ActorType.USER


class RoleResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    permissions: List[dict]
    is_system: bool
    created_at: datetime


class RoleAssignmentResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role_id: str
    role_name: str
    scope_id: str
    scope_type: str
    actor_type: str
    assigned_by: str
    assigned_at: datetime


@router.get("/tenants/{tenant_slug}/roles", response_model=List[RoleResponse])
async def list_roles(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    cursor = db.roles.find({"tenant_id": tenant.id})
    roles = []
    async for doc in cursor:
        roles.append(RoleResponse(
            id=str(doc["_id"]),
            tenant_id=str(doc["tenant_id"]),
            name=doc["name"],
            description=doc.get("description"),
            permissions=doc.get("permissions", []),
            is_system=doc.get("is_system", False),
            created_at=doc["created_at"],
        ))

    return roles


@router.post("/tenants/{tenant_slug}/roles", response_model=RoleResponse)
async def create_role(
    tenant_slug: str,
    request: CreateRoleRequest,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ROLE, action=Action.WRITE),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    existing = await db.roles.find_one({"tenant_id": tenant.id, "name": request.name})
    if existing:
        raise HTTPException(status_code=400, detail="Role with this name already exists")

    permissions = [{"resource_type": p.resource_type.value, "action": p.action.value} for p in request.permissions]

    role = Role(
        tenant_id=tenant.id,
        name=request.name,
        description=request.description,
        permissions=[Permission(**p) for p in permissions],
        is_system=False,
    )

    result = await db.roles.insert_one(role.model_dump(by_alias=True))

    return RoleResponse(
        id=str(result.inserted_id),
        tenant_id=str(tenant.id),
        name=request.name,
        description=request.description,
        permissions=permissions,
        is_system=False,
        created_at=role.created_at,
    )


@router.get("/tenants/{tenant_slug}/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    tenant_slug: str,
    role_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    doc = await db.roles.find_one({"_id": ObjectId(role_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Role not found")

    return RoleResponse(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        name=doc["name"],
        description=doc.get("description"),
        permissions=doc.get("permissions", []),
        is_system=doc.get("is_system", False),
        created_at=doc["created_at"],
    )


@router.put("/tenants/{tenant_slug}/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    tenant_slug: str,
    role_id: str,
    request: UpdateRoleRequest,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ROLE, action=Action.WRITE),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    doc = await db.roles.find_one({"_id": ObjectId(role_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Role not found")

    if doc.get("is_system"):
        raise HTTPException(status_code=400, detail="Cannot modify system roles")

    update_data = {"updated_at": datetime.utcnow()}
    if request.name:
        update_data["name"] = request.name
    if request.description is not None:
        update_data["description"] = request.description
    if request.permissions is not None:
        update_data["permissions"] = [
            {"resource_type": p.resource_type.value, "action": p.action.value}
            for p in request.permissions
        ]

    await db.roles.update_one({"_id": ObjectId(role_id)}, {"$set": update_data})

    updated = await db.roles.find_one({"_id": ObjectId(role_id)})

    return RoleResponse(
        id=str(updated["_id"]),
        tenant_id=str(updated["tenant_id"]),
        name=updated["name"],
        description=updated.get("description"),
        permissions=updated.get("permissions", []),
        is_system=updated.get("is_system", False),
        created_at=updated["created_at"],
    )


@router.delete("/tenants/{tenant_slug}/roles/{role_id}")
async def delete_role(
    tenant_slug: str,
    role_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ROLE, action=Action.DELETE),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    doc = await db.roles.find_one({"_id": ObjectId(role_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Role not found")

    if doc.get("is_system"):
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    assignments = await db.role_assignments.find_one({"role_id": ObjectId(role_id)})
    if assignments:
        raise HTTPException(status_code=400, detail="Cannot delete role with active assignments")

    await db.roles.delete_one({"_id": ObjectId(role_id)})

    return {"status": "deleted"}


@router.get("/tenants/{tenant_slug}/role-assignments", response_model=List[RoleAssignmentResponse])
async def list_role_assignments(
    tenant_slug: str,
    user_id: Optional[str] = None,
    scope_id: Optional[str] = None,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    query = {"tenant_id": tenant.id}
    if user_id:
        query["user_id"] = ObjectId(user_id)
    if scope_id:
        query["scope_id"] = ObjectId(scope_id)

    assignments = await db.role_assignments.find(query).to_list(length=1000)

    role_ids = list(set(a["role_id"] for a in assignments))
    roles = await db.roles.find({"_id": {"$in": role_ids}}).to_list(length=100)
    role_map = {r["_id"]: r for r in roles}

    result = []
    for a in assignments:
        role = role_map.get(a["role_id"])
        result.append(RoleAssignmentResponse(
            id=str(a["_id"]),
            tenant_id=str(a["tenant_id"]),
            user_id=str(a["user_id"]),
            role_id=str(a["role_id"]),
            role_name=role["name"] if role else "Unknown",
            scope_id=str(a["scope_id"]),
            scope_type=a["scope_type"],
            actor_type=a.get("actor_type", "user"),
            assigned_by=str(a["assigned_by"]),
            assigned_at=a["assigned_at"],
        ))

    return result


@router.post("/tenants/{tenant_slug}/role-assignments", response_model=RoleAssignmentResponse)
async def create_role_assignment(
    tenant_slug: str,
    request: CreateRoleAssignmentRequest,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ROLE, action=Action.ADMIN),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    role = await db.roles.find_one({"_id": ObjectId(request.role_id), "tenant_id": tenant.id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    target_user = await db.users.find_one({"_id": ObjectId(request.user_id)})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.role_assignments.find_one({
        "tenant_id": tenant.id,
        "user_id": ObjectId(request.user_id),
        "role_id": ObjectId(request.role_id),
        "scope_id": ObjectId(request.scope_id),
    })
    if existing:
        raise HTTPException(status_code=400, detail="Role assignment already exists")

    assignment = RoleAssignment(
        tenant_id=tenant.id,
        user_id=ObjectId(request.user_id),
        actor_type=request.actor_type,
        role_id=ObjectId(request.role_id),
        scope_id=ObjectId(request.scope_id),
        scope_type=request.scope_type,
        assigned_by=user.id,
    )

    result = await db.role_assignments.insert_one(assignment.model_dump(by_alias=True))

    return RoleAssignmentResponse(
        id=str(result.inserted_id),
        tenant_id=str(tenant.id),
        user_id=request.user_id,
        role_id=request.role_id,
        role_name=role["name"],
        scope_id=request.scope_id,
        scope_type=request.scope_type,
        actor_type=request.actor_type.value,
        assigned_by=str(user.id),
        assigned_at=assignment.assigned_at,
    )


@router.delete("/tenants/{tenant_slug}/role-assignments/{assignment_id}")
async def delete_role_assignment(
    tenant_slug: str,
    assignment_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ROLE, action=Action.ADMIN),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    result = await db.role_assignments.delete_one({
        "_id": ObjectId(assignment_id),
        "tenant_id": tenant.id,
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Role assignment not found")

    return {"status": "deleted"}


@router.get("/tenants/{tenant_slug}/users/{user_id}/permissions")
async def get_user_permissions(
    tenant_slug: str,
    user_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    assignments = await db.role_assignments.find({
        "tenant_id": tenant.id,
        "user_id": ObjectId(user_id),
    }).to_list(length=100)

    if not assignments:
        return {"permissions": [], "scopes": []}

    role_ids = list(set(a["role_id"] for a in assignments))
    roles = await db.roles.find({"_id": {"$in": role_ids}}).to_list(length=100)

    all_permissions = set()
    scopes = []

    for role in roles:
        for perm in role.get("permissions", []):
            all_permissions.add((perm["resource_type"], perm["action"]))

    for a in assignments:
        role = next((r for r in roles if r["_id"] == a["role_id"]), None)
        if role:
            scopes.append({
                "scope_id": str(a["scope_id"]),
                "scope_type": a["scope_type"],
                "role_name": role["name"],
                "permissions": role.get("permissions", []),
            })

    return {
        "permissions": [{"resource_type": p[0], "action": p[1]} for p in all_permissions],
        "scopes": scopes,
    }
