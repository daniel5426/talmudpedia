from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.db.postgres.models.identity import Tenant, User
from app.services.agent_service import (
    AgentGraphValidationError,
    AgentService,
    CreateAgentData,
    UpdateAgentData,
)


def _valid_graph() -> dict:
    return {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "end", "type": "end", "position": {"x": 200, "y": 0}, "config": {"output_message": "done"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "end", "type": "control"},
        ],
    }


def _invalid_graph_missing_end() -> dict:
    return {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
        ],
        "edges": [],
    }


async def _seed_tenant_admin(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"admin-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        org_role="owner",
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant.id)}


@pytest.mark.asyncio
async def test_service_create_rejects_missing_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)

    with pytest.raises(AgentGraphValidationError) as exc_info:
        await service.create_agent(
            CreateAgentData(
                name="Missing Graph",
                slug=f"missing-graph-{uuid4().hex[:8]}",
            ),
            user_id=user.id,
        )

    assert any("graph_definition is required" in entry["message"] for entry in exc_info.value.errors)


@pytest.mark.asyncio
async def test_service_create_rejects_empty_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)

    with pytest.raises(AgentGraphValidationError) as exc_info:
        await service.create_agent(
            CreateAgentData(
                name="Empty Graph",
                slug=f"empty-graph-{uuid4().hex[:8]}",
                graph_definition={"spec_version": "1.0", "nodes": [], "edges": []},
            ),
            user_id=user.id,
        )

    messages = [entry["message"] for entry in exc_info.value.errors]
    assert any("exactly one Start node" in message for message in messages)
    assert any("at least one End node" in message for message in messages)


@pytest.mark.asyncio
async def test_service_update_without_graph_still_succeeds(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Update Agent",
            slug=f"update-agent-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    updated = await service.update_agent(agent.id, UpdateAgentData(name="Updated Name"))
    assert updated.name == "Updated Name"


@pytest.mark.asyncio
async def test_service_update_rejects_invalid_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Update Invalid",
            slug=f"update-invalid-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    with pytest.raises(AgentGraphValidationError) as exc_info:
        await service.update_agent(
            agent.id,
            UpdateAgentData(graph_definition=_invalid_graph_missing_end()),
        )

    assert any("at least one End node" in entry["message"] for entry in exc_info.value.errors)


@pytest.mark.asyncio
async def test_service_update_graph_rejects_invalid_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Graph Update",
            slug=f"graph-update-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    with pytest.raises(AgentGraphValidationError):
        await service.update_graph(agent.id, _invalid_graph_missing_end())

    updated = await service.update_graph(agent.id, _valid_graph())
    assert isinstance(updated.graph_definition, dict)
    assert len(updated.graph_definition.get("nodes") or []) == 2


@pytest.mark.asyncio
async def test_create_endpoint_missing_graph_returns_validation_error(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    payload = {
        "name": "Missing Graph API",
        "slug": f"missing-graph-api-{uuid4().hex[:8]}",
        "description": "test",
        "graph_definition": None,
    }

    response = await client.post("/agents", json=payload, headers=_headers(user, tenant))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert any("graph_definition is required" in entry["message"] for entry in detail["errors"])


@pytest.mark.asyncio
async def test_update_endpoint_invalid_graph_returns_validation_error(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Patch Agent",
            slug=f"patch-agent-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    response = await client.patch(
        f"/agents/{agent.id}",
        json={"graph_definition": _invalid_graph_missing_end()},
        headers=_headers(user, tenant),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert any("at least one End node" in entry["message"] for entry in detail["errors"])


@pytest.mark.asyncio
async def test_update_graph_endpoint_invalid_graph_returns_validation_error(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, tenant_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Graph Endpoint Agent",
            slug=f"graph-endpoint-agent-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    response = await client.put(
        f"/agents/{agent.id}/graph",
        json=_invalid_graph_missing_end(),
        headers=_headers(user, tenant),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert any("at least one End node" in entry["message"] for entry in detail["errors"])
