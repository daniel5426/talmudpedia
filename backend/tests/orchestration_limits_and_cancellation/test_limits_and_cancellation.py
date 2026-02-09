from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.orchestration import OrchestrationGroup, OrchestratorPolicy, OrchestratorTargetAllowlist
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.delegation_service import DelegationService
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.workload_identity_service import WorkloadIdentityService


async def _setup_fixture(
    db_session,
    *,
    max_depth: int = 3,
    max_fanout: int = 8,
    max_children_total: int = 32,
):
    tenant = Tenant(name="Limits Tenant", slug=f"limits-{uuid4().hex[:8]}")
    user = User(email=f"limits-{uuid4().hex[:8]}@example.com", role="admin")
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
        name="Limits Principal",
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
            max_depth=max_depth,
            max_fanout=max_fanout,
            max_children_total=max_children_total,
            join_timeout_s=30,
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


@pytest.mark.asyncio
async def test_spawn_run_idempotency_under_repeated_calls(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    spawned_ids = []
    for _ in range(20):
        out = await kernel.spawn_run(
            caller_run_id=fx["root_run"].id,
            parent_node_id="idempotency_stress",
            target_agent_id=fx["target"].id,
            target_agent_slug=None,
            mapped_input_payload={"input": "stress"},
            failure_policy="best_effort",
            timeout_s=10,
            scope_subset=["agents.execute"],
            idempotency_key="same-key",
            start_background=False,
        )
        spawned_ids.append(out["spawned_run_ids"][0])

    assert len(set(spawned_ids)) == 1

    rows = await db_session.execute(
        select(AgentRun).where(AgentRun.parent_run_id == fx["root_run"].id)
    )
    assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_limits_enforced_for_fanout_and_depth(db_session):
    fx = await _setup_fixture(db_session, max_depth=1, max_fanout=2, max_children_total=16)
    kernel = OrchestrationKernelService(db_session)

    with pytest.raises(PermissionError):
        await kernel.spawn_group(
            caller_run_id=fx["root_run"].id,
            parent_node_id="fanout_limit",
            targets=[
                {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"n": 1}},
                {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"n": 2}},
                {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"n": 3}},
            ],
            failure_policy="best_effort",
            join_mode="all",
            quorum_threshold=None,
            timeout_s=30,
            scope_subset=["agents.execute"],
            idempotency_key_prefix="fanout-limit",
            start_background=False,
        )

    first_child = await kernel.spawn_run(
        caller_run_id=fx["root_run"].id,
        parent_node_id="depth_parent",
        target_agent_id=fx["target"].id,
        target_agent_slug=None,
        mapped_input_payload={"input": "first"},
        failure_policy="best_effort",
        timeout_s=10,
        scope_subset=["agents.execute"],
        idempotency_key="depth-first",
        start_background=False,
    )

    with pytest.raises(PermissionError):
        await kernel.spawn_run(
            caller_run_id=UUID(first_child["spawned_run_ids"][0]),
            parent_node_id="depth_child",
            target_agent_id=fx["target"].id,
            target_agent_slug=None,
            mapped_input_payload={"input": "second"},
            failure_policy="best_effort",
            timeout_s=10,
            scope_subset=["agents.execute"],
            idempotency_key="depth-second",
            start_background=False,
        )


@pytest.mark.asyncio
async def test_join_timeout_propagates_cancellation(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    group = await kernel.spawn_group(
        caller_run_id=fx["root_run"].id,
        parent_node_id="timeout_group",
        targets=[
            {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"input": "a"}},
            {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"input": "b"}},
        ],
        failure_policy="best_effort",
        join_mode="all",
        quorum_threshold=None,
        timeout_s=1,
        scope_subset=["agents.execute"],
        idempotency_key_prefix=f"timeout-{uuid4().hex[:8]}",
        start_background=False,
    )

    run_ids = group["spawned_run_ids"]
    for run_id in run_ids:
        run = await db_session.get(AgentRun, UUID(run_id))
        run.status = RunStatus.running

    group_row = await db_session.get(OrchestrationGroup, UUID(group["orchestration_group_id"]))
    group_row.started_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    await db_session.commit()

    joined = await kernel.join(
        caller_run_id=fx["root_run"].id,
        orchestration_group_id=group_row.id,
        mode="best_effort",
        quorum_threshold=None,
        timeout_s=1,
    )

    assert joined["complete"] is True
    assert joined["status"] == "timed_out"
    assert joined["cancellation_propagated"]["count"] == 2

    for run_id in run_ids:
        run = await db_session.get(AgentRun, UUID(run_id))
        assert run.status == RunStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_subtree_is_idempotent_on_repeated_calls(db_session):
    fx = await _setup_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    group = await kernel.spawn_group(
        caller_run_id=fx["root_run"].id,
        parent_node_id="cancel_storm",
        targets=[
            {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"input": "a"}},
            {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"input": "b"}},
            {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"input": "c"}},
        ],
        failure_policy="best_effort",
        join_mode="all",
        quorum_threshold=None,
        timeout_s=10,
        scope_subset=["agents.execute"],
        idempotency_key_prefix=f"cancel-{uuid4().hex[:8]}",
        start_background=False,
    )

    first = await kernel.cancel_subtree(
        caller_run_id=fx["root_run"].id,
        run_id=fx["root_run"].id,
        include_root=False,
        reason="storm-test",
    )
    second = await kernel.cancel_subtree(
        caller_run_id=fx["root_run"].id,
        run_id=fx["root_run"].id,
        include_root=False,
        reason="storm-test",
    )

    assert first["cancelled_count"] >= len(group["spawned_run_ids"])
    assert second["cancelled_count"] == 0
