from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.rbac import Role, RoleAssignment
from app.services.security_bootstrap_service import SecurityBootstrapService


@pytest.mark.asyncio
async def test_bootstrap_seeds_default_roles_and_owner_assignment_idempotently(db_session):
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

    db_session.add(
        OrgMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            org_unit_id=org_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()

    service = SecurityBootstrapService(db_session)
    await service.ensure_default_roles(tenant.id)
    await service.ensure_owner_assignment(tenant_id=tenant.id, user_id=user.id, assigned_by=user.id)

    # second pass should be idempotent
    await service.ensure_default_roles(tenant.id)
    await service.ensure_owner_assignment(tenant_id=tenant.id, user_id=user.id, assigned_by=user.id)
    await db_session.commit()

    roles = (await db_session.execute(select(Role).where(Role.tenant_id == tenant.id))).scalars().all()
    role_names = sorted(role.name for role in roles)
    assert role_names == ["admin", "member", "owner"]
    assert all(role.is_system for role in roles)

    assignments = (
        await db_session.execute(
            select(RoleAssignment).where(
                RoleAssignment.tenant_id == tenant.id,
                RoleAssignment.user_id == user.id,
                RoleAssignment.scope_type == "tenant",
            )
        )
    ).scalars().all()
    owner_assignments = [item for item in assignments if item.role_id in {role.id for role in roles if role.name == "owner"}]
    assert len(owner_assignments) == 1
