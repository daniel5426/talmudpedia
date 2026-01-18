from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
import uuid
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete

# Use Postgres models
from app.db.postgres.models.identity import User, Tenant, OrgUnit
from app.db.postgres.models.rbac import Role, RoleAssignment, RolePermission, Action, ResourceType, ActorType
from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission, parse_id, Permission as CorePermission

router = APIRouter()

# Schema definitions
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
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str]
    permissions: List[dict]
    is_system: bool
    created_at: datetime

class RoleAssignmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    scope_id: uuid.UUID
    scope_type: str
    actor_type: str
    assigned_by: uuid.UUID
    assigned_at: datetime

@router.get("/tenants/{tenant_slug}/roles", response_model=List[RoleResponse])
async def list_roles(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    
    # Query roles with their permissions
    # We'll use select(Role) and since it has a relationship, we can load it 
    # but manually building the response is safer for now.
    stmt = select(Role).where(Role.tenant_id == tenant.id)
    result = await db.execute(stmt)
    roles = result.scalars().all()

    response = []
    for role in roles:
        # Fetch permissions for this role
        perm_stmt = select(RolePermission).where(RolePermission.role_id == role.id)
        perm_result = await db.execute(perm_stmt)
        perms = perm_result.scalars().all()
        
        response.append(RoleResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=role.description,
            permissions=[{"resource_type": p.resource_type.value, "action": p.action.value} for p in perms],
            is_system=role.is_system,
            created_at=role.created_at
        ))

    return response

@router.post("/tenants/{tenant_slug}/roles", response_model=RoleResponse)
async def create_role(
    tenant_slug: str,
    request: CreateRoleRequest,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=CorePermission(resource_type=ResourceType.ROLE, action=Action.WRITE),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check for existing role
    stmt = select(Role).where(and_(Role.tenant_id == tenant.id, Role.name == request.name))
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role with this name already exists")

    # Create role
    new_role = Role(
        tenant_id=tenant.id,
        name=request.name,
        description=request.description,
        is_system=False
    )
    db.add(new_role)
    await db.flush() # Get the role ID

    # Create permissions
    perms_to_return = []
    for p in request.permissions:
        perm = RolePermission(
            role_id=new_role.id,
            resource_type=p.resource_type,
            action=p.action
        )
        db.add(perm)
        perms_to_return.append({"resource_type": p.resource_type.value, "action": p.action.value})

    await db.commit()

    return RoleResponse(
        id=new_role.id,
        tenant_id=tenant.id,
        name=new_role.name,
        description=new_role.description,
        permissions=perms_to_return,
        is_system=False,
        created_at=new_role.created_at
    )

@router.get("/tenants/{tenant_slug}/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    tenant_slug: str,
    role_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    rid = parse_id(role_id)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(status_code=400, detail="Invalid role ID format")

    stmt = select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id))
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Fetch permissions
    perm_stmt = select(RolePermission).where(RolePermission.role_id == role.id)
    perm_result = await db.execute(perm_stmt)
    perms = perm_result.scalars().all()

    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        description=role.description,
        permissions=[{"resource_type": p.resource_type.value, "action": p.action.value} for p in perms],
        is_system=role.is_system,
        created_at=role.created_at
    )

@router.put("/tenants/{tenant_slug}/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    tenant_slug: str,
    role_id: str,
    request: UpdateRoleRequest,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx
    rid = parse_id(role_id)

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=CorePermission(resource_type=ResourceType.ROLE, action=Action.WRITE),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id))
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")

    if request.name:
        role.name = request.name
    if request.description is not None:
        role.description = request.description
    
    if request.permissions is not None:
        # Replace permissions: delete old, add new
        await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for p in request.permissions:
            db.add(RolePermission(role_id=role.id, resource_type=p.resource_type, action=p.action))

    await db.commit()
    await db.refresh(role)

    # Fetch final permissions for response
    perm_stmt = select(RolePermission).where(RolePermission.role_id == role.id)
    perm_result = await db.execute(perm_stmt)
    perms = perm_result.scalars().all()

    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        description=role.description,
        permissions=[{"resource_type": p.resource_type.value, "action": p.action.value} for p in perms],
        is_system=role.is_system,
        created_at=role.created_at
    )

@router.delete("/tenants/{tenant_slug}/roles/{role_id}")
async def delete_role(
    tenant_slug: str,
    role_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx
    rid = parse_id(role_id)

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=CorePermission(resource_type=ResourceType.ROLE, action=Action.DELETE),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id))
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    # Check for active assignments
    ass_stmt = select(RoleAssignment).where(RoleAssignment.role_id == role.id).limit(1)
    ass_res = await db.execute(ass_stmt)
    if ass_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cannot delete role with active assignments")

    await db.delete(role)
    await db.commit()

    return {"status": "deleted"}

@router.get("/tenants/{tenant_slug}/role-assignments", response_model=List[RoleAssignmentResponse])
async def list_role_assignments(
    tenant_slug: str,
    user_id: Optional[str] = None,
    scope_id: Optional[str] = None,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx

    conditions = [RoleAssignment.tenant_id == tenant.id]
    if user_id:
        conditions.append(RoleAssignment.user_id == parse_id(user_id))
    if scope_id:
        conditions.append(RoleAssignment.scope_id == parse_id(scope_id))

    stmt = select(RoleAssignment).where(and_(*conditions))
    res = await db.execute(stmt)
    assignments = res.scalars().all()

    result = []
    for a in assignments:
        # Get role name for the response
        role_stmt = select(Role).where(Role.id == a.role_id)
        role_res = await db.execute(role_stmt)
        role = role_res.scalar_one_or_none()
        
        result.append(RoleAssignmentResponse(
            id=a.id,
            tenant_id=a.tenant_id,
            user_id=a.user_id,
            role_id=a.role_id,
            role_name=role.name if role else "Unknown",
            scope_id=a.scope_id,
            scope_type=a.scope_type,
            actor_type=a.actor_type.value,
            assigned_by=a.assigned_by,
            assigned_at=a.assigned_at
        ))

    return result

@router.post("/tenants/{tenant_slug}/role-assignments", response_model=RoleAssignmentResponse)
async def create_role_assignment(
    tenant_slug: str,
    request: CreateRoleAssignmentRequest,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=CorePermission(resource_type=ResourceType.ROLE, action=Action.ADMIN),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    rid = parse_id(request.role_id)
    uid = parse_id(request.user_id)
    sid = parse_id(request.scope_id)

    # Verify role
    stmt = select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id))
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Verify user exists in Postgres
    user_stmt = select(User).where(User.id == uid)
    u_res = await db.execute(user_stmt)
    if not u_res.scalar_one_or_none():
         raise HTTPException(status_code=404, detail="User not found")

    # Check for existing assignment
    exist_stmt = select(RoleAssignment).where(
        and_(
            RoleAssignment.tenant_id == tenant.id,
            RoleAssignment.user_id == uid,
            RoleAssignment.role_id == rid,
            RoleAssignment.scope_id == sid
        )
    )
    e_res = await db.execute(exist_stmt)
    if e_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role assignment already exists")

    assignment = RoleAssignment(
        tenant_id=tenant.id,
        user_id=uid,
        actor_type=request.actor_type,
        role_id=rid,
        scope_id=sid,
        scope_type=request.scope_type,
        assigned_by=user.id
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return RoleAssignmentResponse(
        id=assignment.id,
        tenant_id=assignment.tenant_id,
        user_id=assignment.user_id,
        role_id=assignment.role_id,
        role_name=role.name,
        scope_id=assignment.scope_id,
        scope_type=assignment.scope_type,
        actor_type=assignment.actor_type.value,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at
    )

@router.delete("/tenants/{tenant_slug}/role-assignments/{assignment_id}")
async def delete_role_assignment(
    tenant_slug: str,
    assignment_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx
    aid = parse_id(assignment_id)

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=CorePermission(resource_type=ResourceType.ROLE, action=Action.ADMIN),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(RoleAssignment).where(and_(RoleAssignment.id == aid, RoleAssignment.tenant_id == tenant.id))
    res = await db.execute(stmt)
    assignment = res.scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Role assignment not found")

    await db.delete(assignment)
    await db.commit()

    return {"status": "deleted"}

@router.get("/tenants/{tenant_slug}/users/{user_id}/permissions")
async def get_user_permissions(
    tenant_slug: str,
    user_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    uid = parse_id(user_id)

    stmt = select(RoleAssignment).where(
        and_(
            RoleAssignment.tenant_id == tenant.id,
            RoleAssignment.user_id == uid
        )
    )
    result = await db.execute(stmt)
    assignments = result.scalars().all()

    if not assignments:
        return {"permissions": [], "scopes": []}

    all_permissions = set()
    scopes = []

    for a in assignments:
        # Get role and its permissions
        role_stmt = select(Role).where(Role.id == a.role_id)
        role_res = await db.execute(role_stmt)
        role = role_res.scalar_one_or_none()
        if not role:
            continue
            
        perm_stmt = select(RolePermission).where(RolePermission.role_id == role.id)
        perm_res = await db.execute(perm_stmt)
        perms = perm_res.scalars().all()
        
        role_perms = []
        for p in perms:
            all_permissions.add((p.resource_type.value, p.action.value))
            role_perms.append({"resource_type": p.resource_type.value, "action": p.action.value})
            
        scopes.append({
            "scope_id": a.scope_id,
            "scope_type": a.scope_type,
            "role_name": role.name,
            "permissions": role_perms
        })

    return {
        "permissions": [{"resource_type": p[0], "action": p[1]} for p in list(all_permissions)],
        "scopes": scopes,
    }
