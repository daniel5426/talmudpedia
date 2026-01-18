from typing import Optional, List, Tuple, Any
import uuid
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

# Use Postgres models instead of Mongo models
from app.db.postgres.models.identity import User, Tenant, OrgUnit, OrgMembership
from app.db.postgres.models.rbac import Role, RoleAssignment, Action, ResourceType, RolePermission
from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user

# Re-define Permission model for core logic use if needed, 
# but we can use the enums directly.
from pydantic import BaseModel

class Permission(BaseModel):
    resource_type: ResourceType
    action: Action

def parse_id(id_str: Any) -> Optional[uuid.UUID]:
    """
    Parse an ID string to UUID.
    Returns None if the ID cannot be parsed as a valid UUID.
    For Sefaria text IDs (MongoDB ObjectIds), returns None.
    """
    if id_str is None:
        return None
    if isinstance(id_str, uuid.UUID):
        return id_str
    
    # Try UUID
    if isinstance(id_str, str):
        try:
            return uuid.UUID(id_str)
        except (ValueError, AttributeError):
            pass
            
    return None  # Cannot parse as UUID

class AuthorizationContext:
    def __init__(
        self,
        user: User,
        tenant: Tenant,
        org_unit: Optional[OrgUnit],
        membership: Optional[OrgMembership],
        role_assignments: List[RoleAssignment],
        roles: dict,
    ):
        self.user = user
        self.tenant = tenant
        self.org_unit = org_unit
        self.membership = membership
        self.role_assignments = role_assignments
        self.roles = roles

async def get_org_unit_ancestors(org_unit_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> List[uuid.UUID]:
    ancestors = []
    current_id = org_unit_id

    while current_id:
        ancestors.append(current_id)
        # SQLAlchemy query for org unit
        stmt = select(OrgUnit).where(and_(OrgUnit.id == current_id, OrgUnit.tenant_id == tenant_id))
        result = await db.execute(stmt)
        org_unit = result.scalar_one_or_none()
        
        if not org_unit or not org_unit.parent_id:
            break
        current_id = org_unit.parent_id

    return ancestors

async def check_permission(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    required_permission: Permission,
    db: AsyncSession,
    resource_id: Optional[uuid.UUID] = None,
    resource_owner_id: Optional[uuid.UUID] = None,
) -> bool:
    # 1. Fetch all role assignments for this user in this tenant
    stmt = select(RoleAssignment).where(
        and_(
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.user_id == user_id
        )
    )
    result = await db.execute(stmt)
    assignments = result.scalars().all()

    if not assignments:
        return False

    # 2. Identify scopes to check
    scope_ids_to_check = {tenant_id}
    if resource_id:
        scope_ids_to_check.add(resource_id)
    if resource_owner_id:
        ancestors = await get_org_unit_ancestors(resource_owner_id, tenant_id, db)
        scope_ids_to_check.update(ancestors)

    # 3. Check each assignment
    for assignment in assignments:
        if assignment.scope_id not in scope_ids_to_check:
            continue

        # Check permissions of the associated role
        # We can use the relationship or query specifically
        stmt = select(RolePermission).where(
            and_(
                RolePermission.role_id == assignment.role_id,
                RolePermission.resource_type == required_permission.resource_type,
                RolePermission.action == required_permission.action
            )
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            return True

    return False

async def get_accessible_scopes(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    permission: Permission,
    db: AsyncSession,
) -> List[uuid.UUID]:
    stmt = select(RoleAssignment).where(
        and_(
            RoleAssignment.tenant_id == tenant_id,
            RoleAssignment.user_id == user_id
        )
    )
    result = await db.execute(stmt)
    assignments = result.scalars().all()

    if not assignments:
        return []

    accessible_scopes = set()

    for assignment in assignments:
        stmt = select(RolePermission).where(
            and_(
                RolePermission.role_id == assignment.role_id,
                RolePermission.resource_type == permission.resource_type,
                RolePermission.action == permission.action
            )
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            accessible_scopes.add(assignment.scope_id)

    return list(accessible_scopes)

async def get_tenant_context(
    tenant_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tuple[Tenant, User]:
    stmt = select(Tenant).where(Tenant.slug == tenant_slug)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Check membership
    stmt = select(OrgMembership).where(
        and_(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == current_user.id
        )
    )
    res = await db.execute(stmt)
    membership = res.scalar_one_or_none()

    if not membership and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this tenant",
        )

    return tenant, current_user

async def get_auth_context(
    tenant_slug: str,
    org_unit_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthorizationContext:
    # 1. Get Tenant
    stmt = select(Tenant).where(Tenant.slug == tenant_slug)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # 2. Get Membership
    stmt = select(OrgMembership).where(
        and_(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == current_user.id
        )
    )
    res = await db.execute(stmt)
    membership = res.scalar_one_or_none()

    if not membership and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    # 3. Get Org Unit if requested
    org_unit = None
    if org_unit_slug:
        stmt = select(OrgUnit).where(and_(OrgUnit.tenant_id == tenant.id, OrgUnit.slug == org_unit_slug))
        res = await db.execute(stmt)
        org_unit = res.scalar_one_or_none()

    # 4. Get Role Assignments
    stmt = select(RoleAssignment).where(
        and_(
            RoleAssignment.tenant_id == tenant.id,
            RoleAssignment.user_id == current_user.id
        )
    )
    res = await db.execute(stmt)
    role_assignments = res.scalars().all()

    # 5. Get Roles (for context mapping)
    role_ids = list(set(a.role_id for a in role_assignments))
    roles = {}
    if role_ids:
        stmt = select(Role).where(Role.id.in_(role_ids))
        res = await db.execute(stmt)
        roles_list = res.scalars().all()
        roles = {r.id: r for r in roles_list}

    return AuthorizationContext(
        user=current_user,
        tenant=tenant,
        org_unit=org_unit,
        membership=membership,
        role_assignments=role_assignments,
        roles=roles,
    )

def require_permission(permission: Permission):
    async def dependency(
        ctx: AuthorizationContext = Depends(get_auth_context),
        db: AsyncSession = Depends(get_db),
        resource_id: Optional[str] = None,
    ):
        # Even though we are on Postgres, resource_id could be Mongo OID (e.g. Sefaria text)
        # or a Postgres UUID. parse_id handles both.
        res_id = parse_id(resource_id) if resource_id else None
        org_unit_id = ctx.org_unit.id if ctx.org_unit else None

        has_access = await check_permission(
            user_id=ctx.user.id,
            tenant_id=ctx.tenant.id,
            required_permission=permission,
            db=db,
            resource_id=res_id,
            resource_owner_id=org_unit_id,
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.resource_type.value}:{permission.action.value}",
            )

        return ctx

    return dependency
