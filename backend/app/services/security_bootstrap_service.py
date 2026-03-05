from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import TENANT_DEFAULT_ROLE_SCOPES, normalize_scope_list
from app.db.postgres.models.rbac import ActorType, Role, RoleAssignment, RolePermission


class SecurityBootstrapService:
    """Seeds immutable default RBAC roles and baseline assignments for a tenant."""

    SYSTEM_ROLE_ORDER = ("owner", "admin", "member")

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
                permissions=TENANT_DEFAULT_ROLE_SCOPES.get(role_name, []),
            )

        await self.db.flush()
        return roles_by_name

    async def ensure_owner_assignment(self, *, tenant_id: UUID, user_id: UUID, assigned_by: UUID | None = None) -> None:
        roles = await self.ensure_default_roles(tenant_id)
        owner_role = roles["owner"]

        exists = (
            await self.db.execute(
                select(RoleAssignment).where(
                    and_(
                        RoleAssignment.tenant_id == tenant_id,
                        RoleAssignment.user_id == user_id,
                        RoleAssignment.role_id == owner_role.id,
                        RoleAssignment.scope_id == tenant_id,
                        RoleAssignment.scope_type == "tenant",
                    )
                )
            )
        ).scalar_one_or_none()
        if exists:
            return

        self.db.add(
            RoleAssignment(
                tenant_id=tenant_id,
                role_id=owner_role.id,
                user_id=user_id,
                actor_type=ActorType.USER,
                scope_id=tenant_id,
                scope_type="tenant",
                assigned_by=assigned_by or user_id,
            )
        )
        await self.db.flush()

    async def ensure_member_assignment(self, *, tenant_id: UUID, user_id: UUID, assigned_by: UUID | None = None) -> None:
        roles = await self.ensure_default_roles(tenant_id)
        member_role = roles["member"]

        exists = (
            await self.db.execute(
                select(RoleAssignment).where(
                    and_(
                        RoleAssignment.tenant_id == tenant_id,
                        RoleAssignment.user_id == user_id,
                        RoleAssignment.role_id == member_role.id,
                        RoleAssignment.scope_id == tenant_id,
                        RoleAssignment.scope_type == "tenant",
                    )
                )
            )
        ).scalar_one_or_none()
        if exists:
            return

        self.db.add(
            RoleAssignment(
                tenant_id=tenant_id,
                role_id=member_role.id,
                user_id=user_id,
                actor_type=ActorType.USER,
                scope_id=tenant_id,
                scope_type="tenant",
                assigned_by=assigned_by or user_id,
            )
        )
        await self.db.flush()

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
