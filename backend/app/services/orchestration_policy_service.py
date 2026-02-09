from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus
from app.db.postgres.models.orchestration import OrchestratorPolicy, OrchestratorTargetAllowlist


DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_FANOUT = 8
DEFAULT_MAX_CHILDREN_TOTAL = 32
DEFAULT_JOIN_TIMEOUT_S = 60
DEFAULT_FAILURE_POLICY = "best_effort"
ORCHESTRATION_SURFACE_OPTION_A = "option_a_graphspec_v2"
ORCHESTRATION_SURFACE_OPTION_B = "option_b_runtime_primitives"


class OrchestrationPolicyError(PermissionError):
    pass


@dataclass
class PolicySnapshot:
    tenant_id: UUID
    orchestrator_agent_id: UUID
    enforce_published_only: bool = True
    default_failure_policy: str = DEFAULT_FAILURE_POLICY
    max_depth: int = DEFAULT_MAX_DEPTH
    max_fanout: int = DEFAULT_MAX_FANOUT
    max_children_total: int = DEFAULT_MAX_CHILDREN_TOTAL
    join_timeout_s: int = DEFAULT_JOIN_TIMEOUT_S
    allowed_scope_subset: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "orchestrator_agent_id": str(self.orchestrator_agent_id),
            "enforce_published_only": self.enforce_published_only,
            "default_failure_policy": self.default_failure_policy,
            "max_depth": self.max_depth,
            "max_fanout": self.max_fanout,
            "max_children_total": self.max_children_total,
            "join_timeout_s": self.join_timeout_s,
            "allowed_scope_subset": list(self.allowed_scope_subset or []),
        }


class OrchestrationPolicyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_policy(self, tenant_id: UUID, orchestrator_agent_id: UUID) -> PolicySnapshot:
        result = await self.db.execute(
            select(OrchestratorPolicy).where(
                OrchestratorPolicy.tenant_id == tenant_id,
                OrchestratorPolicy.orchestrator_agent_id == orchestrator_agent_id,
                OrchestratorPolicy.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return PolicySnapshot(
                tenant_id=tenant_id,
                orchestrator_agent_id=orchestrator_agent_id,
            )

        return PolicySnapshot(
            tenant_id=tenant_id,
            orchestrator_agent_id=orchestrator_agent_id,
            enforce_published_only=bool(row.enforce_published_only),
            default_failure_policy=row.default_failure_policy or DEFAULT_FAILURE_POLICY,
            max_depth=row.max_depth or DEFAULT_MAX_DEPTH,
            max_fanout=row.max_fanout or DEFAULT_MAX_FANOUT,
            max_children_total=row.max_children_total or DEFAULT_MAX_CHILDREN_TOTAL,
            join_timeout_s=row.join_timeout_s or DEFAULT_JOIN_TIMEOUT_S,
            allowed_scope_subset=list(row.allowed_scope_subset or []),
        )

    async def assert_target_allowed(
        self,
        *,
        tenant_id: UUID,
        orchestrator_agent_id: UUID,
        target: Agent,
        policy: PolicySnapshot,
    ) -> None:
        if policy.enforce_published_only:
            target_status = target.status.value if hasattr(target.status, "value") else str(target.status)
            if target_status != AgentStatus.published.value:
                raise OrchestrationPolicyError("Target agent is not published")

        allowlist_res = await self.db.execute(
            select(OrchestratorTargetAllowlist).where(
                OrchestratorTargetAllowlist.tenant_id == tenant_id,
                OrchestratorTargetAllowlist.orchestrator_agent_id == orchestrator_agent_id,
                OrchestratorTargetAllowlist.is_active.is_(True),
            )
        )
        allowlist = list(allowlist_res.scalars().all())
        if not allowlist:
            raise OrchestrationPolicyError("Orchestrator has no target allowlist entries")

        target_slug = str(target.slug)
        target_id = target.id

        allowed = any(
            (entry.target_agent_id and entry.target_agent_id == target_id)
            or (entry.target_agent_slug and entry.target_agent_slug == target_slug)
            for entry in allowlist
        )
        if not allowed:
            raise OrchestrationPolicyError("Target agent is not allowlisted for this orchestrator")

    def assert_scope_subset(self, *, scope_subset: list[str], policy: PolicySnapshot, effective_scopes: list[str]) -> None:
        requested = set(scope_subset or [])
        if not requested:
            raise OrchestrationPolicyError("scope_subset is required")

        effective = set(effective_scopes or [])
        if not requested.issubset(effective):
            raise OrchestrationPolicyError("scope_subset is not within caller effective scopes")

        policy_subset = set(policy.allowed_scope_subset or [])
        if policy_subset and not requested.issubset(policy_subset):
            raise OrchestrationPolicyError("scope_subset exceeds orchestrator policy capability set")

    async def assert_spawn_limits(
        self,
        *,
        policy: PolicySnapshot,
        root_run_id: UUID,
        parent_run_id: UUID,
        parent_depth: int,
        requested_children: int,
    ) -> None:
        next_depth = int(parent_depth or 0) + 1
        if next_depth > policy.max_depth:
            raise OrchestrationPolicyError(
                f"max_depth exceeded ({next_depth} > {policy.max_depth})"
            )

        if requested_children < 1:
            raise OrchestrationPolicyError("requested_children must be >= 1")

        if requested_children > policy.max_fanout:
            raise OrchestrationPolicyError(
                f"max_fanout exceeded ({requested_children} > {policy.max_fanout})"
            )

        sibling_count = await self.db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.parent_run_id == parent_run_id)
        )
        sibling_count = int(sibling_count or 0)
        if sibling_count + requested_children > policy.max_fanout:
            raise OrchestrationPolicyError(
                f"max_fanout exceeded for parent ({sibling_count + requested_children} > {policy.max_fanout})"
            )

        total_children = await self.db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.root_run_id == root_run_id,
                AgentRun.parent_run_id.is_not(None),
            )
        )
        total_children = int(total_children or 0)
        if total_children + requested_children > policy.max_children_total:
            raise OrchestrationPolicyError(
                f"max_children_total exceeded ({total_children + requested_children} > {policy.max_children_total})"
            )


def is_orchestration_surface_enabled(
    *,
    surface: str,
    tenant_id: UUID | str | None,
) -> bool:
    """
    Feature-gate orchestration surfaces with optional tenant allowlists.

    Env flags:
    - ORCHESTRATION_OPTION_A_ENABLED (default: true)
    - ORCHESTRATION_OPTION_A_TENANT_ALLOWLIST / ORCHESTRATION_OPTION_A_TENANTS
    - ORCHESTRATION_OPTION_B_ENABLED (default: true)
    - ORCHESTRATION_OPTION_B_TENANT_ALLOWLIST / ORCHESTRATION_OPTION_B_TENANTS
    """
    if surface == ORCHESTRATION_SURFACE_OPTION_A:
        enabled = _read_bool_env("ORCHESTRATION_OPTION_A_ENABLED", default=True)
        allowlist = _read_tenant_allowlist_env(
            "ORCHESTRATION_OPTION_A_TENANT_ALLOWLIST",
            "ORCHESTRATION_OPTION_A_TENANTS",
        )
    elif surface == ORCHESTRATION_SURFACE_OPTION_B:
        enabled = _read_bool_env("ORCHESTRATION_OPTION_B_ENABLED", default=True)
        allowlist = _read_tenant_allowlist_env(
            "ORCHESTRATION_OPTION_B_TENANT_ALLOWLIST",
            "ORCHESTRATION_OPTION_B_TENANTS",
        )
    else:
        return False

    if not enabled:
        return False
    if not allowlist:
        return True
    if tenant_id is None:
        return False
    return str(tenant_id) in allowlist


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _read_tenant_allowlist_env(*names: str) -> set[str]:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        values = {
            item.strip()
            for item in str(raw).split(",")
            if item and item.strip()
        }
        return values
    return set()
