from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.rbac import get_tenant_context, parse_id
from app.core.scope_registry import build_scope_catalog, legacy_permission_to_scope, normalize_scope_list
from app.db.postgres.models.identity import User
from app.db.postgres.models.rbac import ActorType, Role, RoleAssignment, RolePermission
from app.db.postgres.session import get_db

router = APIRouter()


class CreateRoleRequest(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[list[str]] = None


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
    permissions: list[str]
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


def _has_scope(principal: dict, required_scope: str) -> bool:
    scopes = set(principal.get("scopes") or [])
    return "*" in scopes or required_scope in scopes


def _require_scope(principal: dict, required_scope: str) -> None:
    if not _has_scope(principal, required_scope):
        raise HTTPException(status_code=403, detail=f"Missing required scope: {required_scope}")


def _permission_scope_key(permission: RolePermission) -> str | None:
    scope_key = getattr(permission, "scope_key", None)
    if scope_key:
        return str(scope_key)
    return legacy_permission_to_scope(
        getattr(getattr(permission, "resource_type", None), "value", getattr(permission, "resource_type", None)),
        getattr(getattr(permission, "action", None), "value", getattr(permission, "action", None)),
    )


async def _role_permissions(db: AsyncSession, role_id: uuid.UUID) -> list[str]:
    rows = (
        await db.execute(select(RolePermission).where(RolePermission.role_id == role_id))
    ).scalars().all()
    permissions = []
    for row in rows:
        scope_key = _permission_scope_key(row)
        if scope_key:
            permissions.append(scope_key)
    return normalize_scope_list(permissions)


@router.get("/tenants/{tenant_slug}/scope-catalog")
async def get_scope_catalog(
    tenant_slug: str,
    _ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
):
    _require_scope(principal, "roles.read")
    return build_scope_catalog()


@router.get("/tenants/{tenant_slug}/roles", response_model=list[RoleResponse])
async def list_roles(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.read")

    roles = (
        await db.execute(select(Role).where(Role.tenant_id == tenant.id).order_by(Role.name.asc()))
    ).scalars().all()

    response: list[RoleResponse] = []
    for role in roles:
        response.append(
            RoleResponse(
                id=role.id,
                tenant_id=role.tenant_id,
                name=role.name,
                description=role.description,
                permissions=await _role_permissions(db, role.id),
                is_system=role.is_system,
                created_at=role.created_at,
            )
        )
    return response


@router.post("/tenants/{tenant_slug}/roles", response_model=RoleResponse)
async def create_role(
    tenant_slug: str,
    request: CreateRoleRequest,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.write")

    existing = (
        await db.execute(select(Role).where(and_(Role.tenant_id == tenant.id, Role.name == request.name)))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Role with this name already exists")

    role = Role(
        tenant_id=tenant.id,
        family="project",
        name=request.name,
        description=request.description,
        is_system=False,
    )
    db.add(role)
    await db.flush()

    permission_keys = normalize_scope_list(request.permissions)
    for scope_key in permission_keys:
        db.add(RolePermission(role_id=role.id, scope_key=scope_key))

    await db.commit()
    await db.refresh(role)

    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        description=role.description,
        permissions=permission_keys,
        is_system=role.is_system,
        created_at=role.created_at,
    )


@router.get("/tenants/{tenant_slug}/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    tenant_slug: str,
    role_id: str,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.read")

    rid = parse_id(role_id)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(status_code=400, detail="Invalid role ID format")

    role = (
        await db.execute(select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id)))
    ).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        description=role.description,
        permissions=await _role_permissions(db, role.id),
        is_system=role.is_system,
        created_at=role.created_at,
    )


@router.put("/tenants/{tenant_slug}/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    tenant_slug: str,
    role_id: str,
    request: UpdateRoleRequest,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.write")

    rid = parse_id(role_id)
    role = (
        await db.execute(select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id)))
    ).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")

    if request.name:
        role.name = request.name
    if request.description is not None:
        role.description = request.description

    if request.permissions is not None:
        await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for scope_key in normalize_scope_list(request.permissions):
            db.add(RolePermission(role_id=role.id, scope_key=scope_key))

    await db.commit()
    await db.refresh(role)

    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        description=role.description,
        permissions=await _role_permissions(db, role.id),
        is_system=role.is_system,
        created_at=role.created_at,
    )


@router.delete("/tenants/{tenant_slug}/roles/{role_id}")
async def delete_role(
    tenant_slug: str,
    role_id: str,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.write")

    rid = parse_id(role_id)
    role = (
        await db.execute(select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id)))
    ).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    active_assignment = (
        await db.execute(select(RoleAssignment).where(RoleAssignment.role_id == role.id).limit(1))
    ).scalar_one_or_none()
    if active_assignment:
        raise HTTPException(status_code=400, detail="Cannot delete role with active assignments")

    await db.delete(role)
    await db.commit()
    return {"status": "deleted"}


@router.get("/tenants/{tenant_slug}/role-assignments", response_model=list[RoleAssignmentResponse])
async def list_role_assignments(
    tenant_slug: str,
    user_id: Optional[str] = None,
    scope_id: Optional[str] = None,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.read")

    conditions = [RoleAssignment.tenant_id == tenant.id]
    if user_id:
        conditions.append(RoleAssignment.user_id == parse_id(user_id))
    if scope_id:
        conditions.append(RoleAssignment.scope_id == parse_id(scope_id))

    assignments = (
        await db.execute(select(RoleAssignment).where(and_(*conditions)))
    ).scalars().all()

    role_ids = {a.role_id for a in assignments}
    roles = {
        role.id: role
        for role in (
            await db.execute(select(Role).where(Role.id.in_(list(role_ids)) if role_ids else sa.false()))
        ).scalars().all()
    }

    response: list[RoleAssignmentResponse] = []
    for assignment in assignments:
        role = roles.get(assignment.role_id)
        response.append(
            RoleAssignmentResponse(
                id=assignment.id,
                tenant_id=assignment.tenant_id,
                user_id=assignment.user_id,
                role_id=assignment.role_id,
                role_name=role.name if role else "Unknown",
                scope_id=assignment.scope_id,
                scope_type=assignment.scope_type,
                actor_type=assignment.actor_type.value,
                assigned_by=assignment.assigned_by,
                assigned_at=assignment.assigned_at,
            )
        )
    return response


@router.post("/tenants/{tenant_slug}/role-assignments", response_model=RoleAssignmentResponse)
async def create_role_assignment(
    tenant_slug: str,
    request: CreateRoleAssignmentRequest,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, current_user = ctx
    _require_scope(principal, "roles.assign")

    rid = parse_id(request.role_id)
    uid = parse_id(request.user_id)
    sid = parse_id(request.scope_id)

    role = (
        await db.execute(select(Role).where(and_(Role.id == rid, Role.tenant_id == tenant.id)))
    ).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if not (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    existing = (
        await db.execute(
            select(RoleAssignment).where(
                and_(
                    RoleAssignment.tenant_id == tenant.id,
                    RoleAssignment.user_id == uid,
                    RoleAssignment.role_id == rid,
                    RoleAssignment.scope_id == sid,
                )
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Role assignment already exists")

    assignment = RoleAssignment(
        tenant_id=tenant.id,
        role_id=rid,
        user_id=uid,
        actor_type=request.actor_type,
        scope_id=sid,
        scope_type=request.scope_type,
        assigned_by=current_user.id,
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
        assigned_at=assignment.assigned_at,
    )


@router.delete("/tenants/{tenant_slug}/role-assignments/{assignment_id}")
async def delete_role_assignment(
    tenant_slug: str,
    assignment_id: str,
    ctx: tuple = Depends(get_tenant_context),
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.assign")

    aid = parse_id(assignment_id)
    assignment = (
        await db.execute(select(RoleAssignment).where(and_(RoleAssignment.id == aid, RoleAssignment.tenant_id == tenant.id)))
    ).scalar_one_or_none()
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
    principal: dict = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    _require_scope(principal, "roles.read")

    uid = parse_id(user_id)
    assignments = (
        await db.execute(
            select(RoleAssignment).where(
                and_(RoleAssignment.tenant_id == tenant.id, RoleAssignment.user_id == uid)
            )
        )
    ).scalars().all()

    if not assignments:
        return {"permissions": [], "scopes": []}

    role_ids = {a.role_id for a in assignments}
    roles = {
        role.id: role
        for role in (
            await db.execute(select(Role).where(Role.id.in_(list(role_ids)) if role_ids else sa.false()))
        ).scalars().all()
    }

    role_permissions: dict[uuid.UUID, list[str]] = {}
    for role_id in role_ids:
        role_permissions[role_id] = await _role_permissions(db, role_id)

    all_permissions: set[str] = set()
    scopes: list[dict[str, object]] = []

    for assignment in assignments:
        role = roles.get(assignment.role_id)
        perms = role_permissions.get(assignment.role_id, [])
        all_permissions.update(perms)
        scopes.append(
            {
                "scope_id": str(assignment.scope_id),
                "scope_type": assignment.scope_type,
                "role_name": role.name if role else "Unknown",
                "permissions": list(perms),
            }
        )

    return {
        "permissions": sorted(all_permissions),
        "scopes": scopes,
    }
