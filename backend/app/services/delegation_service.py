from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.identity import User, OrgMembership, OrgRole
from app.db.postgres.models.agents import Agent
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

PLATFORM_ARCHITECT_SCOPES = {
    "pipelines.catalog.read",
    "pipelines.write",
    "agents.write",
    "tools.write",
    "artifacts.write",
    "agents.execute",
    "agents.run_tests",
}

DEFAULT_AGENT_RUN_SCOPES = {
    "agents.execute",
}

TENANT_ADMIN_SCOPES = {
    "pipelines.catalog.read",
    "pipelines.write",
    "agents.write",
    "tools.write",
    "artifacts.write",
    "agents.execute",
    "agents.run_tests",
}

TENANT_MEMBER_SCOPES = {
    "pipelines.catalog.read",
    "agents.execute",
}


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
        if str(user.role).lower() == "admin":
            return {"*"}

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
            return set(TENANT_ADMIN_SCOPES)
        return set(TENANT_MEMBER_SCOPES)

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
            raise ValueError("Workload principal not found")
        if principal.tenant_id != tenant_id:
            raise ValueError("Principal tenant mismatch")

        policy = await self.identity.get_latest_policy(principal_id)
        if policy is None:
            raise ValueError("No workload scope policy found")

        requested = set(requested_scopes)
        approved = set(policy.approved_scopes or []) if policy.status == WorkloadPolicyStatus.APPROVED else set()
        user_scopes = await self._resolve_user_scopes(tenant_id, initiator_user_id)
        effective = self._intersect_scopes(user_scopes, approved, requested)

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

        approval_required = policy.status != WorkloadPolicyStatus.APPROVED
        return grant, approval_required

    async def create_agent_run_grant(
        self,
        *,
        agent: Agent,
        initiator_user_id: UUID | None,
        run_id: UUID | None,
        requested_scopes: Iterable[str] | None = None,
    ) -> tuple[WorkloadPrincipal, DelegationGrant, bool]:
        scopes = set(requested_scopes or DEFAULT_AGENT_RUN_SCOPES)
        if agent.slug == "platform-architect":
            scopes.update(PLATFORM_ARCHITECT_SCOPES)

        principal = await self.identity.ensure_principal(
            tenant_id=agent.tenant_id,
            slug=f"agent:{agent.slug}",
            name=f"Agent Workload ({agent.slug})",
            principal_type=WorkloadPrincipalType.AGENT,
            created_by=initiator_user_id,
            requested_scopes=scopes,
            auto_approve_system=False,
        )
        await self.identity.ensure_binding(
            tenant_id=agent.tenant_id,
            principal_id=principal.id,
            resource_type=WorkloadResourceType.AGENT,
            resource_id=str(agent.id),
        )

        grant, approval_required = await self.create_delegation_grant(
            tenant_id=agent.tenant_id,
            principal_id=principal.id,
            initiator_user_id=initiator_user_id,
            requested_scopes=scopes,
            run_id=run_id,
        )
        return principal, grant, approval_required
