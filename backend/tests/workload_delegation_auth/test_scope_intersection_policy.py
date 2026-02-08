from uuid import uuid4

import pytest

from app.db.postgres.models.identity import Tenant, User, OrgUnit, OrgUnitType, OrgMembership, OrgRole, MembershipStatus
from app.db.postgres.models.security import WorkloadPrincipalType, WorkloadPolicyStatus
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.delegation_service import DelegationService


@pytest.mark.asyncio
async def test_scope_intersection_enforces_least_privilege(db_session):
    tenant = Tenant(name="Scope Tenant", slug=f"scope-tenant-{uuid4().hex[:8]}")
    user = User(email=f"scope-user-{uuid4().hex[:8]}@example.com", role="user")
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
            role=OrgRole.admin,
            status=MembershipStatus.active,
        )
    )
    await db_session.commit()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug="agent:scope-check",
        name="Scope Check",
        principal_type=WorkloadPrincipalType.AGENT,
        created_by=user.id,
        requested_scopes=["pipelines.catalog.read", "agents.write", "tools.write"],
        auto_approve_system=False,
    )

    policy = await identity.get_latest_policy(principal.id)
    policy.status = WorkloadPolicyStatus.APPROVED
    policy.approved_scopes = ["pipelines.catalog.read", "tools.write"]
    await db_session.commit()

    delegation = DelegationService(db_session)
    grant, _approval_required = await delegation.create_delegation_grant(
        tenant_id=tenant.id,
        principal_id=principal.id,
        initiator_user_id=user.id,
        requested_scopes=["pipelines.catalog.read", "agents.write", "tools.write"],
    )

    assert grant.effective_scopes == ["pipelines.catalog.read", "tools.write"]
