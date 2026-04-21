from __future__ import annotations

from uuid import uuid4

import pytest
import jwt

from app.core.security import ALGORITHM, SECRET_KEY, create_access_token
from app.db.postgres.models.identity import Organization, User
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


def _graph_with_missing_runtime_refs() -> dict:
    return {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "assistant",
                "type": "agent",
                "position": {"x": 150, "y": 0},
                "config": {"model_id": "11111111-1111-1111-1111-111111111111", "instructions": "help"},
            },
            {
                "id": "tool_call",
                "type": "tool",
                "position": {"x": 300, "y": 0},
                "config": {"tool_id": "22222222-2222-2222-2222-222222222222"},
            },
            {"id": "end", "type": "end", "position": {"x": 450, "y": 0}, "config": {"output_message": "done"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "assistant", "type": "control"},
            {"id": "e2", "source": "assistant", "target": "tool_call", "type": "control"},
            {"id": "e3", "source": "tool_call", "target": "end", "type": "control"},
        ],
    }


def _graph_with_agent_model_only_in_data_config() -> dict:
    return {
        "spec_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "assistant",
                "type": "agent",
                "position": {"x": 150, "y": 0},
                "config": {},
                "data": {"config": {"model_id": "legacy-only-model", "instructions": "help"}},
            },
            {"id": "end", "type": "end", "position": {"x": 300, "y": 0}, "config": {"output_message": "done"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "assistant", "type": "control"},
            {"id": "e2", "source": "assistant", "target": "end", "type": "control"},
        ],
    }


async def _seed_tenant_admin(db_session):
    suffix = uuid4().hex[:8]
    tenant = Organization(name=f"Organization {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"admin-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


def _headers(user: User, tenant: Organization) -> dict[str, str]:
    base_token = create_access_token(
        subject=str(user.id),
        organization_id=str(tenant.id),
        org_role="owner",
    )
    payload = jwt.decode(base_token, SECRET_KEY, algorithms=[ALGORITHM])
    payload["scope"] = ["agents.read", "agents.write"]
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": str(tenant.id)}


@pytest.mark.asyncio
async def test_service_create_rejects_missing_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)

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
async def test_service_create_accepts_incomplete_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)

    agent = await service.create_agent(
        CreateAgentData(
            name="Empty Graph",
            slug=f"empty-graph-{uuid4().hex[:8]}",
            graph_definition={"spec_version": "1.0", "nodes": [], "edges": []},
        )
    )

    assert isinstance(agent.graph_definition, dict)
    assert agent.graph_definition["nodes"] == []
    assert agent.graph_definition["edges"] == []


@pytest.mark.asyncio
async def test_service_update_without_graph_still_succeeds(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)
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
async def test_service_update_accepts_incomplete_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Update Invalid",
            slug=f"update-invalid-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    updated = await service.update_agent(
        agent.id,
        UpdateAgentData(graph_definition=_invalid_graph_missing_end()),
    )

    assert isinstance(updated.graph_definition, dict)
    assert len(updated.graph_definition["nodes"]) == 1
    assert updated.graph_definition["edges"] == []


@pytest.mark.asyncio
async def test_service_update_graph_accepts_incomplete_graph(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Graph Update",
            slug=f"graph-update-{uuid4().hex[:8]}",
            graph_definition=_valid_graph(),
        ),
        user_id=user.id,
    )

    updated = await service.update_graph(agent.id, _invalid_graph_missing_end())
    assert isinstance(updated.graph_definition, dict)
    assert len(updated.graph_definition["nodes"]) == 1
    assert updated.graph_definition["edges"] == []

    updated = await service.update_graph(agent.id, _valid_graph())
    assert isinstance(updated.graph_definition, dict)
    assert len(updated.graph_definition.get("nodes") or []) == 2


@pytest.mark.asyncio
async def test_service_create_ignores_runtime_config_inside_data_payload(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)

    agent = await service.create_agent(
        CreateAgentData(
            name="Legacy Data Config",
            slug=f"legacy-data-config-{uuid4().hex[:8]}",
            graph_definition=_graph_with_agent_model_only_in_data_config(),
        ),
        user_id=user.id,
    )

    assistant = next(node for node in agent.graph_definition["nodes"] if node["id"] == "assistant")
    assert assistant["config"].get("model_id") is None


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
    assert detail["message"] == "Graph write rejected"
    assert any(
        "graph_definition is required" in str(entry.get("message"))
        for entry in detail.get("details", {}).get("errors", [])
    )


@pytest.mark.asyncio
async def test_update_endpoint_accepts_incomplete_graph(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)
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

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["graph_definition"], dict)
    assert len(payload["graph_definition"]["nodes"]) == 1


@pytest.mark.asyncio
async def test_update_graph_endpoint_accepts_incomplete_graph(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)
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

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["graph_definition"], dict)
    assert len(payload["graph_definition"]["nodes"]) == 1


@pytest.mark.asyncio
async def test_service_validate_graph_reports_runtime_reference_errors(db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)

    result = await service._build_validation_result_for_graph(
        _graph_with_missing_runtime_refs(),
        agent_id=uuid4(),
    )

    assert result.valid is False
    codes = {entry["code"] for entry in result.errors}
    assert "MODEL_NOT_FOUND" in codes
    assert "TOOL_NOT_FOUND" in codes


@pytest.mark.asyncio
async def test_validate_endpoint_returns_structured_errors_and_warnings(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    service = AgentService(db=db_session, organization_id=tenant.id)
    agent = await service.create_agent(
        CreateAgentData(
            name="Validate Endpoint Shape",
            slug=f"validate-endpoint-shape-{uuid4().hex[:8]}",
            graph_definition=_invalid_graph_missing_end(),
        ),
        user_id=user.id,
    )

    response = await client.post(
        f"/agents/{agent.id}/validate",
        headers=_headers(user, tenant),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert isinstance(payload.get("errors"), list)
    assert isinstance(payload.get("warnings"), list)
    assert any("code" in item for item in payload["errors"])
    assert any("path" in item for item in payload["errors"])


@pytest.mark.asyncio
async def test_nodes_catalog_and_schema_endpoints(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)
    headers = _headers(user, tenant)

    catalog_response = await client.get("/agents/nodes/catalog", headers=headers)
    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    nodes = catalog_payload.get("nodes") or []
    assert isinstance(nodes, list)
    assert any(item.get("type") == "agent" for item in nodes)

    schema_response = await client.post(
        "/agents/nodes/schema",
        json={"node_types": ["agent", "tool"]},
        headers=headers,
    )
    assert schema_response.status_code == 200
    schema_payload = schema_response.json()
    assert "agent" in schema_payload.get("schemas", {})
    assert "tool" in schema_payload.get("schemas", {})
    assert schema_payload.get("unknown", []) == []


@pytest.mark.asyncio
async def test_nodes_schema_requires_non_empty_node_types(client, db_session):
    tenant, user = await _seed_tenant_admin(db_session)

    response = await client.post(
        "/agents/nodes/schema",
        json={"node_types": []},
        headers=_headers(user, tenant),
    )
    assert response.status_code == 422
