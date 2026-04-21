import pytest

from app.api.dependencies import get_current_principal
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User


def _override_principal(tenant: Organization, user: User, scopes: list[str]):
    async def _inner():
        return {
            "sub": str(user.id),
            "user_id": str(user.id),
            "organization_id": str(tenant.id),
            "scopes": scopes,
        }

    return _inner


@pytest.mark.asyncio
async def test_owner_can_patch_tenant_profile(client, db_session, run_prefix):
    tenant = Organization(name="Organization A", slug=f"tenant-a-{run_prefix}")
    owner = User(email=f"owner-{run_prefix}@tenant-a.com", hashed_password="x", role="user")
    db_session.add_all([tenant, owner])
    await db_session.flush()
    root = OrgUnit(organization_id=tenant.id, parent_id=None, name="Root", slug=f"root-tenant-a-{run_prefix}", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        organization_id=tenant.id,
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
    app.dependency_overrides[get_current_principal] = _override_principal(tenant, owner, ["*"])
    response = await client.patch(
        f"/api/tenants/{tenant.id}",
        json={"name": "Organization A Updated", "status": "suspended"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Organization A Updated"
    assert payload["status"] == "suspended"


@pytest.mark.asyncio
async def test_member_cannot_patch_tenant_profile(client, db_session, run_prefix):
    tenant = Organization(name="Organization A", slug=f"tenant-member-{run_prefix}")
    member_user = User(email=f"member-{run_prefix}@tenant-a.com", hashed_password="x", role="user")
    db_session.add_all([tenant, member_user])
    await db_session.flush()
    root = OrgUnit(organization_id=tenant.id, parent_id=None, name="Root", slug=f"root-tenant-member-{run_prefix}", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        organization_id=tenant.id,
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
    app.dependency_overrides[get_current_principal] = _override_principal(tenant, member_user, ["organization_units.read"])
    response = await client.patch(
        f"/api/tenants/{tenant.id}",
        json={"name": "Should Fail"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 403
