from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.identity import User, OrgMembership, OrgRole
from app.db.postgres.models.rbac import RoleAssignment, RolePermission
from app.db.postgres.models.agents import Agent
from app.core.scope_registry import (
    DEFAULT_AGENT_RUN_SCOPES,
    legacy_permission_to_scope,
    is_platform_admin_role,
    PLATFORM_ARCHITECT_SCOPE_PROFILE_V1,
    TENANT_DEFAULT_ROLE_SCOPES,
)
from app.db.postgres.models.security import (
    DelegationGrant,
    DelegationGrantStatus,
    WorkloadPrincipal,
    WorkloadPrincipalType,
    WorkloadPolicyStatus,
    WorkloadResourceType,
)
from app.services.workload_identity_service import WorkloadIdentityService

DELEGATION_GRANT_TTL_MINUTES = 15


class DelegationPolicyError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DelegationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.identity = WorkloadIdentityService(db)

    async def _resolve_user_scopes(self, tenant_id: UUID, user_id: UUID | None) -> set[str]:
        if user_id is None:
            return set()

        user = await self.db.get(User, user_id)
        if user is None:
            return set()
        if is_platform_admin_role(getattr(user, "role", None)):
            return {"*"}

        assignment_res = await self.db.execute(
            select(RoleAssignment).where(
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.user_id == user_id,
            )
        )
        assignments = list(assignment_res.scalars().all())
        role_ids = {a.role_id for a in assignments if a.role_id is not None}
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
            if scopes:
                return scopes

        # Legacy fallback while old tenants are being migrated/reset.
        membership_res = await self.db.execute(
            select(OrgMembership).where(
                OrgMembership.tenant_id == tenant_id,
                OrgMembership.user_id == user_id,
            )
        )
        membership = membership_res.scalar_one_or_none()
        if membership is None:
            return set()
        role_value = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
        role_value = role_value.lower()
        if role_value in {OrgRole.owner.value, OrgRole.admin.value}:
            return set(TENANT_DEFAULT_ROLE_SCOPES.get("admin", []))
        return set(TENANT_DEFAULT_ROLE_SCOPES.get("member", []))

    @staticmethod
    def _intersect_scopes(user_scopes: set[str], approved_scopes: set[str], requested_scopes: set[str]) -> set[str]:
        if "*" in user_scopes:
            return approved_scopes.intersection(requested_scopes)
        return user_scopes.intersection(approved_scopes).intersection(requested_scopes)

    async def create_delegation_grant(
        self,
        *,
        tenant_id: UUID,
        principal_id: UUID,
        initiator_user_id: UUID | None,
        requested_scopes: Iterable[str],
        run_id: UUID | None = None,
        expires_in_minutes: int = DELEGATION_GRANT_TTL_MINUTES,
    ) -> tuple[DelegationGrant, bool]:
        principal = await self.identity.get_principal_by_id(principal_id)
        if principal is None:
            raise DelegationPolicyError("WORKLOAD_PRINCIPAL_MISSING", "Workload principal not found")
        if principal.tenant_id != tenant_id:
            raise ValueError("Principal tenant mismatch")

        policy = await self.identity.get_latest_policy(principal_id)
        if policy is None:
            raise DelegationPolicyError("WORKLOAD_POLICY_PENDING", "No workload scope policy found")
        if policy.status == WorkloadPolicyStatus.PENDING:
            raise DelegationPolicyError("WORKLOAD_POLICY_PENDING", "Workload scope policy is pending approval")
        if policy.status != WorkloadPolicyStatus.APPROVED:
            raise DelegationPolicyError(
                "INSUFFICIENT_APPROVED_SCOPES",
                f"Workload scope policy is not approved (status={policy.status.value})",
            )

        requested = set(requested_scopes or [])
        approved = set(policy.approved_scopes or [])
        if not requested:
            requested = set(approved)
        if not requested.issubset(approved):
            raise DelegationPolicyError(
                "INSUFFICIENT_APPROVED_SCOPES",
                "Requested scopes exceed approved workload policy scopes",
            )

        if initiator_user_id is None:
            effective = approved.intersection(requested)
        else:
            user_scopes = await self._resolve_user_scopes(tenant_id, initiator_user_id)
            effective = self._intersect_scopes(user_scopes, approved, requested)
        if not effective:
            raise DelegationPolicyError(
                "INSUFFICIENT_APPROVED_SCOPES",
                "No effective scopes after applying initiator and policy bounds",
            )

        grant = DelegationGrant(
            tenant_id=tenant_id,
            principal_id=principal_id,
            initiator_user_id=initiator_user_id,
            run_id=run_id,
            requested_scopes=sorted(requested),
            effective_scopes=sorted(effective),
            status=DelegationGrantStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
        )
        self.db.add(grant)
        await self.db.flush()

        return grant, False

    async def create_agent_run_grant(
        self,
        *,
        agent: Agent,
        initiator_user_id: UUID | None,
        run_id: UUID | None,
        requested_scopes: Iterable[str] | None = None,
    ) -> tuple[WorkloadPrincipal, DelegationGrant, bool]:
        requested = set(requested_scopes or [])
        if not requested:
            profile = str(getattr(agent, "workload_scope_profile", "") or "").strip().lower()
            if profile == "platform_architect_v1" or agent.slug == "platform-architect":
                requested.update(PLATFORM_ARCHITECT_SCOPE_PROFILE_V1)
            else:
                requested.update(DEFAULT_AGENT_RUN_SCOPES)
            overrides = getattr(agent, "workload_scope_overrides", None)
            if isinstance(overrides, list):
                requested.update(str(scope) for scope in overrides if str(scope).strip())

        principal = await self.identity.get_bound_principal(
            tenant_id=agent.tenant_id,
            resource_type=WorkloadResourceType.AGENT,
            resource_id=str(agent.id),
        )
        if principal is None:
            raise DelegationPolicyError(
                "WORKLOAD_PRINCIPAL_MISSING",
                "Agent workload principal is not provisioned",
            )
        if principal.principal_type != WorkloadPrincipalType.AGENT:
            raise DelegationPolicyError(
                "WORKLOAD_PRINCIPAL_MISSING",
                "Bound workload principal type is invalid for agent runs",
            )

        grant, approval_required = await self.create_delegation_grant(
            tenant_id=agent.tenant_id,
            principal_id=principal.id,
            initiator_user_id=initiator_user_id,
            requested_scopes=requested,
            run_id=run_id,
        )
        return principal, grant, approval_required
