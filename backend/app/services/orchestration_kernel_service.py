from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.security import DelegationGrant
from app.db.postgres.models.orchestration import OrchestrationGroup, OrchestrationGroupMember
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService
from app.services.orchestration_lineage_service import OrchestrationLineageService
from app.services.orchestration_policy_service import (
    OrchestrationPolicyError,
    OrchestrationPolicyService,
)


WORKLOAD_AUDIENCE = "talmudpedia-internal-api"


class OrchestrationKernelService:
    """
    Canonical orchestration kernel used by both graph-native orchestration
    and runtime primitive/tool surfaces.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.policy = OrchestrationPolicyService(db)
        self.lineage = OrchestrationLineageService(db)

    async def spawn_run(
        self,
        *,
        caller_run_id: UUID,
        parent_node_id: str | None,
        target_agent_id: UUID | None,
        target_agent_slug: str | None,
        mapped_input_payload: dict[str, Any] | None,
        failure_policy: str | None,
        timeout_s: int | None,
        scope_subset: list[str],
        idempotency_key: str,
        start_background: bool = True,
        orchestration_group_id: UUID | None = None,
    ) -> dict[str, Any]:
        caller_run = await self._require_run(caller_run_id)
        target = await self._resolve_target(
            tenant_id=caller_run.tenant_id,
            target_agent_id=target_agent_id,
            target_agent_slug=target_agent_slug,
        )
        policy = await self.policy.get_policy(caller_run.tenant_id, caller_run.agent_id)

        await self.policy.assert_target_allowed(
            tenant_id=caller_run.tenant_id,
            orchestrator_agent_id=caller_run.agent_id,
            target=target,
            policy=policy,
        )

        await self.policy.assert_spawn_limits(
            policy=policy,
            root_run_id=caller_run.root_run_id or caller_run.id,
            parent_run_id=caller_run.id,
            parent_depth=int(caller_run.depth or 0),
            requested_children=1,
        )

        caller_grant = await self._require_delegation_grant(caller_run)
        self.policy.assert_scope_subset(
            scope_subset=scope_subset,
            policy=policy,
            effective_scopes=list(caller_grant.effective_scopes or []),
        )

        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            raise ValueError("idempotency_key is required")

        existing_res = await self.db.execute(
            select(AgentRun).where(
                AgentRun.parent_run_id == caller_run.id,
                AgentRun.spawn_key == normalized_key,
            )
        )
        existing = existing_res.scalar_one_or_none()
        if existing is not None:
            return {
                "spawned_run_ids": [str(existing.id)],
                "accepted_policy_snapshot": policy.as_dict(),
                "effective_scope_subset": sorted(set(scope_subset)),
                "lineage": self._serialize_lineage(existing),
                "idempotent": True,
            }

        child_grant = await self._mint_child_grant(
            caller_run=caller_run,
            requested_scopes=scope_subset,
        )
        child_token = await self._mint_child_token(child_grant=child_grant, scope_subset=scope_subset)

        child_input = self._build_child_input_payload(
            caller_run=caller_run,
            child_grant=child_grant,
            child_token=child_token,
            mapped_input_payload=mapped_input_payload,
            parent_node_id=parent_node_id,
            scope_subset=scope_subset,
            idempotency_key=normalized_key,
            orchestration_group_id=orchestration_group_id,
        )

        executor = AgentExecutorService(db=self.db)
        child_run_id = await executor.start_run(
            agent_id=target.id,
            input_params=child_input,
            user_id=caller_run.initiator_user_id or caller_run.user_id,
            background=start_background,
            requested_scopes=scope_subset,
            root_run_id=caller_run.root_run_id or caller_run.id,
            parent_run_id=caller_run.id,
            parent_node_id=parent_node_id,
            depth=int(caller_run.depth or 0) + 1,
            spawn_key=normalized_key,
            orchestration_group_id=orchestration_group_id,
        )

        child_grant.run_id = child_run_id
        await self.db.commit()

        child_run = await self._require_run(child_run_id)
        return {
            "spawned_run_ids": [str(child_run_id)],
            "accepted_policy_snapshot": policy.as_dict(),
            "effective_scope_subset": sorted(set(scope_subset)),
            "lineage": self._serialize_lineage(child_run),
            "idempotent": False,
            "failure_policy": failure_policy or policy.default_failure_policy,
            "timeout_s": timeout_s,
        }

    async def spawn_group(
        self,
        *,
        caller_run_id: UUID,
        parent_node_id: str | None,
        targets: list[dict[str, Any]],
        failure_policy: str | None,
        join_mode: str,
        quorum_threshold: int | None,
        timeout_s: int | None,
        scope_subset: list[str],
        idempotency_key_prefix: str,
        start_background: bool = True,
    ) -> dict[str, Any]:
        caller_run = await self._require_run(caller_run_id)
        policy = await self.policy.get_policy(caller_run.tenant_id, caller_run.agent_id)

        if not targets:
            raise ValueError("targets is required")

        normalized_join_mode = self._normalize_join_mode(join_mode)
        if normalized_join_mode is None:
            raise ValueError(f"Unsupported join_mode '{join_mode}'")
        if normalized_join_mode == "quorum":
            if quorum_threshold is None or int(quorum_threshold) < 1:
                raise ValueError("quorum_threshold is required for quorum join_mode")

        await self.policy.assert_spawn_limits(
            policy=policy,
            root_run_id=caller_run.root_run_id or caller_run.id,
            parent_run_id=caller_run.id,
            parent_depth=int(caller_run.depth or 0),
            requested_children=len(targets),
        )

        caller_grant = await self._require_delegation_grant(caller_run)
        self.policy.assert_scope_subset(
            scope_subset=scope_subset,
            policy=policy,
            effective_scopes=list(caller_grant.effective_scopes or []),
        )

        group = OrchestrationGroup(
            tenant_id=caller_run.tenant_id,
            orchestrator_run_id=caller_run.id,
            parent_node_id=parent_node_id,
            failure_policy=failure_policy or policy.default_failure_policy,
            join_mode=normalized_join_mode,
            quorum_threshold=quorum_threshold,
            timeout_s=timeout_s or policy.join_timeout_s,
            status="running",
            policy_snapshot=policy.as_dict(),
        )
        self.db.add(group)
        await self.db.flush()

        spawned: list[str] = []
        for idx, target in enumerate(targets):
            key = f"{idempotency_key_prefix}:{idx}"
            result = await self.spawn_run(
                caller_run_id=caller_run_id,
                parent_node_id=parent_node_id,
                target_agent_id=self._as_uuid(target.get("target_agent_id")),
                target_agent_slug=target.get("target_agent_slug"),
                mapped_input_payload=target.get("mapped_input_payload") if isinstance(target.get("mapped_input_payload"), dict) else {},
                failure_policy=failure_policy,
                timeout_s=timeout_s,
                scope_subset=scope_subset,
                idempotency_key=key,
                start_background=start_background,
                orchestration_group_id=group.id,
            )
            run_id = result["spawned_run_ids"][0]
            spawned.append(run_id)

            member = OrchestrationGroupMember(
                group_id=group.id,
                run_id=UUID(run_id),
                ordinal=idx,
                status="queued",
            )
            self.db.add(member)

        await self.db.commit()

        return {
            "orchestration_group_id": str(group.id),
            "spawned_run_ids": spawned,
            "accepted_policy_snapshot": policy.as_dict(),
            "effective_scope_subset": sorted(set(scope_subset)),
            "lineage": {
                "root_run_id": str(caller_run.root_run_id or caller_run.id),
                "parent_run_id": str(caller_run.id),
                "parent_node_id": parent_node_id,
                "depth": int(caller_run.depth or 0) + 1,
            },
            "join_mode": group.join_mode,
            "quorum_threshold": group.quorum_threshold,
            "timeout_s": group.timeout_s,
        }

    async def join(
        self,
        *,
        caller_run_id: UUID,
        orchestration_group_id: UUID,
        mode: str | None,
        quorum_threshold: int | None,
        timeout_s: int | None,
    ) -> dict[str, Any]:
        _ = await self._require_run(caller_run_id)
        group = await self.db.get(OrchestrationGroup, orchestration_group_id)
        if group is None:
            raise ValueError("Orchestration group not found")

        members_res = await self.db.execute(
            select(OrchestrationGroupMember).where(OrchestrationGroupMember.group_id == group.id)
        )
        members = list(members_res.scalars().all())
        if not members:
            return {
                "group_id": str(group.id),
                "status": "empty",
                "complete": True,
                "success_count": 0,
                "failure_count": 0,
                "running_count": 0,
            }

        run_ids = [m.run_id for m in members]
        runs_res = await self.db.execute(select(AgentRun).where(AgentRun.id.in_(run_ids)))
        runs = {r.id: r for r in runs_res.scalars().all()}

        success_states = {RunStatus.completed.value}
        failed_states = {RunStatus.failed.value, RunStatus.cancelled.value}
        running_states = {RunStatus.queued.value, RunStatus.running.value, RunStatus.paused.value}

        success = 0
        failed = 0
        running = 0
        total_members = len(members)

        for member in members:
            run = runs.get(member.run_id)
            if run is None:
                member.status = "missing"
                failed += 1
                continue

            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            member.status = status
            if status in success_states:
                success += 1
            elif status in failed_states:
                failed += 1
            elif status in running_states:
                running += 1
            else:
                running += 1

        effective_mode = self._normalize_join_mode(mode or group.join_mode)
        if effective_mode is None:
            raise ValueError(f"Unsupported join mode '{mode or group.join_mode}'")

        effective_failure_policy = str(group.failure_policy or "best_effort")
        if effective_mode == "best_effort" and effective_failure_policy == "fail_fast":
            effective_mode = "fail_fast"

        effective_quorum = quorum_threshold if quorum_threshold is not None else group.quorum_threshold
        effective_timeout = timeout_s if timeout_s is not None else group.timeout_s

        complete = False
        outcome = "running"
        cancellation_reason: str | None = None

        if effective_mode == "first_success":
            if success >= 1:
                complete = True
                outcome = "completed"
                cancellation_reason = "join_first_success"
            elif running == 0:
                complete = True
                outcome = "failed"
        elif effective_mode == "quorum":
            if not effective_quorum or effective_quorum < 1:
                raise ValueError("quorum_threshold is required for quorum mode")
            if effective_quorum > total_members:
                raise ValueError("quorum_threshold cannot exceed group size")
            if success >= effective_quorum:
                complete = True
                outcome = "completed"
                cancellation_reason = "join_quorum_reached"
            elif success + running < effective_quorum:
                complete = True
                outcome = "failed"
        elif effective_mode == "fail_fast":
            if failed > 0:
                complete = True
                outcome = "failed"
                cancellation_reason = "join_fail_fast"
            elif running == 0:
                complete = True
                outcome = "completed" if failed == 0 else "failed"
        else:
            if running == 0:
                complete = True
                outcome = "completed" if failed == 0 else "completed_with_errors"

        started_at = group.started_at
        if started_at is not None and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if (
            not complete
            and effective_timeout is not None
            and int(effective_timeout) > 0
        ):
            deadline = (started_at or now) + timedelta(seconds=int(effective_timeout))
            if now >= deadline:
                complete = True
                outcome = "timed_out"
                cancellation_reason = "join_timed_out"

        cancelled_run_ids: list[str] = []
        if complete and cancellation_reason:
            cancelled_run_ids = await self._cancel_active_group_members(
                members=members,
                runs=runs,
                reason=cancellation_reason,
            )
            if cancelled_run_ids:
                failed += len(cancelled_run_ids)
                running = max(0, running - len(cancelled_run_ids))

        group.status = outcome if complete else "running"
        if complete:
            group.completed_at = now

        await self.db.commit()

        return {
            "group_id": str(group.id),
            "status": group.status,
            "complete": complete,
            "mode": effective_mode,
            "failure_policy": effective_failure_policy,
            "quorum_threshold": effective_quorum,
            "timeout_s": effective_timeout,
            "success_count": success,
            "failure_count": failed,
            "running_count": running,
            "member_run_ids": [str(m.run_id) for m in members],
            "cancellation_propagated": {
                "count": len(cancelled_run_ids),
                "run_ids": cancelled_run_ids,
                "reason": cancellation_reason,
            },
        }

    async def cancel_subtree(
        self,
        *,
        caller_run_id: UUID,
        run_id: UUID,
        include_root: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any]:
        _ = await self._require_run(caller_run_id)
        root = await self._require_run(run_id)

        frontier = [root.id]
        subtree_ids: set[UUID] = set()
        while frontier:
            current = frontier.pop()
            subtree_ids.add(current)
            children_res = await self.db.execute(
                select(AgentRun.id).where(AgentRun.parent_run_id == current)
            )
            for child_id in children_res.scalars().all():
                if child_id not in subtree_ids:
                    frontier.append(child_id)

        if not include_root:
            subtree_ids.discard(root.id)

        runs_res = await self.db.execute(select(AgentRun).where(AgentRun.id.in_(list(subtree_ids) or [UUID(int=0)])))
        runs = list(runs_res.scalars().all())

        changed = 0
        cancelled_ids: list[str] = []
        for item in runs:
            status = item.status.value if hasattr(item.status, "value") else str(item.status)
            if status in {RunStatus.queued.value, RunStatus.running.value, RunStatus.paused.value}:
                item.status = RunStatus.cancelled
                item.error_message = reason or "cancelled_by_orchestration"
                item.completed_at = datetime.now(timezone.utc)
                changed += 1
                cancelled_ids.append(str(item.id))

        await self.db.commit()

        return {
            "run_id": str(run_id),
            "cancelled_count": changed,
            "cancelled_run_ids": cancelled_ids,
            "scanned_count": len(runs),
            "include_root": include_root,
            "reason": reason or "cancelled_by_orchestration",
        }

    async def evaluate_and_replan(
        self,
        *,
        caller_run_id: UUID,
        run_id: UUID,
    ) -> dict[str, Any]:
        _ = await self._require_run(caller_run_id)
        _ = await self._require_run(run_id)

        children_res = await self.db.execute(
            select(AgentRun).where(AgentRun.parent_run_id == run_id)
        )
        children = list(children_res.scalars().all())

        failed_statuses = {RunStatus.failed.value, RunStatus.cancelled.value}
        failed_children = [
            item for item in children
            if (item.status.value if hasattr(item.status, "value") else str(item.status)) in failed_statuses
        ]

        return {
            "run_id": str(run_id),
            "needs_replan": len(failed_children) > 0,
            "failed_children": [str(item.id) for item in failed_children],
            "failed_count": len(failed_children),
            "total_children": len(children),
            "suggested_action": "replan" if failed_children else "continue",
        }

    async def query_tree(self, *, run_id: UUID) -> dict[str, Any]:
        return await self.lineage.query_tree(run_id)

    async def _require_run(self, run_id: UUID) -> AgentRun:
        row = await self.db.get(AgentRun, run_id)
        if row is None:
            raise ValueError("Run not found")
        return row

    async def _resolve_target(
        self,
        *,
        tenant_id: UUID,
        target_agent_id: UUID | None,
        target_agent_slug: str | None,
    ) -> Agent:
        if target_agent_id is not None:
            target = await self.db.get(Agent, target_agent_id)
            if target is None or target.tenant_id != tenant_id:
                raise ValueError("Target agent not found")
            return target

        if target_agent_slug:
            res = await self.db.execute(
                select(Agent).where(
                    Agent.tenant_id == tenant_id,
                    Agent.slug == target_agent_slug,
                )
            )
            target = res.scalar_one_or_none()
            if target is not None:
                return target

        raise ValueError("target_agent_id or target_agent_slug is required")

    async def _require_delegation_grant(self, run: AgentRun) -> DelegationGrant:
        if run.delegation_grant_id is None:
            raise OrchestrationPolicyError("Caller run has no delegation grant context")

        grant = await self.db.get(DelegationGrant, run.delegation_grant_id)
        if grant is None:
            raise OrchestrationPolicyError("Caller delegation grant not found")
        return grant

    async def _mint_child_grant(self, *, caller_run: AgentRun, requested_scopes: list[str]) -> DelegationGrant:
        if caller_run.workload_principal_id is None:
            raise OrchestrationPolicyError("Caller run has no workload principal context")

        delegation = DelegationService(self.db)
        child_grant, approval_required = await delegation.create_delegation_grant(
            tenant_id=caller_run.tenant_id,
            principal_id=caller_run.workload_principal_id,
            initiator_user_id=caller_run.initiator_user_id or caller_run.user_id,
            requested_scopes=requested_scopes,
            run_id=None,
        )
        if approval_required:
            raise OrchestrationPolicyError("Delegation policy approval required for child scope minting")
        await self.db.flush()
        return child_grant

    async def _mint_child_token(self, *, child_grant: DelegationGrant, scope_subset: list[str]) -> str:
        broker = TokenBrokerService(self.db)
        token, _payload = await broker.mint_workload_token(
            grant_id=child_grant.id,
            audience=WORKLOAD_AUDIENCE,
            scope_subset=scope_subset,
        )
        await self.db.flush()
        return token

    def _build_child_input_payload(
        self,
        *,
        caller_run: AgentRun,
        child_grant: DelegationGrant,
        child_token: str,
        mapped_input_payload: dict[str, Any] | None,
        parent_node_id: str | None,
        scope_subset: list[str],
        idempotency_key: str,
        orchestration_group_id: UUID | None,
    ) -> dict[str, Any]:
        payload = dict(mapped_input_payload or {})
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        context = dict(context)

        context["tenant_id"] = str(caller_run.tenant_id)
        context["user_id"] = str(caller_run.initiator_user_id or caller_run.user_id) if (caller_run.initiator_user_id or caller_run.user_id) else None
        context["grant_id"] = str(child_grant.id)
        context["principal_id"] = str(caller_run.workload_principal_id) if caller_run.workload_principal_id else None
        context["initiator_user_id"] = str(caller_run.initiator_user_id) if caller_run.initiator_user_id else None
        context["requested_scopes"] = list(scope_subset)
        context["token"] = child_token
        context["root_run_id"] = str(caller_run.root_run_id or caller_run.id)
        context["parent_run_id"] = str(caller_run.id)
        context["parent_node_id"] = parent_node_id
        context["depth"] = int(caller_run.depth or 0) + 1
        context["spawn_key"] = idempotency_key
        if orchestration_group_id is not None:
            context["orchestration_group_id"] = str(orchestration_group_id)

        payload["context"] = context

        state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        state = dict(state)
        state["context"] = dict(context)
        payload["state"] = state

        payload.setdefault("messages", [])
        return payload

    async def _cancel_active_group_members(
        self,
        *,
        members: list[OrchestrationGroupMember],
        runs: dict[UUID, AgentRun],
        reason: str,
    ) -> list[str]:
        active_states = {RunStatus.queued.value, RunStatus.running.value, RunStatus.paused.value}
        cancelled: list[str] = []
        now = datetime.now(timezone.utc)

        for member in members:
            run = runs.get(member.run_id)
            if run is None:
                continue
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status not in active_states:
                continue
            run.status = RunStatus.cancelled
            run.error_message = reason
            run.completed_at = now
            member.status = RunStatus.cancelled.value
            cancelled.append(str(run.id))
        return cancelled

    @staticmethod
    def _normalize_join_mode(value: str | None) -> str | None:
        mode = str(value or "all").strip().lower()
        aliases = {"all": "best_effort", "best_effort": "best_effort"}
        if mode in aliases:
            return aliases[mode]
        if mode in {"fail_fast", "quorum", "first_success"}:
            return mode
        return None

    @staticmethod
    def _serialize_lineage(run: AgentRun) -> dict[str, Any]:
        return {
            "root_run_id": str(run.root_run_id or run.id),
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "parent_node_id": run.parent_node_id,
            "depth": int(run.depth or 0),
            "spawn_key": run.spawn_key,
            "orchestration_group_id": str(run.orchestration_group_id) if run.orchestration_group_id else None,
        }

    @staticmethod
    def _as_uuid(value: Any) -> UUID | None:
        if value in (None, ""):
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except Exception:
            return None
