from typing import Optional, List, Tuple
from bson import ObjectId
from fastapi import Depends, HTTPException, status, Request

from app.db.models.user import User
from app.db.models.tenant import Tenant
from app.db.models.org_unit import OrgUnit, OrgMembership
from app.db.models.rbac import Permission, Role, RoleAssignment, Action, ResourceType
from app.db.connection import MongoDatabase
from app.api.routers.auth import get_current_user


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


async def get_org_unit_ancestors(org_unit_id: ObjectId, tenant_id: ObjectId) -> List[ObjectId]:
    db = MongoDatabase.get_db()
    ancestors = []
    current_id = org_unit_id

    while current_id:
        ancestors.append(current_id)
        org_unit = await db.org_units.find_one({"_id": current_id, "tenant_id": tenant_id})
        if not org_unit or not org_unit.get("parent_id"):
            break
        current_id = org_unit["parent_id"]

    return ancestors


async def check_permission(
    user_id: ObjectId,
    tenant_id: ObjectId,
    required_permission: Permission,
    resource_id: Optional[ObjectId] = None,
    resource_owner_id: Optional[ObjectId] = None,
) -> bool:
    db = MongoDatabase.get_db()

    assignments = await db.role_assignments.find({
        "tenant_id": tenant_id,
        "user_id": user_id,
    }).to_list(length=100)

    if not assignments:
        return False

    role_ids = list(set(a["role_id"] for a in assignments))
    roles = await db.roles.find({"_id": {"$in": role_ids}}).to_list(length=100)
    role_map = {r["_id"]: r for r in roles}

    scope_ids_to_check = set()

    if resource_id:
        scope_ids_to_check.add(resource_id)

    if resource_owner_id:
        ancestors = await get_org_unit_ancestors(resource_owner_id, tenant_id)
        scope_ids_to_check.update(ancestors)

    scope_ids_to_check.add(tenant_id)

    for assignment in assignments:
        scope_id = assignment.get("scope_id")
        if scope_id not in scope_ids_to_check:
            continue

        role = role_map.get(assignment["role_id"])
        if not role:
            continue

        for perm in role.get("permissions", []):
            if (perm.get("resource_type") == required_permission.resource_type.value and
                perm.get("action") == required_permission.action.value):
                return True

    return False


async def get_accessible_scopes(
    user_id: ObjectId,
    tenant_id: ObjectId,
    permission: Permission,
) -> List[ObjectId]:
    db = MongoDatabase.get_db()

    assignments = await db.role_assignments.find({
        "tenant_id": tenant_id,
        "user_id": user_id,
    }).to_list(length=100)

    if not assignments:
        return []

    role_ids = list(set(a["role_id"] for a in assignments))
    roles = await db.roles.find({"_id": {"$in": role_ids}}).to_list(length=100)
    role_map = {r["_id"]: r for r in roles}

    accessible_scopes = set()

    for assignment in assignments:
        role = role_map.get(assignment["role_id"])
        if not role:
            continue

        has_permission = any(
            p.get("resource_type") == permission.resource_type.value and
            p.get("action") == permission.action.value
            for p in role.get("permissions", [])
        )

        if has_permission:
            accessible_scopes.add(assignment["scope_id"])

    return list(accessible_scopes)


async def get_tenant_context(
    tenant_slug: str,
    current_user: User = Depends(get_current_user),
) -> Tuple[Tenant, User]:
    db = MongoDatabase.get_db()

    tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
    if not tenant_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant = Tenant(**tenant_doc)

    membership = await db.org_memberships.find_one({
        "tenant_id": tenant.id,
        "user_id": current_user.id,
    })

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
) -> AuthorizationContext:
    db = MongoDatabase.get_db()

    tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
    if not tenant_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant = Tenant(**tenant_doc)

    membership_doc = await db.org_memberships.find_one({
        "tenant_id": tenant.id,
        "user_id": current_user.id,
    })

    if not membership_doc and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this tenant",
        )

    membership = OrgMembership(**membership_doc) if membership_doc else None

    org_unit = None
    if org_unit_slug:
        org_unit_doc = await db.org_units.find_one({
            "tenant_id": tenant.id,
            "slug": org_unit_slug,
        })
        if org_unit_doc:
            org_unit = OrgUnit(**org_unit_doc)

    assignments_cursor = db.role_assignments.find({
        "tenant_id": tenant.id,
        "user_id": current_user.id,
    })
    assignment_docs = await assignments_cursor.to_list(length=100)
    role_assignments = [RoleAssignment(**a) for a in assignment_docs]

    role_ids = list(set(a.role_id for a in role_assignments))
    roles_cursor = db.roles.find({"_id": {"$in": role_ids}})
    role_docs = await roles_cursor.to_list(length=100)
    roles = {r["_id"]: Role(**r) for r in role_docs}

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
        resource_id: Optional[str] = None,
    ):
        resource_oid = ObjectId(resource_id) if resource_id else None
        org_unit_oid = ctx.org_unit.id if ctx.org_unit else None

        has_access = await check_permission(
            user_id=ctx.user.id,
            tenant_id=ctx.tenant.id,
            required_permission=permission,
            resource_id=resource_oid,
            resource_owner_id=org_unit_oid,
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.resource_type.value}:{permission.action.value}",
            )

        return ctx

    return dependency
