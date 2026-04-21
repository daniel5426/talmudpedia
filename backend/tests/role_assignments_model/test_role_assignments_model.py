from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.rbac import Role, RoleAssignment, RolePermission
from app.db.postgres.models.workspace import Project
from app.services.auth_context_service import resolve_effective_scopes
from app.services.security_bootstrap_service import SecurityBootstrapService


async def _seed_tenant_owner(db_session):
    tenant = Organization(name=f"Organization {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    org_unit = OrgUnit(
        organization_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            organization_id=tenant.id,
            user_id=user.id,
            org_unit_id=org_unit.id,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=user.id, assigned_by=user.id)
    await db_session.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_resolve_effective_scopes_uses_local_role_assignments_only(db_session):
    tenant, user = await _seed_tenant_owner(db_session)
    project = Project(
        organization_id=tenant.id,
        name="Project One",
        slug=f"project-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.commit()

    scopes = await resolve_effective_scopes(
        db=db_session,
        user=user,
        organization_id=tenant.id,
        project_id=project.id,
    )

    assert "roles.assign" in scopes
    assert "projects.write" in scopes
    assert "pipelines.write" in scopes


@pytest.mark.asyncio
async def test_project_role_assignments_store_explicit_project_id(db_session):
    tenant, user = await _seed_tenant_owner(db_session)
    project = Project(
        organization_id=tenant.id,
        name="Project One",
        slug=f"project-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    role = Role(
        organization_id=tenant.id,
        family="project",
        name=f"custom-{uuid4().hex[:6]}",
        description="custom",
        is_system=False,
    )
    db_session.add(role)
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, scope_key="pipelines.read"))
    db_session.add(
        RoleAssignment(
            organization_id=tenant.id,
            role_id=role.id,
            user_id=user.id,
            project_id=project.id,
            assigned_by=user.id,
        )
    )
    await db_session.commit()

    assignment = (
        await db_session.execute(
            select(RoleAssignment).where(RoleAssignment.role_id == role.id, RoleAssignment.user_id == user.id)
        )
    ).scalar_one()

    assert assignment.project_id == project.id
