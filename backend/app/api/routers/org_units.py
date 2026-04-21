from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, or_

from app.db.postgres.models.identity import User, Organization, OrganizationStatus, OrgUnit, OrgUnitType, OrgMembership, MembershipStatus
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType, ModelStatus
from app.db.postgres.models.rag import RetrievalPolicy
from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.api.dependencies import get_current_principal, require_scopes
from app.core.scope_registry import is_platform_admin_role
from app.services.auth_context_service import resolve_effective_scopes
from app.services.security_bootstrap_service import SecurityBootstrapService

router = APIRouter()

# Schemas
class CreateTenantRequest(BaseModel):
    name: str

class CreateOrgUnitRequest(BaseModel):
    name: str
    type: OrgUnitType
    parent_id: Optional[str] = None

class UpdateOrgUnitRequest(BaseModel):
    name: Optional[str] = None

class AddMemberRequest(BaseModel):
    user_id: str
    org_unit_id: str

class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime

class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[OrganizationStatus] = None

class TenantSettingsResponse(BaseModel):
    default_chat_model_id: Optional[str] = None
    default_embedding_model_id: Optional[str] = None
    default_retrieval_policy: Optional[RetrievalPolicy] = None

class UpdateTenantSettingsRequest(BaseModel):
    default_chat_model_id: Optional[str] = None
    default_embedding_model_id: Optional[str] = None
    default_retrieval_policy: Optional[RetrievalPolicy] = None

class OrgUnitResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    name: str
    type: str
    created_at: datetime

class OrgUnitTreeResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    children: List["OrgUnitTreeResponse"] = []

OrgUnitTreeResponse.model_rebuild()


def _organization_status_value(status_value: OrganizationStatus | str) -> str:
    return status_value.value if hasattr(status_value, "value") else str(status_value)


async def _ensure_organization_settings_editor(organization: Organization, user: User, db: AsyncSession) -> None:
    """Allow mutations only for global admins or users with organization write access."""
    if is_platform_admin_role(getattr(user, "role", None)):
        return

    scopes = await resolve_effective_scopes(
        db=db,
        user=user,
        organization_id=organization.id,
        project_id=None,
    )
    if "organizations.write" not in set(scopes):
        raise HTTPException(status_code=403, detail="Permission denied")


def _organization_row_key() -> str:
    return f"organization-{uuid.uuid4().hex[:20]}"


def _org_unit_row_key() -> str:
    return f"group-{uuid.uuid4().hex[:20]}"


def _normalize_organization_settings(raw: Optional[Dict[str, Any]]) -> TenantSettingsResponse:
    settings = raw or {}
    return TenantSettingsResponse(
        default_chat_model_id=settings.get("default_chat_model_id"),
        default_embedding_model_id=settings.get("default_embedding_model_id"),
        default_retrieval_policy=settings.get("default_retrieval_policy"),
    )


async def _validate_default_model_id(
    *,
    model_id: Optional[str],
    capability: ModelCapabilityType,
    organization: Organization,
    db: AsyncSession,
) -> Optional[str]:
    if model_id is None:
        return None

    model_uuid = parse_id(model_id)
    if model_uuid is None:
        raise HTTPException(status_code=400, detail=f"Invalid model id: {model_id}")

    stmt = select(ModelRegistry).where(
        and_(
            ModelRegistry.id == model_uuid,
            or_(ModelRegistry.organization_id == organization.id, ModelRegistry.organization_id == None),
            ModelRegistry.capability_type == capability,
            ModelRegistry.status == ModelStatus.ACTIVE,
            ModelRegistry.is_active == True,
        )
    )
    model = (await db.execute(stmt)).scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=400,
            detail=f"Model not found or invalid capability/status for {capability.value}",
        )
    return str(model.id)


def parse_id(id_str: Any) -> Optional[uuid.UUID]:
    if id_str is None:
        return None
    if isinstance(id_str, uuid.UUID):
        return id_str
    if isinstance(id_str, str):
        try:
            return uuid.UUID(id_str)
        except (ValueError, AttributeError):
            return None
    return None


async def get_organization_context(
    organization_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> tuple[Organization, User]:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    membership = (
        await db.execute(
            select(OrgMembership).where(
                and_(
                    OrgMembership.organization_id == organization.id,
                    OrgMembership.user_id == current_user.id,
                    OrgMembership.status == MembershipStatus.active,
                )
            )
        )
    ).scalar_one_or_none()
    if membership is None and not is_platform_admin_role(getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    scopes = set(principal.get("scopes") or [])
    if "*" not in scopes and str(organization.id) != str(principal.get("organization_id")):
        raise HTTPException(status_code=403, detail="Active organization does not match requested organization")
    return organization, current_user

# Endpoints
@router.post("/organizations", response_model=TenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not is_platform_admin_role(getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail="Only global admins can create organizations")

    # Check for existing
    organization = Organization(
        name=request.name,
        slug=_organization_row_key(),
        status=OrganizationStatus.active,
    )
    db.add(organization)
    await db.flush()

    root_org = OrgUnit(
        organization_id=organization.id,
        parent_id=None,
        name=request.name,
        slug="root",
        system_key="root",
        type=OrgUnitType.org,
    )
    db.add(root_org)
    await db.flush()

    membership = OrgMembership(
        organization_id=organization.id,
        user_id=current_user.id,
        org_unit_id=root_org.id,
        status=MembershipStatus.active
    )
    db.add(membership)
    bootstrap = SecurityBootstrapService(db)
    await bootstrap.ensure_default_roles(organization.id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=organization.id,
        user_id=current_user.id,
        assigned_by=current_user.id,
    )
    await db.commit()
    await db.refresh(organization)

    return TenantResponse(
        id=organization.id,
        name=organization.name,
        status=_organization_status_value(organization.status),
        created_at=organization.created_at,
    )

@router.get("/organizations", response_model=List[TenantResponse])
async def list_tenants(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if is_platform_admin_role(getattr(current_user, "role", None)):
        stmt = select(Organization)
    else:
        stmt = select(Organization).join(OrgMembership).where(OrgMembership.user_id == current_user.id)

    res = await db.execute(stmt)
    tenants = res.scalars().all()

    return [TenantResponse(
        id=t.id,
        name=t.name,
        status=t.status.value,
        created_at=t.created_at
    ) for t in tenants]

@router.get("/organizations/{organization_id}", response_model=TenantResponse)
async def get_tenant(
    organization_id: uuid.UUID,
    ctx: tuple = Depends(get_organization_context),
):
    organization, _ = ctx
    return TenantResponse(
        id=organization.id,
        name=organization.name,
        status=_organization_status_value(organization.status),
        created_at=organization.created_at,
    )


@router.patch("/organizations/{organization_id}", response_model=TenantResponse)
async def update_tenant(
    organization_id: uuid.UUID,
    request: UpdateTenantRequest,
    ctx: tuple = Depends(get_organization_context),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx
    await _ensure_organization_settings_editor(organization=organization, user=user, db=db)

    if request.name is not None:
        organization.name = request.name

    if request.status is not None:
        organization.status = request.status

    await db.commit()
    await db.refresh(organization)
    return TenantResponse(
        id=organization.id,
        name=organization.name,
        status=_organization_status_value(organization.status),
        created_at=organization.created_at,
    )


@router.get("/organizations/{organization_id}/settings", response_model=TenantSettingsResponse)
async def get_organization_settings(
    organization_id: uuid.UUID,
    ctx: tuple = Depends(get_organization_context),
):
    organization, _ = ctx
    return _normalize_organization_settings(organization.settings)


@router.patch("/organizations/{organization_id}/settings", response_model=TenantSettingsResponse)
async def update_organization_settings(
    organization_id: uuid.UUID,
    request: UpdateTenantSettingsRequest,
    ctx: tuple = Depends(get_organization_context),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx
    await _ensure_organization_settings_editor(organization=organization, user=user, db=db)

    settings = dict(organization.settings or {})
    fields_set = request.model_fields_set

    if "default_chat_model_id" in fields_set:
        settings["default_chat_model_id"] = await _validate_default_model_id(
            model_id=request.default_chat_model_id,
            capability=ModelCapabilityType.CHAT,
            organization=organization,
            db=db,
        )

    if "default_embedding_model_id" in fields_set:
        settings["default_embedding_model_id"] = await _validate_default_model_id(
            model_id=request.default_embedding_model_id,
            capability=ModelCapabilityType.EMBEDDING,
            organization=organization,
            db=db,
        )

    if "default_retrieval_policy" in fields_set:
        settings["default_retrieval_policy"] = (
            request.default_retrieval_policy.value
            if request.default_retrieval_policy is not None
            else None
        )

    organization.settings = settings
    await db.commit()
    await db.refresh(organization)
    return _normalize_organization_settings(organization.settings)

@router.get("/organizations/{organization_id}/org-units", response_model=List[OrgUnitResponse])
async def list_org_units(
    organization_id: uuid.UUID,
    ctx: tuple = Depends(get_organization_context),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = ctx
    stmt = select(OrgUnit).where(OrgUnit.organization_id == organization.id)
    res = await db.execute(stmt)
    units = res.scalars().all()

    return [OrgUnitResponse(
        id=u.id,
        organization_id=u.organization_id,
        parent_id=u.parent_id,
        name=u.name,
        type=u.type.value,
        created_at=u.created_at
    ) for u in units]

@router.get("/organizations/{organization_id}/org-units/tree", response_model=List[OrgUnitTreeResponse])
async def get_org_unit_tree(
    organization_id: uuid.UUID,
    ctx: tuple = Depends(get_organization_context),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = ctx
    stmt = select(OrgUnit).where(OrgUnit.organization_id == organization.id)
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
            type=unit.type.value,
            children=children,
        )

    return [build_tree(r) for r in roots]

@router.post("/organizations/{organization_id}/org-units", response_model=OrgUnitResponse)
async def create_org_unit(
    organization_id: uuid.UUID,
    request: CreateOrgUnitRequest,
    ctx: tuple = Depends(get_organization_context),
    _: dict[str, Any] = Depends(require_scopes("organization_units.write")),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx

    pid = parse_id(request.parent_id) if request.parent_id else None
    if pid:
        stmt = select(OrgUnit).where(and_(OrgUnit.id == pid, OrgUnit.organization_id == organization.id))
        res = await db.execute(stmt)
        if not res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent org unit not found")

    org_unit = OrgUnit(
        organization_id=organization.id,
        parent_id=pid,
        name=request.name,
        slug=_org_unit_row_key(),
        type=request.type,
    )
    db.add(org_unit)
    await db.commit()
    await db.refresh(org_unit)

    return OrgUnitResponse(
        id=org_unit.id,
        organization_id=org_unit.organization_id,
        parent_id=org_unit.parent_id,
        name=org_unit.name,
        type=org_unit.type.value,
        created_at=org_unit.created_at,
    )

@router.get("/organizations/{organization_id}/org-units/{org_unit_id}", response_model=OrgUnitResponse)
async def get_org_unit(
    organization_id: uuid.UUID,
    org_unit_id: str,
    ctx: tuple = Depends(get_organization_context),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = ctx
    uid = parse_id(org_unit_id)

    stmt = select(OrgUnit).where(and_(OrgUnit.id == uid, OrgUnit.organization_id == organization.id))
    res = await db.execute(stmt)
    unit = res.scalar_one_or_none()
    
    if not unit:
        raise HTTPException(status_code=404, detail="Org unit not found")

    return OrgUnitResponse(
        id=unit.id,
        organization_id=unit.organization_id,
        parent_id=unit.parent_id,
        name=unit.name,
        type=unit.type.value,
        created_at=unit.created_at,
    )

@router.put("/organizations/{organization_id}/org-units/{org_unit_id}", response_model=OrgUnitResponse)
async def update_org_unit(
    organization_id: uuid.UUID,
    org_unit_id: str,
    request: UpdateOrgUnitRequest,
    ctx: tuple = Depends(get_organization_context),
    _: dict[str, Any] = Depends(require_scopes("organization_units.write")),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx
    uid = parse_id(org_unit_id)

    stmt = select(OrgUnit).where(and_(OrgUnit.id == uid, OrgUnit.organization_id == organization.id))
    res = await db.execute(stmt)
    unit = res.scalar_one_or_none()
    
    if not unit:
        raise HTTPException(status_code=404, detail="Org unit not found")

    if request.name:
        unit.name = request.name

    await db.commit()
    await db.refresh(unit)

    return OrgUnitResponse(
        id=unit.id,
        organization_id=unit.organization_id,
        parent_id=unit.parent_id,
        name=unit.name,
        type=unit.type.value,
        created_at=unit.created_at,
    )

@router.delete("/organizations/{organization_id}/org-units/{org_unit_id}")
async def delete_org_unit(
    organization_id: uuid.UUID,
    org_unit_id: str,
    ctx: tuple = Depends(get_organization_context),
    _: dict[str, Any] = Depends(require_scopes("organization_units.delete")),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx
    uid = parse_id(org_unit_id)

    stmt = select(OrgUnit).where(and_(OrgUnit.id == uid, OrgUnit.organization_id == organization.id))
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

@router.get("/organizations/{organization_id}/members")
async def list_members(
    organization_id: uuid.UUID,
    org_unit_id: Optional[str] = None,
    ctx: tuple = Depends(get_organization_context),
    db: AsyncSession = Depends(get_db),
):
    organization, _ = ctx
    
    conditions = [OrgMembership.organization_id == organization.id]
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

@router.post("/organizations/{organization_id}/members")
async def add_member(
    organization_id: uuid.UUID,
    request: AddMemberRequest,
    ctx: tuple = Depends(get_organization_context),
    _: dict[str, Any] = Depends(require_scopes("organization_members.write")),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx

    uid = parse_id(request.user_id)
    ouid = parse_id(request.org_unit_id)

    # Verify user
    u_stmt = select(User).where(User.id == uid)
    u_res = await db.execute(u_stmt)
    if not u_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    # Verify org unit
    ou_stmt = select(OrgUnit).where(and_(OrgUnit.id == ouid, OrgUnit.organization_id == organization.id))
    ou_res = await db.execute(ou_stmt)
    if not ou_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Org unit not found")

    # Check existing
    stmt = select(OrgMembership).where(
        and_(
            OrgMembership.organization_id == organization.id,
            OrgMembership.user_id == uid,
            OrgMembership.org_unit_id == ouid
        )
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member of this org unit")

    membership = OrgMembership(
        organization_id=organization.id,
        user_id=uid,
        org_unit_id=ouid,
        status=MembershipStatus.active
    )
    db.add(membership)
    bootstrap = SecurityBootstrapService(db)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=organization.id,
        user_id=uid,
        assigned_by=user.id,
    )
    await db.commit()
    await db.refresh(membership)

    return {"membership_id": str(membership.id), "status": "created"}

@router.delete("/organizations/{organization_id}/members/{membership_id}")
async def remove_member(
    organization_id: uuid.UUID,
    membership_id: str,
    ctx: tuple = Depends(get_organization_context),
    _: dict[str, Any] = Depends(require_scopes("organization_members.delete")),
    db: AsyncSession = Depends(get_db),
):
    organization, user = ctx
    mid = parse_id(membership_id)

    stmt = select(OrgMembership).where(and_(OrgMembership.id == mid, OrgMembership.organization_id == organization.id))
    res = await db.execute(stmt)
    membership = res.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    await db.delete(membership)
    await db.commit()

    return {"status": "deleted"}
