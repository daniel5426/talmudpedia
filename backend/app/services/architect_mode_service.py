from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import ALL_SCOPES, is_platform_admin_role, legacy_permission_to_scope
from app.db.postgres.models.identity import User
from app.db.postgres.models.rbac import RoleAssignment, RolePermission


class ArchitectMode(str, enum.Enum):
    READ_ONLY = "read_only"
    DEFAULT = "default"
    FULL_ACCESS = "full_access"


READ_ONLY_ARCHITECT_SCOPES: list[str] = sorted(
    {
        "pipelines.catalog.read",
        "pipelines.read",
        "agents.read",
        "tools.read",
        "artifacts.read",
        "models.read",
        "knowledge_stores.read",
        "credentials.read",
        "threads.read",
        "apps.read",
    }
)

DEFAULT_ARCHITECT_SCOPES: list[str] = sorted(
    set(READ_ONLY_ARCHITECT_SCOPES).union(
        {
            "pipelines.write",
            "agents.write",
            "agents.execute",
            "agents.run_tests",
            "tools.write",
            "artifacts.write",
            "models.write",
            "knowledge_stores.write",
        }
    )
)

FULL_ACCESS_ARCHITECT_SCOPES: list[str] = sorted(set(ALL_SCOPES))

_MODE_ORDER: dict[ArchitectMode, int] = {
    ArchitectMode.READ_ONLY: 0,
    ArchitectMode.DEFAULT: 1,
    ArchitectMode.FULL_ACCESS: 2,
}


class ArchitectModeError(ValueError):
    pass


class ArchitectModeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_effective_mode(
        self,
        *,
        organization_id: UUID,
        user_id: UUID | None,
        requested_mode: str | None,
    ) -> ArchitectMode:
        requested = self.parse_mode(requested_mode)
        max_mode = await self.resolve_user_max_mode(organization_id=organization_id, user_id=user_id)
        return requested if _MODE_ORDER[requested] <= _MODE_ORDER[max_mode] else max_mode

    async def resolve_user_max_mode(
        self,
        *,
        organization_id: UUID,
        user_id: UUID | None,
    ) -> ArchitectMode:
        if user_id is None:
            raise ArchitectModeError("platform-architect requires an initiating user")

        scopes = await self._resolve_user_scopes(organization_id=organization_id, user_id=user_id)
        if "*" in scopes:
            return ArchitectMode.FULL_ACCESS
        if scopes.intersection({"roles.write", "roles.assign", "tenants.write", "api_keys.write", "credentials.write"}):
            return ArchitectMode.FULL_ACCESS
        if scopes.intersection(
            {
                "pipelines.write",
                "agents.write",
                "tools.write",
                "artifacts.write",
                "models.write",
                "knowledge_stores.write",
            }
        ):
            return ArchitectMode.DEFAULT
        return ArchitectMode.READ_ONLY

    @staticmethod
    def parse_mode(raw_mode: str | None) -> ArchitectMode:
        raw = str(raw_mode or "").strip().lower()
        if not raw:
            return ArchitectMode.DEFAULT
        try:
            return ArchitectMode(raw)
        except ValueError as exc:
            raise ArchitectModeError(f"Unsupported architect_mode '{raw_mode}'") from exc

    @staticmethod
    def scopes_for_mode(mode: ArchitectMode) -> list[str]:
        if mode == ArchitectMode.READ_ONLY:
            return list(READ_ONLY_ARCHITECT_SCOPES)
        if mode == ArchitectMode.DEFAULT:
            return list(DEFAULT_ARCHITECT_SCOPES)
        return list(FULL_ACCESS_ARCHITECT_SCOPES)

    async def _resolve_user_scopes(self, *, organization_id: UUID, user_id: UUID) -> set[str]:
        user = await self.db.get(User, user_id)
        if user is None:
            return set()
        if is_platform_admin_role(getattr(user, "role", None)):
            return {"*"}

        assignment_res = await self.db.execute(
            select(RoleAssignment).where(
                RoleAssignment.organization_id == organization_id,
                RoleAssignment.user_id == user_id,
            )
        )
        assignments = list(assignment_res.scalars().all())
        role_ids = {assignment.role_id for assignment in assignments if assignment.role_id is not None}
        scopes: set[str] = set()
        if role_ids:
            perms_res = await self.db.execute(
                select(RolePermission).where(RolePermission.role_id.in_(list(role_ids)))
            )
            for perm in perms_res.scalars().all():
                scope_key = getattr(perm, "scope_key", None)
                if scope_key:
                    scopes.add(str(scope_key))
                    continue
                mapped = legacy_permission_to_scope(
                    getattr(getattr(perm, "resource_type", None), "value", getattr(perm, "resource_type", None)),
                    getattr(getattr(perm, "action", None), "value", getattr(perm, "action", None)),
                )
                if mapped:
                    scopes.add(mapped)
        return scopes
