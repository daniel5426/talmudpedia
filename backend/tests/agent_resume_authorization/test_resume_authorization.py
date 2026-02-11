from uuid import uuid4

import pytest

from app.agent.execution.service import AgentExecutorService
from app.core.security import create_access_token
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgRole,
    OrgUnit,
    OrgUnitType,
    Tenant,
    User,
)


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
