from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.orchestration import OrchestratorPolicy, OrchestratorTargetAllowlist
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.delegation_service import DelegationService
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.workload_identity_service import WorkloadIdentityService


async def _setup_fixture(db_session):
    tenant = Tenant(name="Join Policies Tenant", slug=f"join-policy-{uuid4().hex[:8]}")
    user = User(email=f"join-policy-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    orchestrator = Agent(
        tenant_id=tenant.id,
        name="Orchestrator",
        slug=f"orchestrator-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
    )
    target = Agent(
        tenant_id=tenant.id,
        name="Target",
        slug=f"target-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add_all([orchestrator, target])
    await db_session.flush()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug=f"agent:{orchestrator.slug}",
        name="Join Policy Principal",
        principal_type=WorkloadPrincipalType.SYSTEM,
        created_by=user.id,
        requested_scopes=["agents.execute"],
        auto_approve_system=True,
    )

    delegation = DelegationService(db_session)
    grant, _ = await delegation.create_delegation_grant(
        tenant_id=tenant.id,
        principal_id=principal.id,
        initiator_user_id=user.id,
        requested_scopes=["agents.execute"],
    )

    root_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=orchestrator.id,
        user_id=user.id,
        initiator_user_id=user.id,
        workload_principal_id=principal.id,
        delegation_grant_id=grant.id,
        status=RunStatus.running,
        input_params={"messages": [], "context": {"grant_id": str(grant.id), "principal_id": str(principal.id)}},
        depth=0,
    )
    db_session.add(root_run)
    await db_session.flush()
    root_run.root_run_id = root_run.id

    db_session.add(
        OrchestratorPolicy(
            tenant_id=tenant.id,
            orchestrator_agent_id=orchestrator.id,
            allowed_scope_subset=["agents.execute"],
            max_depth=4,
            max_fanout=16,
            max_children_total=64,
            join_timeout_s=90,
            enforce_published_only=True,
        )
    )
    db_session.add(
        OrchestratorTargetAllowlist(
            tenant_id=tenant.id,
            orchestrator_agent_id=orchestrator.id,
            target_agent_id=target.id,
        )
    )
    await db_session.commit()

    return {
        "tenant": tenant,
        "root_run": root_run,
        "target": target,
    }


async def _spawn_group(db_session, *, root_run_id: UUID, target_id: UUID, count: int = 2):
    kernel = OrchestrationKernelService(db_session)
    targets = [
        {
            "target_agent_id": str(target_id),
            "mapped_input_payload": {"input": f"task-{idx}"},
        }
        for idx in range(count)
    ]
    return await kernel.spawn_group(
        caller_run_id=root_run_id,
        parent_node_id="join_policy_test",
        targets=targets,
        failure_policy="best_effort",
        join_mode="all",
        quorum_threshold=None,
        timeout_s=60,
        scope_subset=["agents.execute"],
        idempotency_key_prefix=f"join-{uuid4().hex[:8]}",
        start_background=False,
    )


async def _set_status(db_session, run_id: str, status: RunStatus):
    row = await db_session.get(AgentRun, UUID(run_id))
    row.status = status
    if status in {RunStatus.completed, RunStatus.failed, RunStatus.cancelled}:
        row.completed_at = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_join_fail_fast_cancels_running_members(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    group = await _spawn_group(
        db_session,
        root_run_id=fx["root_run"].id,
        target_id=fx["target"].id,
        count=2,
    )
    run_ids = group["spawned_run_ids"]

    await _set_status(db_session, run_ids[0], RunStatus.failed)
    await _set_status(db_session, run_ids[1], RunStatus.running)
    await db_session.commit()

    joined = await kernel.join(
        caller_run_id=fx["root_run"].id,
        orchestration_group_id=UUID(group["orchestration_group_id"]),
        mode="fail_fast",
        quorum_threshold=None,
        timeout_s=60,
    )

    assert joined["complete"] is True
    assert joined["status"] == "failed"
    assert joined["mode"] == "fail_fast"
    assert joined["cancellation_propagated"]["count"] == 1

    cancelled = await db_session.get(AgentRun, UUID(run_ids[1]))
    assert cancelled.status == RunStatus.cancelled


@pytest.mark.asyncio
async def test_join_first_success_cancels_remaining_members(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    group = await _spawn_group(
        db_session,
        root_run_id=fx["root_run"].id,
        target_id=fx["target"].id,
        count=2,
    )
    run_ids = group["spawned_run_ids"]

    await _set_status(db_session, run_ids[0], RunStatus.completed)
    await _set_status(db_session, run_ids[1], RunStatus.running)
    await db_session.commit()

    joined = await kernel.join(
        caller_run_id=fx["root_run"].id,
        orchestration_group_id=UUID(group["orchestration_group_id"]),
        mode="first_success",
        quorum_threshold=None,
        timeout_s=60,
    )

    assert joined["complete"] is True
    assert joined["status"] == "completed"
    assert joined["cancellation_propagated"]["count"] == 1

    cancelled = await db_session.get(AgentRun, UUID(run_ids[1]))
    assert cancelled.status == RunStatus.cancelled


@pytest.mark.asyncio
async def test_join_quorum_impossible_transitions_to_failed(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    group = await _spawn_group(
        db_session,
        root_run_id=fx["root_run"].id,
        target_id=fx["target"].id,
        count=3,
    )
    run_ids = group["spawned_run_ids"]

    await _set_status(db_session, run_ids[0], RunStatus.completed)
    await _set_status(db_session, run_ids[1], RunStatus.failed)
    await _set_status(db_session, run_ids[2], RunStatus.running)
    await db_session.commit()

    first = await kernel.join(
        caller_run_id=fx["root_run"].id,
        orchestration_group_id=UUID(group["orchestration_group_id"]),
        mode="quorum",
        quorum_threshold=2,
        timeout_s=60,
    )

    assert first["complete"] is False
    assert first["status"] == "running"

    await _set_status(db_session, run_ids[2], RunStatus.failed)
    await db_session.commit()

    second = await kernel.join(
        caller_run_id=fx["root_run"].id,
        orchestration_group_id=UUID(group["orchestration_group_id"]),
        mode="quorum",
        quorum_threshold=2,
        timeout_s=60,
    )

    assert second["complete"] is True
    assert second["status"] == "failed"


@pytest.mark.asyncio
async def test_join_best_effort_returns_completed_with_errors(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    group = await _spawn_group(
        db_session,
        root_run_id=fx["root_run"].id,
        target_id=fx["target"].id,
        count=2,
    )
    run_ids = group["spawned_run_ids"]

    await _set_status(db_session, run_ids[0], RunStatus.completed)
    await _set_status(db_session, run_ids[1], RunStatus.failed)
    await db_session.commit()

    joined = await kernel.join(
        caller_run_id=fx["root_run"].id,
        orchestration_group_id=UUID(group["orchestration_group_id"]),
        mode="best_effort",
        quorum_threshold=None,
        timeout_s=60,
    )

    assert joined["complete"] is True
    assert joined["status"] == "completed_with_errors"
