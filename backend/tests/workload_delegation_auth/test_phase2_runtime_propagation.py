from uuid import uuid4, UUID

import pytest

from app.agent.execution.service import AgentExecutorService
from app.agent.executors.tool import ToolNodeExecutor
from app.db.postgres.models.agents import Agent, AgentRun
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.security import DelegationGrant, WorkloadPrincipalType
from app.services.delegation_service import DelegationService
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.workload_provisioning_service import WorkloadProvisioningService


@pytest.mark.asyncio
async def test_agent_run_persists_existing_workload_context(db_session):
    tenant = Tenant(name="Runtime Tenant", slug=f"runtime-tenant-{uuid4().hex[:8]}")
    user = User(email=f"runtime-user-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    agent = Agent(
        tenant_id=tenant.id,
        name="Runtime Agent",
        slug=f"runtime-agent-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add(agent)
    await db_session.commit()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug="system:runtime-propagation",
        name="Runtime Propagation",
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
    await db_session.commit()

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=agent.id,
        input_params={
            "messages": [],
            "context": {
                "grant_id": str(grant.id),
                "principal_id": str(principal.id),
                "initiator_user_id": str(user.id),
            },
        },
        user_id=None,
        background=False,
    )

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.delegation_grant_id == grant.id
    assert run.workload_principal_id == principal.id
    assert run.initiator_user_id == user.id


@pytest.mark.asyncio
async def test_tool_executor_requires_grant_for_workload_token_mode(db_session):
    executor = ToolNodeExecutor(tenant_id=UUID(str(uuid4())), db=db_session)

    with pytest.raises(PermissionError):
        await executor._execute_http_tool(
            _tool=None,
            input_data={"hello": "world"},
            implementation_config={
                "type": "http",
                "url": "http://localhost:9999/echo",
                "method": "POST",
                "use_workload_token": True,
            },
            node_context={},
        )


@pytest.mark.asyncio
async def test_start_run_mints_delegation_grant_after_run_insert(db_session):
    tenant = Tenant(name="Runtime Tenant 2", slug=f"runtime-tenant-{uuid4().hex[:8]}")
    user = User(email=f"runtime-user-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    agent = Agent(
        tenant_id=tenant.id,
        name="Runtime Agent 2",
        slug=f"runtime-agent-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
        created_by=user.id,
    )
    db_session.add(agent)
    await db_session.flush()

    provisioning = WorkloadProvisioningService(db_session)
    _principal, policy = await provisioning.provision_agent_policy(agent=agent, actor_user_id=user.id)
    await db_session.commit()

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=agent.id,
        input_params={
            "messages": [],
            "context": {
                "requested_scopes": list(policy.approved_scopes or []),
            },
        },
        user_id=user.id,
        background=False,
    )

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.delegation_grant_id is not None
    assert run.workload_principal_id is not None

    grant = await db_session.get(DelegationGrant, run.delegation_grant_id)
    assert grant is not None
    assert grant.run_id == run.id
