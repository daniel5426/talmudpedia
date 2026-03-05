from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import (
    DEFAULT_AGENT_RUN_SCOPES,
    PLATFORM_ARCHITECT_SCOPE_PROFILE_V1,
    is_platform_admin_role,
    normalize_scope_list,
)
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import User
from app.db.postgres.models.security import (
    WorkloadPolicyStatus,
    WorkloadPrincipal,
    WorkloadPrincipalType,
    WorkloadResourceType,
    WorkloadScopePolicy,
)
from app.services.workload_identity_service import WorkloadIdentityService


class WorkloadProvisioningService:
    """Provisioning-time setup for agent workload principals and scope policies."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.identity = WorkloadIdentityService(db)

    def resolve_agent_requested_scopes(
        self,
        *,
        agent: Agent,
        requested_scopes: Iterable[str] | None = None,
    ) -> list[str]:
        requested = set(requested_scopes or [])

        profile = str(getattr(agent, "workload_scope_profile", "") or "").strip().lower()
        if profile == "platform_architect_v1" or str(getattr(agent, "slug", "")) == "platform-architect":
            requested.update(PLATFORM_ARCHITECT_SCOPE_PROFILE_V1)
        else:
            requested.update(DEFAULT_AGENT_RUN_SCOPES)

        overrides = getattr(agent, "workload_scope_overrides", None)
        if isinstance(overrides, list):
            requested.update(str(scope) for scope in overrides if str(scope).strip())

        return normalize_scope_list(list(requested))

    async def provision_agent_policy(
        self,
        *,
        agent: Agent,
        actor_user_id: UUID | None,
        requested_scopes: Iterable[str] | None = None,
    ) -> tuple[WorkloadPrincipal, WorkloadScopePolicy]:
        scopes = self.resolve_agent_requested_scopes(agent=agent, requested_scopes=requested_scopes)

        principal = await self.identity.ensure_principal(
            tenant_id=agent.tenant_id,
            slug=f"agent:{agent.slug}",
            name=f"Agent Workload ({agent.slug})",
            principal_type=WorkloadPrincipalType.AGENT,
            created_by=actor_user_id,
            requested_scopes=scopes,
            auto_approve_system=False,
        )
        await self.identity.ensure_binding(
            tenant_id=agent.tenant_id,
            principal_id=principal.id,
            resource_type=WorkloadResourceType.AGENT,
            resource_id=str(agent.id),
        )

        existing = await self.identity.get_latest_policy(principal.id)
        normalized_existing = normalize_scope_list(list((existing.requested_scopes or []) if existing else []))

        approver_id = await self._resolve_auto_approver(actor_user_id)
        if existing and normalized_existing == scopes:
            if existing.status == WorkloadPolicyStatus.APPROVED:
                return principal, existing
            if existing.status == WorkloadPolicyStatus.PENDING and approver_id is None:
                return principal, existing
            if existing.status == WorkloadPolicyStatus.PENDING and approver_id is not None:
                new_policy = WorkloadScopePolicy(
                    principal_id=principal.id,
                    requested_scopes=scopes,
                    approved_scopes=scopes,
                    status=WorkloadPolicyStatus.APPROVED,
                    approved_by=approver_id,
                    approved_at=datetime.now(timezone.utc),
                    version=int(existing.version or 0) + 1,
                )
                self.db.add(new_policy)
                await self.db.flush()
                return principal, new_policy

        if approver_id is not None:
            status = WorkloadPolicyStatus.APPROVED
            approved_scopes = scopes
            approved_by = approver_id
            approved_at = datetime.now(timezone.utc)
        else:
            status = WorkloadPolicyStatus.PENDING
            approved_scopes = []
            approved_by = None
            approved_at = None

        next_version = 1
        if existing is not None:
            next_version = int(existing.version or 0) + 1

        policy = WorkloadScopePolicy(
            principal_id=principal.id,
            requested_scopes=scopes,
            approved_scopes=approved_scopes,
            status=status,
            approved_by=approved_by,
            approved_at=approved_at,
            version=next_version,
        )
        self.db.add(policy)
        await self.db.flush()
        return principal, policy

    async def _resolve_auto_approver(self, actor_user_id: UUID | None) -> UUID | None:
        if actor_user_id is None:
            return None
        actor = await self.db.get(User, actor_user_id)
        if actor is None:
            return None
        if is_platform_admin_role(getattr(actor, "role", None)):
            return actor.id
        return None
