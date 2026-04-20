from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import (
    ORGANIZATION_OWNER_ROLE,
    PROJECT_DEFAULT_ROLE_SCOPES,
    PROJECT_OWNER_ROLE,
    ROLE_FAMILY_ORGANIZATION,
    ROLE_FAMILY_PROJECT,
    is_platform_admin_role,
)
from app.db.postgres.models.identity import OrgMembership, Tenant, User
from app.db.postgres.models.rbac import Role, RoleAssignment, RolePermission
from app.db.postgres.models.workspace import Project, ProjectStatus


async def list_user_organizations(*, db: AsyncSession, user_id: UUID) -> list[Tenant]:
    result = await db.execute(
        select(Tenant)
        .join(OrgMembership, OrgMembership.tenant_id == Tenant.id)
        .where(
            OrgMembership.user_id == user_id,
            Tenant.workos_organization_id.is_not(None),
        )
        .order_by(Tenant.created_at.asc())
    )
    organizations: list[Tenant] = []
    seen: set[UUID] = set()
    for organization in result.scalars().all():
        if organization.id in seen:
            continue
        organizations.append(organization)
        seen.add(organization.id)
    return organizations


async def list_organization_projects(*, db: AsyncSession, organization_id: UUID) -> list[Project]:
    result = await db.execute(
        select(Project)
        .where(
            and_(
                Project.organization_id == organization_id,
                Project.status == ProjectStatus.active,
            )
        )
        .order_by(Project.is_default.desc(), Project.created_at.asc())
    )
    return list(result.scalars().all())


async def resolve_effective_scopes(
    *,
    db: AsyncSession,
    user: User,
    organization_id: UUID,
    project_id: UUID | None,
    organization_permissions: list[str] | None = None,
) -> list[str]:
    if is_platform_admin_role(getattr(user, "role", None)):
        return ["*"]

    _ = organization_permissions
    resolved_scopes: set[str] = set()

    assignments = (
        await db.execute(
            select(RoleAssignment, Role)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                and_(
                    RoleAssignment.tenant_id == organization_id,
                    RoleAssignment.user_id == user.id,
                )
            )
        )
    ).all()

    allowed_role_ids: set[UUID] = set()
    has_org_owner = False
    for assignment, role in assignments:
        if assignment.scope_type == ROLE_FAMILY_ORGANIZATION and assignment.scope_id == organization_id:
            allowed_role_ids.add(assignment.role_id)
            if role.family == ROLE_FAMILY_ORGANIZATION and role.name == ORGANIZATION_OWNER_ROLE:
                has_org_owner = True
        if project_id is not None and assignment.scope_type == ROLE_FAMILY_PROJECT and assignment.scope_id == project_id:
            allowed_role_ids.add(assignment.role_id)

    if allowed_role_ids:
        perms = (
            await db.execute(select(RolePermission).where(RolePermission.role_id.in_(list(allowed_role_ids))))
        ).scalars().all()
        resolved_scopes.update({str(perm.scope_key) for perm in perms if getattr(perm, "scope_key", None)})
    if project_id is not None and has_org_owner:
        resolved_scopes.update(PROJECT_DEFAULT_ROLE_SCOPES.get(PROJECT_OWNER_ROLE, []))
    return sorted(resolved_scopes)


def serialize_user_summary(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "avatar": user.avatar,
        "role": user.role,
    }


def serialize_organization_summary(organization: Tenant) -> dict[str, Any]:
    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "status": organization.status.value if hasattr(organization.status, "value") else str(organization.status),
    }


def serialize_project_summary(project: Project) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "organization_id": str(project.organization_id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "status": project.status.value if hasattr(project.status, "value") else str(project.status),
        "is_default": bool(project.is_default),
    }
