import pytest

from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import OrgMembership, OrgRole, Tenant, User, MembershipStatus, OrgUnit, OrgUnitType


@pytest.mark.asyncio
async def test_owner_can_patch_tenant_profile(client, db_session):
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    owner = User(email="owner@tenant-a.com", hashed_password="x", role="user")
    db_session.add_all([tenant, owner])
    await db_session.flush()
    root = OrgUnit(tenant_id=tenant.id, parent_id=None, name="Root", slug="root-tenant-a", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=owner.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.commit()

    from main import app

    async def override_current_user():
        return owner

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.patch(
        f"/api/tenants/{tenant.slug}",
        json={"name": "Tenant A Updated", "status": "suspended"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Tenant A Updated"
    assert payload["status"] == "suspended"


@pytest.mark.asyncio
async def test_member_cannot_patch_tenant_profile(client, db_session):
    tenant = Tenant(name="Tenant A", slug="tenant-member")
    member_user = User(email="member@tenant-a.com", hashed_password="x", role="user")
    db_session.add_all([tenant, member_user])
    await db_session.flush()
    root = OrgUnit(tenant_id=tenant.id, parent_id=None, name="Root", slug="root-tenant-member", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=member_user.id,
        org_unit_id=root.id,
        role=OrgRole.member,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.commit()

    from main import app

    async def override_current_user():
        return member_user

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.patch(
        f"/api/tenants/{tenant.slug}",
        json={"name": "Should Fail"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_tenant_slug_conflict_returns_400(client, db_session):
    tenant_a = Tenant(name="Tenant A", slug="tenant-a-conflict")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b-conflict")
    owner = User(email="owner@tenant-conflict.com", hashed_password="x", role="user")
    db_session.add_all([tenant_a, tenant_b, owner])
    await db_session.flush()
    root = OrgUnit(tenant_id=tenant_a.id, parent_id=None, name="Root", slug="root-tenant-conflict", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant_a.id,
        user_id=owner.id,
        org_unit_id=root.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.commit()

    from main import app

    async def override_current_user():
        return owner

    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.patch(
        f"/api/tenants/{tenant_a.slug}",
        json={"slug": tenant_b.slug},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant slug already exists"
