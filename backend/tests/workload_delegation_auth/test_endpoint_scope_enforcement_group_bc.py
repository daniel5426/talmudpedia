from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.api.routers.agents import router as agents_router
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.security import ApprovalDecision, ApprovalStatus, WorkloadPrincipalType
from app.db.postgres.session import get_db
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService
from app.services.workload_identity_service import WorkloadIdentityService


async def _make_client(db_session):
    app = FastAPI()
    app.include_router(agents_router)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _mint_workload_token(db_session, tenant, user, scopes, slug):
    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug=slug,
        name=slug,
        principal_type=WorkloadPrincipalType.SYSTEM,
        created_by=user.id,
        requested_scopes=scopes,
        auto_approve_system=True,
    )

    delegation = DelegationService(db_session)
    grant, _ = await delegation.create_delegation_grant(
        tenant_id=tenant.id,
        principal_id=principal.id,
        initiator_user_id=user.id,
        requested_scopes=scopes,
    )

    broker = TokenBrokerService(db_session)
    token, _payload = await broker.mint_workload_token(
        grant_id=grant.id,
        audience="talmudpedia-internal-api",
        scope_subset=scopes,
    )
    await db_session.commit()
    return token


@pytest.mark.asyncio
async def test_group_b_update_rejects_legacy_token(db_session):
    tenant = Tenant(name="Legacy Group B", slug=f"legacy-gb-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    agent = Agent(
        tenant_id=tenant.id,
        name="Legacy Agent",
        slug=f"legacy-agent-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add(agent)
    await db_session.commit()

    legacy_token = jwt.encode(
        {"sub": "platform-service", "tenant_id": str(tenant.id)},
        "legacy-secret",
        algorithm="HS256",
    )

    async with await _make_client(db_session) as client:
        resp = await client.put(
            f"/agents/{agent.id}",
            json={"name": "Changed Name"},
            headers={"Authorization": f"Bearer {legacy_token}", "X-Tenant-ID": str(tenant.id)},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_group_b_sensitive_delete_requires_approval_for_workload(db_session):
    tenant = Tenant(name="Approval Group B", slug=f"approval-gb-{uuid4().hex[:8]}")
    user = User(email=f"gb-approver-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    agent = Agent(
        tenant_id=tenant.id,
        name="Delete Candidate",
        slug=f"delete-agent-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add(agent)
    await db_session.commit()

    token = await _mint_workload_token(
        db_session,
        tenant,
        user,
        ["agents.write"],
        slug="system:group-b-delete",
    )

    async with await _make_client(db_session) as client:
        denied = await client.delete(
            f"/agents/{agent.id}",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant.id)},
        )
        assert denied.status_code == 403

        db_session.add(
            ApprovalDecision(
                tenant_id=tenant.id,
                subject_type="agent",
                subject_id=str(agent.id),
                action_scope="agents.delete",
                status=ApprovalStatus.APPROVED,
                decided_by=user.id,
            )
        )
        await db_session.commit()

        allowed = await client.delete(
            f"/agents/{agent.id}",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant.id)},
        )

    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_group_c_validate_requires_run_tests_scope(db_session):
    tenant = Tenant(name="Scope Group C", slug=f"scope-gc-{uuid4().hex[:8]}")
    user = User(email=f"gc-user-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    agent = Agent(
        tenant_id=tenant.id,
        name="Validate Agent",
        slug=f"validate-agent-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add(agent)
    await db_session.commit()

    execute_only = await _mint_workload_token(
        db_session,
        tenant,
        user,
        ["agents.execute"],
        slug="system:group-c-execute-only",
    )

    run_tests_token = await _mint_workload_token(
        db_session,
        tenant,
        user,
        ["agents.run_tests"],
        slug="system:group-c-run-tests",
    )

    async with await _make_client(db_session) as client:
        denied = await client.post(
            f"/agents/{agent.id}/validate",
            headers={"Authorization": f"Bearer {execute_only}", "X-Tenant-ID": str(tenant.id)},
        )
        assert denied.status_code == 403

        allowed = await client.post(
            f"/agents/{agent.id}/validate",
            headers={"Authorization": f"Bearer {run_tests_token}", "X-Tenant-ID": str(tenant.id)},
        )

    assert allowed.status_code == 200
