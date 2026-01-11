from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel

from app.db.models.user import User
from app.db.models.tenant import Tenant, TenantStatus
from app.db.models.org_unit import OrgUnit, OrgUnitType, OrgMembership
from app.db.connection import MongoDatabase
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission, Permission, Action, ResourceType


router = APIRouter()


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
    id: str
    name: str
    slug: str
    status: str
    created_at: datetime


class OrgUnitResponse(BaseModel):
    id: str
    tenant_id: str
    parent_id: Optional[str]
    name: str
    slug: str
    type: str
    created_at: datetime


class OrgUnitTreeResponse(BaseModel):
    id: str
    name: str
    slug: str
    type: str
    children: List["OrgUnitTreeResponse"] = []


OrgUnitTreeResponse.model_rebuild()


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only global admins can create tenants")

    db = MongoDatabase.get_db()

    existing = await db.tenants.find_one({"slug": request.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Tenant slug already exists")

    tenant = Tenant(
        name=request.name,
        slug=request.slug,
        status=TenantStatus.ACTIVE,
    )

    result = await db.tenants.insert_one(tenant.model_dump(by_alias=True))
    tenant.id = result.inserted_id

    root_org = OrgUnit(
        tenant_id=tenant.id,
        parent_id=None,
        name=request.name,
        slug=request.slug,
        type=OrgUnitType.ORG,
    )
    await db.org_units.insert_one(root_org.model_dump(by_alias=True))

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=current_user.id,
        org_unit_id=root_org.id,
    )
    await db.org_memberships.insert_one(membership.model_dump(by_alias=True))

    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at,
    )


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(current_user: User = Depends(get_current_user)):
    db = MongoDatabase.get_db()

    if current_user.role == "admin":
        cursor = db.tenants.find({})
    else:
        memberships = await db.org_memberships.find({"user_id": current_user.id}).to_list(100)
        tenant_ids = list(set(m["tenant_id"] for m in memberships))
        cursor = db.tenants.find({"_id": {"$in": tenant_ids}})

    tenants = []
    async for doc in cursor:
        tenants.append(TenantResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            slug=doc["slug"],
            status=doc["status"],
            created_at=doc["created_at"],
        ))

    return tenants


@router.get("/tenants/{tenant_slug}", response_model=TenantResponse)
async def get_tenant(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        created_at=tenant.created_at,
    )


@router.get("/tenants/{tenant_slug}/org-units", response_model=List[OrgUnitResponse])
async def list_org_units(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    cursor = db.org_units.find({"tenant_id": tenant.id})
    units = []
    async for doc in cursor:
        units.append(OrgUnitResponse(
            id=str(doc["_id"]),
            tenant_id=str(doc["tenant_id"]),
            parent_id=str(doc["parent_id"]) if doc.get("parent_id") else None,
            name=doc["name"],
            slug=doc["slug"],
            type=doc["type"],
            created_at=doc["created_at"],
        ))

    return units


@router.get("/tenants/{tenant_slug}/org-units/tree", response_model=List[OrgUnitTreeResponse])
async def get_org_unit_tree(
    tenant_slug: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    all_units = await db.org_units.find({"tenant_id": tenant.id}).to_list(length=1000)

    unit_map = {str(u["_id"]): u for u in all_units}
    children_map = {}
    roots = []

    for unit in all_units:
        unit_id = str(unit["_id"])
        parent_id = str(unit["parent_id"]) if unit.get("parent_id") else None

        if parent_id:
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(unit_id)
        else:
            roots.append(unit_id)

    def build_tree(unit_id: str) -> OrgUnitTreeResponse:
        unit = unit_map[unit_id]
        children = [build_tree(c) for c in children_map.get(unit_id, [])]
        return OrgUnitTreeResponse(
            id=unit_id,
            name=unit["name"],
            slug=unit["slug"],
            type=unit["type"],
            children=children,
        )

    return [build_tree(r) for r in roots]


@router.post("/tenants/{tenant_slug}/org-units", response_model=OrgUnitResponse)
async def create_org_unit(
    tenant_slug: str,
    request: CreateOrgUnitRequest,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ORG_UNIT, action=Action.WRITE),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    existing = await db.org_units.find_one({"tenant_id": tenant.id, "slug": request.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Org unit slug already exists in this tenant")

    parent_id = None
    if request.parent_id:
        parent = await db.org_units.find_one({"_id": ObjectId(request.parent_id), "tenant_id": tenant.id})
        if not parent:
            raise HTTPException(status_code=404, detail="Parent org unit not found")
        parent_id = ObjectId(request.parent_id)

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        parent_id=parent_id,
        name=request.name,
        slug=request.slug,
        type=request.type,
    )

    result = await db.org_units.insert_one(org_unit.model_dump(by_alias=True))

    return OrgUnitResponse(
        id=str(result.inserted_id),
        tenant_id=str(tenant.id),
        parent_id=str(parent_id) if parent_id else None,
        name=request.name,
        slug=request.slug,
        type=request.type.value,
        created_at=org_unit.created_at,
    )


@router.get("/tenants/{tenant_slug}/org-units/{org_unit_id}", response_model=OrgUnitResponse)
async def get_org_unit(
    tenant_slug: str,
    org_unit_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    doc = await db.org_units.find_one({"_id": ObjectId(org_unit_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Org unit not found")

    return OrgUnitResponse(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        parent_id=str(doc["parent_id"]) if doc.get("parent_id") else None,
        name=doc["name"],
        slug=doc["slug"],
        type=doc["type"],
        created_at=doc["created_at"],
    )


@router.put("/tenants/{tenant_slug}/org-units/{org_unit_id}", response_model=OrgUnitResponse)
async def update_org_unit(
    tenant_slug: str,
    org_unit_id: str,
    request: UpdateOrgUnitRequest,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ORG_UNIT, action=Action.WRITE),
        resource_id=ObjectId(org_unit_id),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    doc = await db.org_units.find_one({"_id": ObjectId(org_unit_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Org unit not found")

    update_data = {"updated_at": datetime.utcnow()}
    if request.name:
        update_data["name"] = request.name
    if request.slug:
        update_data["slug"] = request.slug

    await db.org_units.update_one({"_id": ObjectId(org_unit_id)}, {"$set": update_data})

    updated = await db.org_units.find_one({"_id": ObjectId(org_unit_id)})

    return OrgUnitResponse(
        id=str(updated["_id"]),
        tenant_id=str(updated["tenant_id"]),
        parent_id=str(updated["parent_id"]) if updated.get("parent_id") else None,
        name=updated["name"],
        slug=updated["slug"],
        type=updated["type"],
        created_at=updated["created_at"],
    )


@router.delete("/tenants/{tenant_slug}/org-units/{org_unit_id}")
async def delete_org_unit(
    tenant_slug: str,
    org_unit_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ORG_UNIT, action=Action.DELETE),
        resource_id=ObjectId(org_unit_id),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    doc = await db.org_units.find_one({"_id": ObjectId(org_unit_id), "tenant_id": tenant.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Org unit not found")

    if doc["type"] == OrgUnitType.ORG.value:
        raise HTTPException(status_code=400, detail="Cannot delete root organization")

    children = await db.org_units.find_one({"parent_id": ObjectId(org_unit_id)})
    if children:
        raise HTTPException(status_code=400, detail="Cannot delete org unit with children")

    await db.org_units.delete_one({"_id": ObjectId(org_unit_id)})
    await db.org_memberships.delete_many({"org_unit_id": ObjectId(org_unit_id)})

    return {"status": "deleted"}


@router.get("/tenants/{tenant_slug}/members")
async def list_members(
    tenant_slug: str,
    org_unit_id: Optional[str] = None,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, _ = ctx
    db = MongoDatabase.get_db()

    query = {"tenant_id": tenant.id}
    if org_unit_id:
        query["org_unit_id"] = ObjectId(org_unit_id)

    memberships = await db.org_memberships.find(query).to_list(length=1000)

    user_ids = [m["user_id"] for m in memberships]
    users = await db.users.find({"_id": {"$in": user_ids}}).to_list(length=1000)
    user_map = {u["_id"]: u for u in users}

    result = []
    for m in memberships:
        user = user_map.get(m["user_id"])
        if user:
            result.append({
                "membership_id": str(m["_id"]),
                "user_id": str(m["user_id"]),
                "org_unit_id": str(m["org_unit_id"]),
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "joined_at": m["joined_at"],
            })

    return {"members": result}


@router.post("/tenants/{tenant_slug}/members")
async def add_member(
    tenant_slug: str,
    request: AddMemberRequest,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.MEMBERSHIP, action=Action.WRITE),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    target_user = await db.users.find_one({"_id": ObjectId(request.user_id)})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    org_unit = await db.org_units.find_one({"_id": ObjectId(request.org_unit_id), "tenant_id": tenant.id})
    if not org_unit:
        raise HTTPException(status_code=404, detail="Org unit not found")

    existing = await db.org_memberships.find_one({
        "tenant_id": tenant.id,
        "user_id": ObjectId(request.user_id),
        "org_unit_id": ObjectId(request.org_unit_id),
    })
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this org unit")

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=ObjectId(request.user_id),
        org_unit_id=ObjectId(request.org_unit_id),
    )

    result = await db.org_memberships.insert_one(membership.model_dump(by_alias=True))

    return {"membership_id": str(result.inserted_id), "status": "created"}


@router.delete("/tenants/{tenant_slug}/members/{membership_id}")
async def remove_member(
    tenant_slug: str,
    membership_id: str,
    ctx: tuple = Depends(get_tenant_context),
):
    tenant, user = ctx
    db = MongoDatabase.get_db()

    has_permission = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.MEMBERSHIP, action=Action.DELETE),
    )

    if not has_permission and user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")

    result = await db.org_memberships.delete_one({
        "_id": ObjectId(membership_id),
        "tenant_id": tenant.id,
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Membership not found")

    return {"status": "deleted"}
