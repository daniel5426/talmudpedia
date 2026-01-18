from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
import uuid
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete

from app.db.postgres.models.identity import User, Tenant, TenantStatus, OrgUnit, OrgUnitType, OrgMembership, OrgRole, MembershipStatus
from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission, Permission, Action, ResourceType, parse_id

router = APIRouter()

# Schemas
class CreateTenantRequest(BaseModel):
    name: str
    slug: str

class CreateOrgUnitRequest(BaseModel):
    name: str
    slug: str
    type: OrgUnitType
    parent_id: Optional[str] = None

class UpdateOrgUnitRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None

class AddMemberRequest(BaseModel):
    user_id: str
    org_unit_id: str

class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime

class OrgUnitResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    name: str
    slug: str
    type: str
    created_at: datetime

class OrgUnitTreeResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    children: List["OrgUnitTreeResponse"] = []

OrgUnitTreeResponse.model_rebuild()

# Endpoints
@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only global admins can create tenants")

    # Check for existing
    stmt = select(Tenant).where(Tenant.slug == request.slug)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tenant slug already exists")

    tenant = Tenant(
        name=request.name,
        slug=request.slug,
        status=TenantStatus.active,
    )
    db.add(tenant)
    await db.flush()

    root_org = OrgUnit(
        tenant_id=tenant.id,
        parent_id=None,
        name=request.name,
        slug=request.slug,
        type=OrgUnitType.org,
    )
    db.add(root_org)
    await db.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=current_user.id,
        org_unit_id=root_org.id,
        role=OrgRole.owner,
        status=MembershipStatus.active
    )
    db.add(membership)
    await db.commit()
    await db.refresh(tenant)

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at,
    )

@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "admin":
        stmt = select(Tenant)
    else:
        stmt = select(Tenant).join(OrgMembership).where(OrgMembership.user_id == current_user.id)

    res = await db.execute(stmt)
    tenants = res.scalars().all()

    return [TenantResponse(
        id=t.id,
        name=t.name,
        slug=t.slug,
        status=t.status.value,
        created_at=t.created_at
    ) for t in tenants]

@router.get("/tenants/{tenant_slug}", response_model=TenantResponse)
async def get_tenant(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at,
    )

@router.get("/tenants/{tenant_slug}/org-units", response_model=List[OrgUnitResponse])
async def list_org_units(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    stmt = select(OrgUnit).where(OrgUnit.tenant_id == tenant.id)
    res = await db.execute(stmt)
    units = res.scalars().all()

    return [OrgUnitResponse(
        id=u.id,
        tenant_id=u.tenant_id,
        parent_id=u.parent_id,
        name=u.name,
        slug=u.slug,
        type=u.type.value,
        created_at=u.created_at
    ) for u in units]

@router.get("/tenants/{tenant_slug}/org-units/tree", response_model=List[OrgUnitTreeResponse])
async def get_org_unit_tree(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    stmt = select(OrgUnit).where(OrgUnit.tenant_id == tenant.id)
    res = await db.execute(stmt)
    all_units = res.scalars().all()

    unit_map = {u.id: u for u in all_units}
    children_map = {}
    roots = []

    for unit in all_units:
        if unit.parent_id:
            if unit.parent_id not in children_map:
                children_map[unit.parent_id] = []
            children_map[unit.parent_id].append(unit.id)
        else:
            roots.append(unit.id)

    def build_tree(uid: uuid.UUID) -> OrgUnitTreeResponse:
        unit = unit_map[uid]
        children = [build_tree(c) for c in children_map.get(uid, [])]
        return OrgUnitTreeResponse(
            id=unit.id,
            name=unit.name,
            slug=unit.slug,
            type=unit.type.value,
            children=children,
        )

    return [build_tree(r) for r in roots]

@router.post("/tenants/{tenant_slug}/org-units", response_model=OrgUnitResponse)
async def create_org_unit(
    tenant_slug: str,
    request: CreateOrgUnitRequest,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ORG_UNIT, action=Action.WRITE),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(OrgUnit).where(and_(OrgUnit.tenant_id == tenant.id, OrgUnit.slug == request.slug))
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Org unit slug already exists in this tenant")

    pid = parse_id(request.parent_id) if request.parent_id else None
    if pid:
        stmt = select(OrgUnit).where(and_(OrgUnit.id == pid, OrgUnit.tenant_id == tenant.id))
        res = await db.execute(stmt)
        if not res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent org unit not found")

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        parent_id=pid,
        name=request.name,
        slug=request.slug,
        type=request.type,
    )
    db.add(org_unit)
    await db.commit()
    await db.refresh(org_unit)

    return OrgUnitResponse(
        id=org_unit.id,
        tenant_id=org_unit.tenant_id,
        parent_id=org_unit.parent_id,
        name=org_unit.name,
        slug=org_unit.slug,
        type=org_unit.type.value,
        created_at=org_unit.created_at,
    )

@router.get("/tenants/{tenant_slug}/org-units/{org_unit_id}", response_model=OrgUnitResponse)
async def get_org_unit(
    tenant_slug: str,
    org_unit_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    uid = parse_id(org_unit_id)

    stmt = select(OrgUnit).where(and_(OrgUnit.id == uid, OrgUnit.tenant_id == tenant.id))
    res = await db.execute(stmt)
    unit = res.scalar_one_or_none()
    
    if not unit:
        raise HTTPException(status_code=404, detail="Org unit not found")

    return OrgUnitResponse(
        id=unit.id,
        tenant_id=unit.tenant_id,
        parent_id=unit.parent_id,
        name=unit.name,
        slug=unit.slug,
        type=unit.type.value,
        created_at=unit.created_at,
    )

@router.put("/tenants/{tenant_slug}/org-units/{org_unit_id}", response_model=OrgUnitResponse)
async def update_org_unit(
    tenant_slug: str,
    org_unit_id: str,
    request: UpdateOrgUnitRequest,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx
    uid = parse_id(org_unit_id)

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ORG_UNIT, action=Action.WRITE),
        db=db,
        resource_id=uid,
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(OrgUnit).where(and_(OrgUnit.id == uid, OrgUnit.tenant_id == tenant.id))
    res = await db.execute(stmt)
    unit = res.scalar_one_or_none()
    
    if not unit:
        raise HTTPException(status_code=404, detail="Org unit not found")

    if request.name:
        unit.name = request.name
    if request.slug:
        unit.slug = request.slug

    await db.commit()
    await db.refresh(unit)

    return OrgUnitResponse(
        id=unit.id,
        tenant_id=unit.tenant_id,
        parent_id=unit.parent_id,
        name=unit.name,
        slug=unit.slug,
        type=unit.type.value,
        created_at=unit.created_at,
    )

@router.delete("/tenants/{tenant_slug}/org-units/{org_unit_id}")
async def delete_org_unit(
    tenant_slug: str,
    org_unit_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx
    uid = parse_id(org_unit_id)

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ORG_UNIT, action=Action.DELETE),
        db=db,
        resource_id=uid,
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(OrgUnit).where(and_(OrgUnit.id == uid, OrgUnit.tenant_id == tenant.id))
    res = await db.execute(stmt)
    unit = res.scalar_one_or_none()
    
    if not unit:
        raise HTTPException(status_code=404, detail="Org unit not found")

    if unit.type == OrgUnitType.org:
        raise HTTPException(status_code=400, detail="Cannot delete root organization")

    # Check for children
    child_stmt = select(OrgUnit).where(OrgUnit.parent_id == uid).limit(1)
    child_res = await db.execute(child_stmt)
    if child_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cannot delete org unit with children")

    await db.delete(unit)
    # Also delete memberships in this unit
    await db.execute(delete(OrgMembership).where(OrgMembership.org_unit_id == uid))
    await db.commit()

    return {"status": "deleted"}

@router.get("/tenants/{tenant_slug}/members")
async def list_members(
    tenant_slug: str,
    org_unit_id: Optional[str] = None,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = ctx
    
    conditions = [OrgMembership.tenant_id == tenant.id]
    if org_unit_id:
        conditions.append(OrgMembership.org_unit_id == parse_id(org_unit_id))

    stmt = select(OrgMembership).where(and_(*conditions))
    res = await db.execute(stmt)
    memberships = res.scalars().all()

    result = []
    for m in memberships:
        # Get user details
        user_stmt = select(User).where(User.id == m.user_id)
        u_res = await db.execute(user_stmt)
        u = u_res.scalar_one_or_none()
        if u:
            result.append({
                "membership_id": str(m.id),
                "user_id": str(m.user_id),
                "org_unit_id": str(m.org_unit_id),
                "email": u.email,
                "full_name": u.full_name,
                "joined_at": m.joined_at,
            })

    return {"members": result}

@router.post("/tenants/{tenant_slug}/members")
async def add_member(
    tenant_slug: str,
    request: AddMemberRequest,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.MEMBERSHIP, action=Action.WRITE),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    uid = parse_id(request.user_id)
    ouid = parse_id(request.org_unit_id)

    # Verify user
    u_stmt = select(User).where(User.id == uid)
    u_res = await db.execute(u_stmt)
    if not u_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    # Verify org unit
    ou_stmt = select(OrgUnit).where(and_(OrgUnit.id == ouid, OrgUnit.tenant_id == tenant.id))
    ou_res = await db.execute(ou_stmt)
    if not ou_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Org unit not found")

    # Check existing
    stmt = select(OrgMembership).where(
        and_(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == uid,
            OrgMembership.org_unit_id == ouid
        )
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member of this org unit")

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=uid,
        org_unit_id=ouid,
        role=OrgRole.member,
        status=MembershipStatus.active
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)

    return {"membership_id": str(membership.id), "status": "created"}

@router.delete("/tenants/{tenant_slug}/members/{membership_id}")
async def remove_member(
    tenant_slug: str,
    membership_id: str,
    ctx: tuple = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    tenant, user = ctx
    mid = parse_id(membership_id)

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.MEMBERSHIP, action=Action.DELETE),
        db=db
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    stmt = select(OrgMembership).where(and_(OrgMembership.id == mid, OrgMembership.tenant_id == tenant.id))
    res = await db.execute(stmt)
    membership = res.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    await db.delete(membership)
    await db.commit()

    return {"status": "deleted"}
