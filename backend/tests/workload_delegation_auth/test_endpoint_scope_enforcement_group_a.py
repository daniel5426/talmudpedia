from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.db.postgres.session import get_db
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService
from app.api.routers.rag_pipelines import router as rag_pipelines_router


async def _make_client(db_session):
    app = FastAPI()
    app.include_router(rag_pipelines_router, prefix="/admin/pipelines")

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_group_a_catalog_rejects_legacy_service_token(db_session):
    tenant = Tenant(name="Legacy Tenant", slug=f"legacy-tenant-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.commit()

    legacy_token = jwt.encode({"sub": "platform-service", "tenant_id": str(tenant.id)}, "legacy-secret", algorithm="HS256")
    async with await _make_client(db_session) as client:
        resp = await client.get(
            "/admin/pipelines/catalog",
            headers={"Authorization": f"Bearer {legacy_token}", "X-Tenant-ID": str(tenant.id)},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_group_a_catalog_accepts_workload_token_with_scope(db_session):
    tenant = Tenant(name="Scoped Tenant", slug=f"scoped-tenant-{uuid4().hex[:8]}")
    user = User(email=f"scope-admin-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()

    identity = WorkloadIdentityService(db_session)
    principal = await identity.ensure_principal(
        tenant_id=tenant.id,
        slug="system:catalog-reader",
        name="Catalog Reader",
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
    token, _ = await broker.mint_workload_token(
        grant_id=grant.id,
        audience="talmudpedia-internal-api",
        scope_subset=["pipelines.catalog.read"],
    )
    await db_session.commit()

    async with await _make_client(db_session) as client:
        resp = await client.get(
            "/admin/pipelines/catalog",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant.id)},
        )
        assert resp.status_code == 200
