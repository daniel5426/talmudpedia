from uuid import uuid4

import pytest

from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService


@pytest.mark.asyncio
async def test_revoked_grant_invalidates_jti(db_session):
    tenant = Tenant(name="Revoke Tenant", slug=f"revoke-tenant-{uuid4().hex[:8]}")
    user = User(email=f"revoke-user-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug="system:revoker",
        name="Revoker",
        principal_type=WorkloadPrincipalType.SYSTEM,
        created_by=user.id,
        requested_scopes=["pipelines.catalog.read"],
        auto_approve_system=True,
    )

    delegation = DelegationService(db_session)
    grant, _ = await delegation.create_delegation_grant(
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
    assert token
    await db_session.commit()

    assert await broker.is_jti_active(payload["jti"]) is True
    await broker.revoke_grant(grant.id, reason="test")
    await db_session.commit()
    assert await broker.is_jti_active(payload["jti"]) is False
