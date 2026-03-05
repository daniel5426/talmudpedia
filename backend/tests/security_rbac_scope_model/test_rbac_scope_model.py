from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.rbac import Action, Permission, ResourceType, check_permission
from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.rbac import ActorType, Role, RoleAssignment, RolePermission
from app.services.security_bootstrap_service import SecurityBootstrapService


async def _seed_tenant_owner(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=user.id, assigned_by=user.id)
    await db_session.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_check_permission_uses_scope_keys(db_session):
    tenant, user = await _seed_tenant_owner(db_session)

    allowed = await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.ROLE, action=Action.READ),
        db=db_session,
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_role_permission_scope_key_unique_per_role(db_session):
    tenant, user = await _seed_tenant_owner(db_session)

    role = Role(
        tenant_id=tenant.id,
        name=f"custom-{uuid4().hex[:6]}",
        description="custom",
        is_system=False,
    )
    db_session.add(role)
    await db_session.flush()

    db_session.add(RolePermission(role_id=role.id, scope_key="users.read"))
    db_session.add(
        RoleAssignment(
            tenant_id=tenant.id,
            role_id=role.id,
            user_id=user.id,
            actor_type=ActorType.USER,
            scope_id=tenant.id,
            scope_type="tenant",
            assigned_by=user.id,
        )
    )
    await db_session.commit()

    rows = (await db_session.execute(select(RolePermission).where(RolePermission.role_id == role.id))).scalars().all()
    assert [row.scope_key for row in rows] == ["users.read"]
