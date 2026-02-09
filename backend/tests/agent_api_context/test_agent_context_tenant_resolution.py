import pytest
import pytest_asyncio
from starlette.requests import Request
from uuid import uuid4

from app.api.routers.agents import get_agent_context
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgRole,
    OrgUnit,
    OrgUnitType,
    Tenant,
    User,
)


def _request_with_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/agents",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
    }
    return Request(scope)


@pytest_asyncio.fixture
async def tenant_fixture(db_session):
    suffix = uuid4().hex[:8]
    tenant_a = Tenant(name="Tenant A", slug=f"tenant-a-{suffix}")
    tenant_b = Tenant(name="Tenant B", slug=f"tenant-b-{suffix}")
    db_session.add_all([tenant_a, tenant_b])
    await db_session.flush()

    user = User(email=f"multi-tenant-user-{suffix}@example.com", full_name="Multi Tenant", role="user")
    db_session.add(user)
    await db_session.flush()

    ou_a = OrgUnit(tenant_id=tenant_a.id, parent_id=None, name="Org A", slug=f"org-a-{suffix}", type=OrgUnitType.org)
    ou_b = OrgUnit(tenant_id=tenant_b.id, parent_id=None, name="Org B", slug=f"org-b-{suffix}", type=OrgUnitType.org)
    db_session.add_all([ou_a, ou_b])
    await db_session.flush()

    m_a = OrgMembership(
        tenant_id=tenant_a.id,
        user_id=user.id,
        org_unit_id=ou_a.id,
        role=OrgRole.member,
        status=MembershipStatus.active,
    )
    m_b = OrgMembership(
        tenant_id=tenant_b.id,
        user_id=user.id,
        org_unit_id=ou_b.id,
        role=OrgRole.member,
        status=MembershipStatus.active,
    )
    db_session.add_all([m_a, m_b])
    await db_session.commit()

    return {
        "user": user,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
    }


@pytest.mark.asyncio
async def test_get_agent_context_uses_x_tenant_id_when_user_has_multiple_memberships(db_session, tenant_fixture):
    request = _request_with_headers({"X-Tenant-ID": str(tenant_fixture["tenant_b"].id)})
    context = {
        "type": "user",
        "user": tenant_fixture["user"],
        "auth_token": "test-token",
        "scopes": ["agents.write"],
    }

    resolved = await get_agent_context(request=request, context=context, db=db_session)

    assert str(resolved["tenant_id"]) == str(tenant_fixture["tenant_b"].id)


@pytest.mark.asyncio
async def test_get_agent_context_without_header_falls_back_to_membership(db_session, tenant_fixture):
    request = _request_with_headers({})
    context = {
        "type": "user",
        "user": tenant_fixture["user"],
        "auth_token": "test-token",
        "scopes": ["agents.write"],
    }

    resolved = await get_agent_context(request=request, context=context, db=db_session)

    assert resolved["tenant_id"] is not None
