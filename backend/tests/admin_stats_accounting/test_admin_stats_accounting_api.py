from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.scope_registry import ORGANIZATION_DEFAULT_ROLE_SCOPES, ORGANIZATION_OWNER_ROLE
from app.core.security import create_access_token, get_password_hash
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadStatus, AgentThreadSurface
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.services.security_bootstrap_service import SecurityBootstrapService


def _auth_headers(user_id: str, organization_id: str, org_unit_id: str) -> dict[str, str]:
    token = create_access_token(
        subject=user_id,
        organization_id=organization_id,
        org_unit_id=org_unit_id,
    )
    from app.core.security import ALGORITHM, SECRET_KEY

    import jwt

    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    payload["scope"] = list(ORGANIZATION_DEFAULT_ROLE_SCOPES[ORGANIZATION_OWNER_ROLE])
    scoped_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {scoped_token}", "X-Organization-ID": organization_id}


async def _seed_accounting_fixture(db_session):
    tenant = Organization(name=f"Organization {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    owner = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
        full_name="Owner",
    )
    db_session.add_all([tenant, owner])
    await db_session.flush()

    org_unit = OrgUnit(
        organization_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            organization_id=tenant.id,
            user_id=owner.id,
            org_unit_id=org_unit.id,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=owner.id, assigned_by=owner.id)

    agent = Agent(
        organization_id=tenant.id,
        name="Accounting Agent",
        slug=f"accounting-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        status=AgentStatus.published,
    )
    db_session.add(agent)
    await db_session.flush()

    thread = AgentThread(
        organization_id=tenant.id,
        user_id=owner.id,
        agent_id=agent.id,
        title="Accounting Thread",
        surface=AgentThreadSurface.internal,
        status=AgentThreadStatus.active,
    )
    db_session.add(thread)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    runs = [
        AgentRun(
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=owner.id,
            thread_id=thread.id,
            status=RunStatus.completed,
            usage_tokens=120,
            total_tokens=120,
            usage_source="exact",
            cost_usd=0.6,
            cost_source="binding_pricing",
            created_at=now - timedelta(minutes=1),
            started_at=now - timedelta(minutes=1, seconds=10),
            completed_at=now - timedelta(minutes=1, seconds=1),
        ),
        AgentRun(
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=owner.id,
            thread_id=thread.id,
            status=RunStatus.completed,
            usage_tokens=80,
            total_tokens=80,
            usage_source="estimated",
            cost_usd=0.1,
            cost_source="manual_override",
            created_at=now - timedelta(minutes=2),
            started_at=now - timedelta(minutes=2, seconds=10),
            completed_at=now - timedelta(minutes=2, seconds=1),
        ),
        AgentRun(
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=owner.id,
            thread_id=thread.id,
            status=RunStatus.failed,
            usage_tokens=0,
            total_tokens=None,
            usage_source="unknown",
            cost_usd=None,
            cost_source="unknown",
            created_at=now - timedelta(minutes=3),
            started_at=now - timedelta(minutes=3, seconds=10),
            completed_at=now - timedelta(minutes=3, seconds=1),
        ),
    ]
    db_session.add_all(runs)
    await db_session.commit()
    return {"tenant": tenant, "owner": owner, "org_unit": org_unit, "agent": agent}


@pytest.mark.asyncio
async def test_overview_stats_expose_accounting_provenance(client, db_session):
    fixture = await _seed_accounting_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    response = await client.get("/admin/stats/summary?section=overview&days=7", headers=headers)
    assert response.status_code == 200

    payload = response.json()["overview"]
    assert payload["total_tokens"] == 200
    assert payload["total_tokens_exact"] == 120
    assert payload["total_tokens_estimated"] == 80
    assert payload["runs_with_unknown_usage"] == 1
    assert payload["total_spend_exact_usd"] == 0.6
    assert payload["total_spend_estimated_usd"] == 0.1
    assert payload["runs_with_unknown_cost"] == 1


@pytest.mark.asyncio
async def test_agent_stats_expose_accounting_provenance(client, db_session):
    fixture = await _seed_accounting_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    response = await client.get(
        f"/admin/stats/summary?section=agents&days=7&agent_id={fixture['agent'].id}",
        headers=headers,
    )
    assert response.status_code == 200

    payload = response.json()["agents"]
    assert payload["tokens_used_total"] == 200
    assert payload["total_tokens_exact"] == 120
    assert payload["total_tokens_estimated"] == 80
    assert payload["runs_with_unknown_usage"] == 1
    assert payload["total_spend_exact_usd"] == 0.6
    assert payload["total_spend_estimated_usd"] == 0.1
    assert payload["runs_with_unknown_cost"] == 1
