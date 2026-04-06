import asyncio
from uuid import uuid4

import pytest

from app.api.routers.agents import _cancel_foreground_run_tree
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.run_task_registry import cancel_run_tasks, register_run_task, unregister_run_task
from app.core.security import create_access_token
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgRole,
    OrgUnit,
    OrgUnitType,
    Tenant,
    User,
)
from app.services.security_bootstrap_service import SecurityBootstrapService
from app.services.thread_service import ThreadService


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        org_role="owner",
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant.id)}


async def _seed_tenant_with_users(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    owner = User(email=f"owner-{suffix}@example.com", role="user")
    intruder = User(email=f"intruder-{suffix}@example.com", role="user")
    db_session.add_all([tenant, owner, intruder])
    await db_session.flush()

    org = OrgUnit(
        tenant_id=tenant.id,
        parent_id=None,
        name=f"Root {suffix}",
        slug=f"root-{suffix}",
        type=OrgUnitType.org,
    )
    db_session.add(org)
    await db_session.flush()

    db_session.add_all(
        [
            OrgMembership(
                tenant_id=tenant.id,
                user_id=owner.id,
                org_unit_id=org.id,
                role=OrgRole.owner,
                status=MembershipStatus.active,
            ),
            OrgMembership(
                tenant_id=tenant.id,
                user_id=intruder.id,
                org_unit_id=org.id,
                role=OrgRole.member,
                status=MembershipStatus.active,
            ),
        ]
    )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await bootstrap.ensure_member_assignment(tenant_id=tenant.id, user_id=intruder.id, assigned_by=owner.id)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(owner)
    await db_session.refresh(intruder)
    return tenant, owner, intruder


async def _seed_second_tenant_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Other Tenant {suffix}", slug=f"other-tenant-{suffix}")
    user = User(email=f"other-owner-{suffix}@example.com", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    org = OrgUnit(
        tenant_id=tenant.id,
        parent_id=None,
        name=f"Other Root {suffix}",
        slug=f"other-root-{suffix}",
        type=OrgUnitType.org,
    )
    db_session.add(org)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            org_unit_id=org.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=user.id, assigned_by=user.id)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _seed_paused_run(db_session, tenant: Tenant, owner: User) -> AgentRun:
    suffix = uuid4().hex[:8]
    agent = Agent(
        tenant_id=tenant.id,
        name=f"Resume Agent {suffix}",
        slug=f"resume-agent-{suffix}",
        description="resume authorization test",
        graph_definition={"nodes": [], "edges": []},
        memory_config={},
        execution_constraints={},
        created_by=owner.id,
    )
    db_session.add(agent)
    await db_session.flush()

    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        initiator_user_id=owner.id,
        status=RunStatus.paused,
        input_params={"messages": []},
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _seed_running_run_tree(db_session, tenant: Tenant, owner: User) -> tuple[AgentRun, AgentRun, AgentRun]:
    suffix = uuid4().hex[:8]
    agent = Agent(
        tenant_id=tenant.id,
        name=f"Cancel Agent {suffix}",
        slug=f"cancel-agent-{suffix}",
        description="cancel authorization test",
        graph_definition={"nodes": [], "edges": []},
        memory_config={},
        execution_constraints={},
        created_by=owner.id,
    )
    db_session.add(agent)
    await db_session.flush()

    root = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        initiator_user_id=owner.id,
        status=RunStatus.running,
        input_params={"messages": []},
        depth=0,
    )
    db_session.add(root)
    await db_session.flush()
    root.root_run_id = root.id

    child = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        initiator_user_id=owner.id,
        status=RunStatus.running,
        input_params={"messages": []},
        root_run_id=root.id,
        parent_run_id=root.id,
        parent_node_id="delegate_a",
        depth=1,
    )
    db_session.add(child)
    await db_session.flush()

    grandchild = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        initiator_user_id=owner.id,
        status=RunStatus.paused,
        input_params={"messages": []},
        root_run_id=root.id,
        parent_run_id=child.id,
        parent_node_id="delegate_b",
        depth=2,
    )
    db_session.add(grandchild)
    await db_session.commit()
    await db_session.refresh(root)
    await db_session.refresh(child)
    await db_session.refresh(grandchild)
    return root, child, grandchild


@pytest.mark.asyncio
async def test_resume_run_rejects_user_within_same_tenant_when_not_owner(client, db_session, monkeypatch):
    tenant, owner, intruder = await _seed_tenant_with_users(db_session)
    run = await _seed_paused_run(db_session, tenant, owner)

    calls: list[tuple[str, dict]] = []

    async def fake_resume(self, run_id, payload, background=True):
        calls.append((str(run_id), payload))

    monkeypatch.setattr(AgentExecutorService, "resume_run", fake_resume)

    response = await client.post(
        f"/agents/runs/{run.id}/resume",
        json={"approval": "approve"},
        headers=_headers(intruder, tenant),
    )

    assert response.status_code == 403
    assert "ownership" in response.json()["detail"].lower()
    assert calls == []


@pytest.mark.asyncio
async def test_resume_run_rejects_cross_tenant_access(client, db_session, monkeypatch):
    tenant, owner, _intruder = await _seed_tenant_with_users(db_session)
    other_tenant, other_user = await _seed_second_tenant_user(db_session)
    run = await _seed_paused_run(db_session, tenant, owner)

    calls: list[tuple[str, dict]] = []

    async def fake_resume(self, run_id, payload, background=True):
        calls.append((str(run_id), payload))

    monkeypatch.setattr(AgentExecutorService, "resume_run", fake_resume)

    response = await client.post(
        f"/agents/runs/{run.id}/resume",
        json={"approval": "approve"},
        headers=_headers(other_user, other_tenant),
    )

    assert response.status_code == 403
    assert "tenant mismatch" in response.json()["detail"].lower()
    assert calls == []


@pytest.mark.asyncio
async def test_resume_run_allows_owner_and_resumes(client, db_session, monkeypatch):
    tenant, owner, _intruder = await _seed_tenant_with_users(db_session)
    run = await _seed_paused_run(db_session, tenant, owner)

    calls: list[tuple[str, dict]] = []

    async def fake_resume(self, run_id, payload, background=True):
        calls.append((str(run_id), payload))

    monkeypatch.setattr(AgentExecutorService, "resume_run", fake_resume)

    payload = {"approval": "approve"}
    response = await client.post(
        f"/agents/runs/{run.id}/resume",
        json=payload,
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "resumed"}
    assert calls == [(str(run.id), payload)]


@pytest.mark.asyncio
async def test_cancel_run_cascades_to_descendant_runs(client, db_session):
    tenant, owner, _intruder = await _seed_tenant_with_users(db_session)
    root, child, grandchild = await _seed_running_run_tree(db_session, tenant, owner)

    response = await client.post(
        f"/agents/runs/{root.id}/cancel",
        json={"assistant_output_text": "Stopped"},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["run_id"] == str(root.id)

    await db_session.refresh(root)
    await db_session.refresh(child)
    await db_session.refresh(grandchild)

    assert root.status == RunStatus.cancelled
    assert child.status == RunStatus.cancelled
    assert grandchild.status == RunStatus.cancelled
    assert root.output_result["final_output"] == "Stopped"


@pytest.mark.asyncio
async def test_cancel_run_does_not_write_thread_turns_from_cancel_endpoint(client, db_session, monkeypatch):
    tenant, owner, _intruder = await _seed_tenant_with_users(db_session)
    root, _child, _grandchild = await _seed_running_run_tree(db_session, tenant, owner)
    thread = AgentThread(
        tenant_id=tenant.id,
        user_id=owner.id,
        agent_id=root.agent_id,
        surface=AgentThreadSurface.internal,
        title="Cancel thread",
    )
    db_session.add(thread)
    await db_session.flush()
    root.thread_id = thread.id
    await db_session.commit()

    async def _unexpected_start_turn(self, **kwargs):
        raise AssertionError("cancel endpoint should not call start_turn")

    async def _unexpected_complete_turn(self, **kwargs):
        raise AssertionError("cancel endpoint should not call complete_turn")

    monkeypatch.setattr(ThreadService, "start_turn", _unexpected_start_turn)
    monkeypatch.setattr(ThreadService, "complete_turn", _unexpected_complete_turn)

    response = await client.post(
        f"/agents/runs/{root.id}/cancel",
        json={"assistant_output_text": "Stopped"},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancelled_run_does_not_restart_when_execution_worker_enters(db_session):
    tenant, owner, _intruder = await _seed_tenant_with_users(db_session)
    root, _child, _grandchild = await _seed_running_run_tree(db_session, tenant, owner)
    root.status = RunStatus.cancelled
    await db_session.commit()

    executor = AgentExecutorService(db_session)
    events = [event async for event in executor.run_and_stream(root.id, db_session)]

    await db_session.refresh(root)
    assert events == []
    assert root.status == RunStatus.cancelled


@pytest.mark.asyncio
async def test_run_task_registry_cancels_registered_task():
    sleeper = asyncio.create_task(asyncio.sleep(30))
    register_run_task("run-1", sleeper)
    try:
        assert cancel_run_tasks(["run-1"]) == 1
        await asyncio.sleep(0)
        assert sleeper.cancelled()
    finally:
        unregister_run_task("run-1", sleeper)


@pytest.mark.asyncio
async def test_cancel_foreground_run_tree_marks_run_cancelled_and_interrupts_live_tasks(db_session):
    tenant, owner, _intruder = await _seed_tenant_with_users(db_session)
    root, child, grandchild = await _seed_running_run_tree(db_session, tenant, owner)

    sleeper = asyncio.create_task(asyncio.sleep(30))
    cancelled = asyncio.Event()
    register_run_task(child.id, sleeper)
    try:
        sleeper.add_done_callback(lambda task: cancelled.set() if task.cancelled() else None)
        await _cancel_foreground_run_tree(root.id, reason="cancelled_by_client_disconnect")
        await asyncio.wait_for(cancelled.wait(), timeout=2.0)

        await db_session.refresh(root)
        await db_session.refresh(child)
        await db_session.refresh(grandchild)

        assert root.status == RunStatus.cancelled
        assert child.status == RunStatus.cancelled
        assert grandchild.status == RunStatus.cancelled
        assert root.error_message == "cancelled_by_client_disconnect"
    finally:
        unregister_run_task(child.id, sleeper)
