from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.security_bootstrap_service import SecurityBootstrapService


def _auth_headers(user_id: str, tenant_id: str, org_unit_id: str, org_role: str = "owner") -> dict[str, str]:
    token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role=org_role,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id,
    }


async def _seed_admin_user_setup(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    owner = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    target_user = User(
        email=f"target-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    unscoped_user = User(
        email=f"unscoped-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    db_session.add_all([tenant, owner, target_user, unscoped_user])
    await db_session.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    for user, role in ((owner, OrgRole.owner), (target_user, OrgRole.member), (unscoped_user, OrgRole.member)):
        db_session.add(
            OrgMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                org_unit_id=org_unit.id,
                role=role,
                status=MembershipStatus.active,
            )
        )
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await bootstrap.ensure_member_assignment(tenant_id=tenant.id, user_id=target_user.id, assigned_by=owner.id)
    # Intentionally no role assignment for unscoped_user.

    await db_session.commit()
    return tenant, owner, target_user, unscoped_user, org_unit


@pytest.mark.asyncio
async def test_admin_update_user_full_name_only(client, db_session):
    tenant, owner, target_user, _unscoped_user, org_unit = await _seed_admin_user_setup(db_session)
    headers = _auth_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    response = await client.patch(
        f"/admin/users/{target_user.id}",
        headers=headers,
        json={"full_name": "Updated Name"},
    )
    assert response.status_code == 200

    refreshed = (await db_session.execute(select(User).where(User.id == target_user.id))).scalar_one()
    assert refreshed.full_name == "Updated Name"


@pytest.mark.asyncio
async def test_admin_update_user_ignores_role_payload(client, db_session):
    tenant, owner, target_user, _unscoped_user, org_unit = await _seed_admin_user_setup(db_session)
    headers = _auth_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    response = await client.patch(
        f"/admin/users/{target_user.id}",
        headers=headers,
        json={"full_name": "Role Attempt", "role": "admin"},
    )
    assert response.status_code == 200

    refreshed = (await db_session.execute(select(User).where(User.id == target_user.id))).scalar_one()
    assert refreshed.full_name == "Role Attempt"
    assert refreshed.role == "user"


@pytest.mark.asyncio
async def test_admin_users_requires_users_read_scope(client, db_session):
    tenant, _owner, _target_user, unscoped_user, org_unit = await _seed_admin_user_setup(db_session)
    headers = _auth_headers(str(unscoped_user.id), str(tenant.id), str(org_unit.id), org_role="member")

    response = await client.get("/admin/users", headers=headers)
    assert response.status_code == 403
    assert "users.read" in str(response.json())
