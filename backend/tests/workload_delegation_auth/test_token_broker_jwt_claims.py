from uuid import uuid4

import pytest

from app.db.postgres.models.identity import Tenant, User, OrgUnit, OrgUnitType, OrgMembership, OrgRole, MembershipStatus
from app.db.postgres.models.security import WorkloadPrincipalType, WorkloadPolicyStatus
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService
from app.core.workload_jwt import decode_workload_token


@pytest.mark.asyncio
async def test_token_broker_issues_signed_jwt_with_expected_claims(db_session):
    tenant = Tenant(name="Token Tenant", slug=f"token-tenant-{uuid4().hex[:8]}")
    user = User(email=f"token-user-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    org = OrgUnit(tenant_id=tenant.id, name="Root", slug="root", type=OrgUnitType.org)
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

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug="agent:test-broker",
        name="Test Broker Principal",
        principal_type=WorkloadPrincipalType.AGENT,
        created_by=user.id,
        requested_scopes=["pipelines.catalog.read", "agents.write"],
        auto_approve_system=False,
    )

    policy = await identity.get_latest_policy(principal.id)
    policy.status = WorkloadPolicyStatus.APPROVED
    policy.approved_scopes = ["pipelines.catalog.read", "agents.write"]
    await db_session.commit()

    delegation = DelegationService(db_session)
    grant, _approval_required = await delegation.create_delegation_grant(
        tenant_id=tenant.id,
        principal_id=principal.id,
        initiator_user_id=user.id,
        requested_scopes=["pipelines.catalog.read"],
    )

    broker = TokenBrokerService(db_session)
    token, payload = await broker.mint_workload_token(
        grant_id=grant.id,
        audience="talmudpedia-internal-api",
        scope_subset=["pipelines.catalog.read"],
    )
    await db_session.commit()

    decoded = decode_workload_token(token, audience="talmudpedia-internal-api")
    assert decoded["tenant_id"] == str(tenant.id)
    assert decoded["grant_id"] == str(grant.id)
    assert decoded["token_use"] == "workload_delegated"
    assert decoded["scope"] == ["pipelines.catalog.read"]
    assert payload["jti"] == decoded["jti"]

    assert await broker.is_jti_active(decoded["jti"]) is True
