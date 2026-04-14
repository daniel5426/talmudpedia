from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import (
    ORGANIZATION_DEFAULT_ROLE_SCOPES,
    PROJECT_DEFAULT_ROLE_SCOPES,
    TENANT_DEFAULT_ROLE_SCOPES,
    normalize_scope_list,
)
from app.db.postgres.models.rbac import ActorType, Role, RoleAssignment, RolePermission


class SecurityBootstrapService:
    """Seeds immutable default RBAC roles and baseline assignments for a tenant."""

    SYSTEM_ROLE_ORDER = (
        "organization_owner",
        "organization_admin",
        "organization_member",
        "project_owner",
        "project_admin",
        "project_editor",
        "project_viewer",
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_default_roles(self, tenant_id: UUID) -> dict[str, Role]:
        roles_by_name: dict[str, Role] = {}

        existing = (
            await self.db.execute(select(Role).where(Role.tenant_id == tenant_id))
        ).scalars().all()
        for role in existing:
            role_name = str(role.name or "").lower()
            if role_name in self.SYSTEM_ROLE_ORDER:
                roles_by_name[role_name] = role

        for role_name in self.SYSTEM_ROLE_ORDER:
            role = roles_by_name.get(role_name)
            if role is None:
                role = Role(
                    tenant_id=tenant_id,
                    name=role_name,
                    description=f"System default {role_name} role",
                    is_system=True,
                )
                self.db.add(role)
                await self.db.flush()
                roles_by_name[role_name] = role
            else:
                role.is_system = True
                if not role.description:
                    role.description = f"System default {role_name} role"

            await self._sync_role_permissions(
                role_id=role.id,
                permissions=self._role_scope_bundle(role_name),
            )

        await self.db.flush()
        return roles_by_name

    def _role_scope_bundle(self, role_name: str) -> list[str]:
        return (
            ORGANIZATION_DEFAULT_ROLE_SCOPES.get(role_name)
            or PROJECT_DEFAULT_ROLE_SCOPES.get(role_name)
            or TENANT_DEFAULT_ROLE_SCOPES.get(role_name, [])
        )

    async def ensure_organization_owner_assignment(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        roles = await self.ensure_default_roles(organization_id)
        owner_role = roles["organization_owner"]

        exists = (
            await self.db.execute(
                select(RoleAssignment).where(
                    and_(
                        RoleAssignment.tenant_id == organization_id,
                        RoleAssignment.user_id == user_id,
                        RoleAssignment.role_id == owner_role.id,
                        RoleAssignment.scope_id == organization_id,
                        RoleAssignment.scope_type == "organization",
                    )
                )
            )
        ).scalar_one_or_none()
        if exists:
            return

        self.db.add(
            RoleAssignment(
                tenant_id=organization_id,
                role_id=owner_role.id,
                user_id=user_id,
                actor_type=ActorType.USER,
                scope_id=organization_id,
                scope_type="organization",
                assigned_by=assigned_by or user_id,
            )
        )
        await self.db.flush()

    async def ensure_organization_member_assignment(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        assigned_by: UUID | None = None,
    ) -> None:
        roles = await self.ensure_default_roles(organization_id)
        member_role = roles["organization_member"]

        exists = (
            await self.db.execute(
                select(RoleAssignment).where(
                    and_(
                        RoleAssignment.tenant_id == organization_id,
                        RoleAssignment.user_id == user_id,
                        RoleAssignment.role_id == member_role.id,
                        RoleAssignment.scope_id == organization_id,
                        RoleAssignment.scope_type == "organization",
                    )
                )
            )
        ).scalar_one_or_none()
        if exists:
            return

        self.db.add(
            RoleAssignment(
                tenant_id=organization_id,
                role_id=member_role.id,
                user_id=user_id,
                actor_type=ActorType.USER,
                scope_id=organization_id,
                scope_type="organization",
                assigned_by=assigned_by or user_id,
            )
        )
        await self.db.flush()

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
            role_name="project_owner",
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
            role_name="project_viewer",
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
        role = roles[role_name]
        exists = (
            await self.db.execute(
                select(RoleAssignment).where(
                    and_(
                        RoleAssignment.tenant_id == organization_id,
                        RoleAssignment.user_id == user_id,
                        RoleAssignment.role_id == role.id,
                        RoleAssignment.scope_id == project_id,
                        RoleAssignment.scope_type == "project",
                    )
                )
            )
        ).scalar_one_or_none()
        if exists:
            return
        self.db.add(
            RoleAssignment(
                tenant_id=organization_id,
                role_id=role.id,
                user_id=user_id,
                actor_type=ActorType.USER,
                scope_id=project_id,
                scope_type="project",
                assigned_by=assigned_by or user_id,
            )
        )
        await self.db.flush()

    # Legacy wrappers kept for still-unmigrated code paths.
    async def ensure_owner_assignment(self, *, tenant_id: UUID, user_id: UUID, assigned_by: UUID | None = None) -> None:
        await self.ensure_organization_owner_assignment(
            organization_id=tenant_id,
            user_id=user_id,
            assigned_by=assigned_by,
        )

    async def ensure_member_assignment(self, *, tenant_id: UUID, user_id: UUID, assigned_by: UUID | None = None) -> None:
        await self.ensure_organization_member_assignment(
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
