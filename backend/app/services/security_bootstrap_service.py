from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import (
    ORGANIZATION_DEFAULT_ROLE_SCOPES,
    ORGANIZATION_OWNER_ROLE,
    ORGANIZATION_READER_ROLE,
    PROJECT_DEFAULT_ROLE_SCOPES,
    PROJECT_MEMBER_ROLE,
    PROJECT_OWNER_ROLE,
    PROJECT_VIEWER_ROLE,
    ROLE_FAMILY_ORGANIZATION,
    ROLE_FAMILY_PROJECT,
    normalize_scope_list,
)
from app.db.postgres.models.rbac import ActorType, Role, RoleAssignment, RolePermission


class SecurityBootstrapService:
    """Seeds immutable default RBAC roles and baseline assignments for a tenant."""

    SYSTEM_ROLE_ORDER = (
        (ROLE_FAMILY_ORGANIZATION, ORGANIZATION_OWNER_ROLE),
        (ROLE_FAMILY_ORGANIZATION, ORGANIZATION_READER_ROLE),
        (ROLE_FAMILY_PROJECT, PROJECT_OWNER_ROLE),
        (ROLE_FAMILY_PROJECT, PROJECT_MEMBER_ROLE),
        (ROLE_FAMILY_PROJECT, PROJECT_VIEWER_ROLE),
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_default_roles(self, tenant_id: UUID) -> dict[str, Role]:
        roles_by_name: dict[str, Role] = {}

        existing = (
            await self.db.execute(select(Role).where(Role.tenant_id == tenant_id))
        ).scalars().all()
        for role in existing:
            key = self._role_key(role.family, role.name)
            if key in {self._role_key(family, name) for family, name in self.SYSTEM_ROLE_ORDER}:
                roles_by_name[key] = role

        for family, role_name in self.SYSTEM_ROLE_ORDER:
            key = self._role_key(family, role_name)
            role = roles_by_name.get(key)
            if role is None:
                role = Role(
                    tenant_id=tenant_id,
                    family=family,
                    name=role_name,
                    description=f"System default {role_name} role",
                    is_system=True,
                )
                self.db.add(role)
                await self.db.flush()
                roles_by_name[key] = role
            else:
                role.family = family
                role.is_system = True
                if not role.description:
                    role.description = f"System default {role_name} role"

            await self._sync_role_permissions(
                role_id=role.id,
                permissions=self._role_scope_bundle(family, role_name),
            )

        await self.db.flush()
        return roles_by_name

    def _role_key(self, family: str, role_name: str) -> str:
        return f"{family}:{role_name}"

    def _role_scope_bundle(self, family: str, role_name: str) -> list[str]:
        if family == ROLE_FAMILY_ORGANIZATION:
            return ORGANIZATION_DEFAULT_ROLE_SCOPES.get(role_name, [])
        if family == ROLE_FAMILY_PROJECT:
            return PROJECT_DEFAULT_ROLE_SCOPES.get(role_name, [])
        return []

    async def ensure_organization_owner_assignment(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        roles = await self.ensure_default_roles(organization_id)
        owner_role = roles[self._role_key(ROLE_FAMILY_ORGANIZATION, ORGANIZATION_OWNER_ROLE)]

        await self._replace_assignment(
            organization_id=organization_id,
            user_id=user_id,
            role_id=owner_role.id,
            scope_id=organization_id,
            scope_type=ROLE_FAMILY_ORGANIZATION,
            family=ROLE_FAMILY_ORGANIZATION,
            assigned_by=assigned_by or user_id,
        )

    async def ensure_organization_reader_assignment(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        roles = await self.ensure_default_roles(organization_id)
        reader_role = roles[self._role_key(ROLE_FAMILY_ORGANIZATION, ORGANIZATION_READER_ROLE)]

        await self._replace_assignment(
            organization_id=organization_id,
            user_id=user_id,
            role_id=reader_role.id,
            scope_id=organization_id,
            scope_type=ROLE_FAMILY_ORGANIZATION,
            family=ROLE_FAMILY_ORGANIZATION,
            assigned_by=assigned_by or user_id,
        )

    async def ensure_project_owner_assignment(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        await self._ensure_project_assignment(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            role_name=PROJECT_OWNER_ROLE,
            assigned_by=assigned_by,
        )

    async def ensure_project_member_assignment(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        await self._ensure_project_assignment(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            role_name=PROJECT_MEMBER_ROLE,
            assigned_by=assigned_by,
        )

    async def ensure_project_viewer_assignment(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        await self._ensure_project_assignment(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            role_name=PROJECT_VIEWER_ROLE,
            assigned_by=assigned_by,
        )

    async def _ensure_project_assignment(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        user_id: UUID,
        role_name: str,
        assigned_by: UUID | None = None,
    ) -> None:
        roles = await self.ensure_default_roles(organization_id)
        role = roles[self._role_key(ROLE_FAMILY_PROJECT, role_name)]
        await self._replace_assignment(
            organization_id=organization_id,
            user_id=user_id,
            role_id=role.id,
            scope_id=project_id,
            scope_type=ROLE_FAMILY_PROJECT,
            family=ROLE_FAMILY_PROJECT,
            assigned_by=assigned_by or user_id,
        )

    # Legacy wrappers kept for still-unmigrated code paths.
    async def ensure_owner_assignment(self, *, tenant_id: UUID, user_id: UUID, assigned_by: UUID | None = None) -> None:
        await self.ensure_organization_owner_assignment(
            organization_id=tenant_id,
            user_id=user_id,
            assigned_by=assigned_by,
        )

    async def ensure_member_assignment(self, *, tenant_id: UUID, user_id: UUID, assigned_by: UUID | None = None) -> None:
        await self.ensure_organization_reader_assignment(
            organization_id=tenant_id,
            user_id=user_id,
            assigned_by=assigned_by,
        )

    async def reset_tenant_roles(self, tenant_id: UUID) -> None:
        role_ids = (
            await self.db.execute(select(Role.id).where(Role.tenant_id == tenant_id))
        ).scalars().all()
        if role_ids:
            await self.db.execute(delete(RoleAssignment).where(RoleAssignment.role_id.in_(list(role_ids))))
            await self.db.execute(delete(RolePermission).where(RolePermission.role_id.in_(list(role_ids))))
            await self.db.execute(delete(Role).where(Role.id.in_(list(role_ids))))
        await self.db.flush()

    async def _sync_role_permissions(self, *, role_id: UUID, permissions: Iterable[str]) -> None:
        normalized = normalize_scope_list(list(permissions))
        await self.db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for scope_key in normalized:
            self.db.add(RolePermission(role_id=role_id, scope_key=scope_key))
        await self.db.flush()

    async def _replace_assignment(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        role_id: UUID,
        scope_id: UUID,
        scope_type: str,
        family: str,
        assigned_by: UUID,
    ) -> None:
        existing = (
            await self.db.execute(
                select(RoleAssignment)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(
                    and_(
                        RoleAssignment.tenant_id == organization_id,
                        RoleAssignment.user_id == user_id,
                        RoleAssignment.scope_id == scope_id,
                        RoleAssignment.scope_type == scope_type,
                        Role.family == family,
                    )
                )
            )
        ).scalars().all()
        for assignment in existing:
            if assignment.role_id == role_id:
                return
            await self.db.delete(assignment)

        self.db.add(
            RoleAssignment(
                tenant_id=organization_id,
                role_id=role_id,
                user_id=user_id,
                actor_type=ActorType.USER,
                scope_id=scope_id,
                scope_type=scope_type,
                assigned_by=assigned_by,
            )
        )
        await self.db.flush()
