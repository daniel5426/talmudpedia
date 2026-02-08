from uuid import uuid4

import pytest

from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService


@pytest.mark.asyncio
async def test_pending_policy_blocks_token_issuance(db_session):
    tenant = Tenant(name="Approval Tenant", slug=f"approval-tenant-{uuid4().hex[:8]}")
    user = User(email=f"approval-user-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug="agent:needs-approval",
        name="Needs Approval",
        principal_type=WorkloadPrincipalType.AGENT,
        created_by=user.id,
        requested_scopes=["tools.write"],
        auto_approve_system=False,
    )

    delegation = DelegationService(db_session)
    grant, approval_required = await delegation.create_delegation_grant(
        tenant_id=tenant.id,
        principal_id=principal.id,
        initiator_user_id=user.id,
        requested_scopes=["tools.write"],
    )
    assert approval_required is True
    assert grant.effective_scopes == []

    broker = TokenBrokerService(db_session)
    with pytest.raises(PermissionError):
        await broker.mint_workload_token(
            grant_id=grant.id,
            audience="talmudpedia-internal-api",
            scope_subset=["tools.write"],
        )
