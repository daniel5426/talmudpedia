import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.rbac import Role, RoleAssignment
from app.services.security_bootstrap_service import SecurityBootstrapService


REPO_ROOT = Path(__file__).resolve().parents[3]


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
    role_names = {role.name for role in roles}
    assert {"organization_admin", "organization_member", "organization_owner"}.issubset(role_names)
    assert all(role.is_system for role in roles)

    assignments = (
        await db_session.execute(
            select(RoleAssignment).where(
                RoleAssignment.tenant_id == tenant.id,
                RoleAssignment.user_id == user.id,
            )
        )
    ).scalars().all()
    owner_assignments = [
        item for item in assignments if item.role_id in {role.id for role in roles if role.name == "organization_owner"}
    ]
    assert len(owner_assignments) == 1


@pytest.mark.parametrize(
    ("secret_key", "should_fail"),
    [
        (None, True),
        ("YOUR_SECRET_KEY_HERE_CHANGE_IN_PRODUCTION", True),
        ("replace-with-long-random-secret", True),
        ("explicit-test-secret", False),
    ],
)
def test_security_module_requires_non_default_secret_key(secret_key, should_fail):
    env = os.environ.copy()
    if secret_key is None:
        env.pop("SECRET_KEY", None)
    else:
        env["SECRET_KEY"] = secret_key

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'backend'); import app.core.security",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    if should_fail:
        assert result.returncode != 0
        assert "SECRET_KEY must be set to a non-default value" in (result.stderr or result.stdout)
    else:
        assert result.returncode == 0, result.stderr or result.stdout
