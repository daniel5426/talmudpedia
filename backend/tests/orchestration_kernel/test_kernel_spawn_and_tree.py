from uuid import uuid4

import pytest

from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.orchestration import OrchestratorPolicy, OrchestratorTargetAllowlist
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.delegation_service import DelegationService
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.workload_identity_service import WorkloadIdentityService


async def _setup_orchestration_fixture(db_session):
    tenant = Tenant(name="Orch Tenant", slug=f"orch-tenant-{uuid4().hex[:8]}")
    user = User(email=f"orch-admin-{uuid4().hex[:8]}@example.com", role="admin")
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
        name="Orchestrator Principal",
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

    policy = OrchestratorPolicy(
        tenant_id=tenant.id,
        orchestrator_agent_id=orchestrator.id,
        allowed_scope_subset=["agents.execute"],
        max_depth=3,
        max_fanout=8,
        max_children_total=32,
        join_timeout_s=60,
        enforce_published_only=True,
    )
    allow = OrchestratorTargetAllowlist(
        tenant_id=tenant.id,
        orchestrator_agent_id=orchestrator.id,
        target_agent_id=target.id,
    )
    db_session.add_all([policy, allow])
    await db_session.commit()

    return {
        "tenant": tenant,
        "user": user,
        "orchestrator": orchestrator,
        "target": target,
        "root_run": root_run,
    }


@pytest.mark.asyncio
async def test_spawn_run_idempotency_and_tree_query(db_session):
    fx = await _setup_orchestration_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    first = await kernel.spawn_run(
        caller_run_id=fx["root_run"].id,
        parent_node_id="spawn_1",
        target_agent_id=fx["target"].id,
        target_agent_slug=None,
        mapped_input_payload={"input": "hello"},
        failure_policy="best_effort",
        timeout_s=30,
        scope_subset=["agents.execute"],
        idempotency_key="k-1",
        start_background=False,
    )
    second = await kernel.spawn_run(
        caller_run_id=fx["root_run"].id,
        parent_node_id="spawn_1",
        target_agent_id=fx["target"].id,
        target_agent_slug=None,
        mapped_input_payload={"input": "hello"},
        failure_policy="best_effort",
        timeout_s=30,
        scope_subset=["agents.execute"],
        idempotency_key="k-1",
        start_background=False,
    )

    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["spawned_run_ids"][0] == second["spawned_run_ids"][0]

    tree = await kernel.query_tree(run_id=fx["root_run"].id)
    assert tree["root_run_id"] == str(fx["root_run"].id)
    assert tree["node_count"] >= 2
    child_ids = [node["run_id"] for node in tree["tree"]["children"]]
    assert first["spawned_run_ids"][0] in child_ids


@pytest.mark.asyncio
async def test_spawn_run_denies_non_allowlisted_target(db_session):
    fx = await _setup_orchestration_fixture(db_session)
    kernel = OrchestrationKernelService(db_session)

    denied_target = Agent(
        tenant_id=fx["tenant"].id,
        name="Denied",
        slug=f"denied-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add(denied_target)
    await db_session.commit()

    with pytest.raises(PermissionError):
        await kernel.spawn_run(
            caller_run_id=fx["root_run"].id,
            parent_node_id="spawn_2",
            target_agent_id=denied_target.id,
            target_agent_slug=None,
            mapped_input_payload={"input": "hello"},
            failure_policy="best_effort",
            timeout_s=30,
            scope_subset=["agents.execute"],
            idempotency_key="k-denied",
            start_background=False,
        )
