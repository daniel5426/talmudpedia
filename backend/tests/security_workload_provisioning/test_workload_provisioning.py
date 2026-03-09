from uuid import uuid4

import pytest

from app.core.security import get_password_hash
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.security import WorkloadPolicyStatus, WorkloadResourceType
from app.services.delegation_service import DelegationPolicyError, DelegationService
from app.services.published_app_coding_agent_profile import CODING_AGENT_PROFILE_SLUG, ensure_coding_agent_profile
from app.services.workload_provisioning_service import WorkloadProvisioningService
from app.services.workload_identity_service import WorkloadIdentityService


async def _seed_tenant_with_user(db_session, *, user_role: str = "user"):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"user-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role=user_role,
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            org_unit_id=org_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()
    return tenant, user


@pytest.mark.asyncio
async def test_provisioning_auto_approves_for_platform_admin(db_session):
    tenant, admin_user = await _seed_tenant_with_user(db_session, user_role="admin")
    agent = Agent(
        tenant_id=tenant.id,
        name="Architect",
        slug=f"platform-architect-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        created_by=admin_user.id,
    )
    db_session.add(agent)
    await db_session.flush()

    svc = WorkloadProvisioningService(db_session)
    principal, policy = await svc.provision_agent_policy(agent=agent, actor_user_id=admin_user.id)
    await db_session.commit()

    assert principal.id is not None
    assert policy.status == WorkloadPolicyStatus.APPROVED
    assert len(policy.approved_scopes or []) > 0


@pytest.mark.asyncio
async def test_provisioning_is_pending_for_non_admin_actor(db_session):
    tenant, normal_user = await _seed_tenant_with_user(db_session, user_role="user")
    agent = Agent(
        tenant_id=tenant.id,
        name="Worker",
        slug=f"worker-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        created_by=normal_user.id,
    )
    db_session.add(agent)
    await db_session.flush()

    svc = WorkloadProvisioningService(db_session)
    _principal, policy = await svc.provision_agent_policy(agent=agent, actor_user_id=normal_user.id)
    await db_session.commit()

    assert policy.status == WorkloadPolicyStatus.PENDING


@pytest.mark.asyncio
async def test_runtime_grant_fails_when_agent_principal_not_provisioned(db_session):
    tenant, user = await _seed_tenant_with_user(db_session, user_role="admin")
    agent = Agent(
        tenant_id=tenant.id,
        name="Unprovisioned",
        slug=f"unprovisioned-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        created_by=user.id,
    )
    db_session.add(agent)
    await db_session.commit()

    service = DelegationService(db_session)
    with pytest.raises(DelegationPolicyError) as exc:
        await service.create_agent_run_grant(
            agent=agent,
            initiator_user_id=user.id,
            run_id=uuid4(),
        )

    assert exc.value.code == "WORKLOAD_PRINCIPAL_MISSING"


@pytest.mark.asyncio
async def test_coding_agent_profile_ensures_bound_workload_principal(db_session):
    tenant, admin_user = await _seed_tenant_with_user(db_session, user_role="admin")

    profile = await ensure_coding_agent_profile(
        db_session,
        tenant.id,
        actor_user_id=admin_user.id,
    )
    await db_session.commit()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.get_bound_principal(
        tenant_id=tenant.id,
        resource_type=WorkloadResourceType.AGENT,
        resource_id=str(profile.id),
    )
    policy = await identity.get_latest_policy(principal.id) if principal is not None else None

    assert profile.slug == CODING_AGENT_PROFILE_SLUG
    assert principal is not None
    assert policy is not None
    assert policy.status == WorkloadPolicyStatus.APPROVED
