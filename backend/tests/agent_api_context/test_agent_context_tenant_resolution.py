import pytest
import pytest_asyncio
import jwt
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import select
from uuid import uuid4

from app.core.security import ALGORITHM, SECRET_KEY, create_access_token
from app.api.routers.agents import get_agent_context
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgUnit,
    OrgUnitType,
    Organization,
    User,
)
from app.db.postgres.models.workspace import Project
from app.services.agent_service import AgentService, CreateAgentData


def _request_with_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/agents",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
    }
    return Request(scope)


def _auth_headers(
    user_id: str,
    organization_id: str,
    org_unit_id: str,
    *,
    project_id: str | None = None,
    scopes: list[str] | None = None,
) -> dict[str, str]:
    payload = jwt.decode(
        create_access_token(
            subject=user_id,
            organization_id=organization_id,
            org_unit_id=org_unit_id,
        ),
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    if project_id:
        payload["project_id"] = project_id
    payload["scope"] = list(scopes or ["agents.read"])
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": organization_id,
    }


@pytest_asyncio.fixture
async def tenant_fixture(db_session):
    suffix = uuid4().hex[:8]
    tenant_a = Organization(name="Organization A", slug=f"tenant-a-{suffix}")
    tenant_b = Organization(name="Organization B", slug=f"tenant-b-{suffix}")
    db_session.add_all([tenant_a, tenant_b])
    await db_session.flush()

    user = User(email=f"multi-tenant-user-{suffix}@example.com", full_name="Multi Organization", role="user")
    db_session.add(user)
    await db_session.flush()

    ou_a = OrgUnit(organization_id=tenant_a.id, parent_id=None, name="Org A", slug=f"org-a-{suffix}", type=OrgUnitType.org)
    ou_b = OrgUnit(organization_id=tenant_b.id, parent_id=None, name="Org B", slug=f"org-b-{suffix}", type=OrgUnitType.org)
    db_session.add_all([ou_a, ou_b])
    await db_session.flush()

    m_a = OrgMembership(
        organization_id=tenant_a.id,
        user_id=user.id,
        org_unit_id=ou_a.id,
        status=MembershipStatus.active,
    )
    m_b = OrgMembership(
        organization_id=tenant_b.id,
        user_id=user.id,
        org_unit_id=ou_b.id,
        status=MembershipStatus.active,
    )
    db_session.add_all([m_a, m_b])
    await db_session.commit()

    return {
        "user": user,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "org_unit_a": ou_a,
        "org_unit_b": ou_b,
    }


@pytest.mark.asyncio
async def test_get_agent_context_uses_x_tenant_id_when_user_has_multiple_memberships(db_session, tenant_fixture):
    request = _request_with_headers({"X-Organization-ID": str(tenant_fixture["tenant_b"].id)})
    context = {
        "type": "user",
        "user": tenant_fixture["user"],
        "auth_token": "test-token",
        "scopes": ["agents.write"],
    }

    resolved = await get_agent_context(request=request, context=context, db=db_session)

    assert str(resolved["organization_id"]) == str(tenant_fixture["tenant_b"].id)


@pytest.mark.asyncio
async def test_get_agent_context_without_header_requires_explicit_tenant_context(db_session, tenant_fixture):
    request = _request_with_headers({})
    context = {
        "type": "user",
        "user": tenant_fixture["user"],
        "auth_token": "test-token",
        "scopes": ["agents.write"],
    }

    with pytest.raises(HTTPException) as exc:
        await get_agent_context(request=request, context=context, db=db_session)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Organization context required"


@pytest.mark.asyncio
async def test_agents_api_exposes_show_in_playground_and_defaults_true(client, db_session, tenant_fixture):
    tenant = tenant_fixture["tenant_a"]
    user = tenant_fixture["user"]
    org_unit = tenant_fixture["org_unit_a"]
    project = Project(
        organization_id=tenant.id,
        name="Agent API Project",
        slug=f"agent-api-project-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.commit()

    service = AgentService(db_session, tenant.id, project_id=project.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Visible Agent",
            graph_definition={
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                    {"id": "end", "type": "end", "position": {"x": 200, "y": 0}, "config": {}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "end", "type": "control"},
                ],
            },
        ),
        user_id=user.id,
    )
    headers = _auth_headers(str(user.id), str(tenant.id), str(org_unit.id), project_id=str(project.id))

    list_response = await client.get("/agents?view=summary", headers=headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    listed = next(item for item in list_payload["items"] if item["id"] == str(agent.id))
    assert listed["show_in_playground"] is True
    assert listed["project_id"] == str(project.id)

    get_response = await client.get(f"/agents/{agent.id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["show_in_playground"] is True
    assert get_response.json()["project_id"] == str(project.id)

    refreshed = (await db_session.execute(select(Agent).where(Agent.id == agent.id))).scalar_one()
    assert refreshed.show_in_playground is True
