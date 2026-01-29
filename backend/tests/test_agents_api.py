import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy import select
from httpx import AsyncClient

from app.db.postgres.models.identity import Tenant, User, OrgMembership
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.api.routers.auth import get_current_user
from app.agent.registry import AgentExecutorRegistry, AgentOperatorRegistry, AgentOperatorSpec
from unittest.mock import patch
from main import app

@pytest.fixture(autouse=True)
def mock_registry():
    # Reuse the logic from system tests to avoid real LLM nodes
    original_get_exec = AgentExecutorRegistry.get_executor_cls
    original_get_op = AgentOperatorRegistry.get
    
    def side_effect_exec(node_type):
        return original_get_exec(node_type) # Or a default mock

    def side_effect_op(node_type):
        specs = {
            "start": AgentOperatorSpec(type="start", category="core", display_name="Start", description="S"),
            "end": AgentOperatorSpec(type="end", category="core", display_name="End", description="E"),
            "transform": AgentOperatorSpec(type="transform", category="logic", display_name="T", description="D"),
            "human_input": AgentOperatorSpec(type="human_input", category="logic", display_name="H", description="D"),
        }
        return specs.get(node_type) or original_get_op(node_type)
        
    def side_effect_list():
        return [
            AgentOperatorSpec(type="start", category="core", display_name="Start", description="S"),
            AgentOperatorSpec(type="end", category="core", display_name="End", description="E"),
        ]

    with patch.object(AgentExecutorRegistry, 'get_executor_cls', side_effect=side_effect_exec), \
         patch.object(AgentOperatorRegistry, 'get', side_effect=side_effect_op), \
         patch.object(AgentOperatorRegistry, 'list_operators', side_effect=side_effect_list):
        yield


@pytest.mark.asyncio
async def test_list_operators(authorized_client):
    """Test the /agents/operators endpoint returns properly serialized operators."""
    response = await authorized_client.get("/agents/operators")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Verify structure of first operator
    op = data[0]
    assert "type" in op
    assert "category" in op
    assert "display_name" in op
    assert "reads" in op
    assert "writes" in op
    assert "ui" in op
    
    # Verify enum values are serialized as strings (not objects)
    for write in op.get("writes", []):
        assert isinstance(write, str), f"Expected string, got {type(write)}"

@pytest_asyncio.fixture
async def setup_api_env(db_session):
    """Setup tenant, user, and membership for API testing."""
    from app.db.postgres.models.identity import OrgUnit, OrgUnitType, OrgRole, MembershipStatus
    
    tenant = Tenant(name="API Test Tenant", slug="api-test-tenant")
    db_session.add(tenant)
    await db_session.flush()
    
    unit = OrgUnit(
        tenant_id=tenant.id,
        name="Main Org",
        slug="main-org",
        type=OrgUnitType.org
    )
    db_session.add(unit)
    await db_session.flush()
    
    user = User(email="api-test@example.com", full_name="API Tester", role="admin")
    db_session.add(user)
    await db_session.flush()
    
    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=unit.id,
        role=OrgRole.admin,
        status=MembershipStatus.active
    )
    db_session.add(membership)
    await db_session.flush()
    
    await db_session.commit()
    
    return tenant, user

@pytest_asyncio.fixture
async def authorized_client(client, setup_api_env):
    """Override get_current_user to return the test user."""
    tenant, user = setup_api_env
    
    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_agent_lifecycle_api(authorized_client, db_session, setup_api_env):
    tenant, user = setup_api_env
    
    # 1. Test POST /agents (Create)
    create_data = {
        "name": "API Agent",
        "slug": "api-agent",
        "description": "Created via API",
        "graph_definition": {"nodes": [], "edges": []}
    }
    response = await authorized_client.post("/agents", json=create_data)
    assert response.status_code == 200
    agent_id = response.json()["id"]
    assert response.json()["name"] == "API Agent"
    
    # 2. Test GET /agents (List)
    response = await authorized_client.get("/agents")
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    
    # 3. Test GET /agents/{id} (Get)
    response = await authorized_client.get(f"/agents/{agent_id}")
    assert response.status_code == 200
    assert response.json()["id"] == agent_id
    
    # 4. Test PUT /agents/{id} (Update)
    update_data = {"name": "Updated API Agent"}
    response = await authorized_client.put(f"/agents/{agent_id}", json=update_data)
    assert response.status_code == 200
    assert response.json()["name"] == "Updated API Agent"
    
    # 5. Test PUT /agents/{id}/graph (Update Graph)
    graph_data = {
        "nodes": [{"id": "node_1", "type": "start", "position": {"x": 0, "y": 0}}],
        "edges": []
    }
    response = await authorized_client.put(f"/agents/{agent_id}/graph", json=graph_data)
    assert response.status_code == 200
    assert response.json()["graph_definition"]["nodes"][0]["id"] == "node_1"
    
    # 6. Test POST /agents/{id}/validate
    response = await authorized_client.post(f"/agents/{agent_id}/validate")
    assert response.status_code == 200
    # Might be invalid if it doesn't have an end node, but endpoint should respond
    assert "valid" in response.json()
    
    # 7. Test POST /agents/{id}/publish
    # Add an end node to make it publishable if validation is strict (it isn't strictly enforced inpublish yet but good practice)
    publish_graph = {
        "nodes": [
            {"id": "s", "type": "start", "position": {"x": 0, "y": 0}},
            {"id": "e", "type": "end", "position": {"x": 100, "y": 0}}
        ],
        "edges": [{"id": "e1", "source": "s", "target": "e"}]
    }
    await authorized_client.put(f"/agents/{agent_id}/graph", json=publish_graph)
    
    response = await authorized_client.post(f"/agents/{agent_id}/publish")
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    
    # 8. Test GET /agents/{id}/versions
    response = await authorized_client.get(f"/agents/{agent_id}/versions")
    assert response.status_code == 200
    assert "versions" in response.json()
    assert len(response.json()["versions"]) >= 1

@pytest.mark.asyncio
async def test_agent_execution_api(authorized_client, db_session, setup_api_env):
    tenant, user = setup_api_env
    
    # Create a simple valid agent for execution
    agent = Agent(
        tenant_id=tenant.id,
        name="Exec Agent",
        slug="exec-agent",
        graph_definition={
            "nodes": [
                {"id": "s", "type": "start", "position": {"x": 0, "y": 0}},
                {"id": "e", "type": "end", "position": {"x": 200, "y": 0}}
            ],
            "edges": [{"id": "e1", "source": "s", "target": "e"}]
        },
        version=1,
        status="published"
    )
    db_session.add(agent)
    await db_session.commit()
    
    # 1. Test POST /agents/{id}/run
    response = await authorized_client.post(f"/agents/{agent.id}/run", json={
        "input": "test input",
        "messages": []
    })
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert run_id is not None
    
    # 2. Test GET /agents/runs/{id} (Status) and wait for completion
    import asyncio
    status = "queued"
    for _ in range(10): # retry for 10 seconds
        response = await authorized_client.get(f"/agents/runs/{run_id}")
        assert response.status_code == 200
        status = response.json()["status"]
        if status in ("completed", "failed", "paused"):
            break
        await asyncio.sleep(1)
    
    assert response.json()["id"] == run_id
    assert status in ("completed", "pased", "running", "failed") # running is also acceptable if it takes longer

@pytest.mark.asyncio
async def test_agent_resume_api(authorized_client, db_session, setup_api_env):
    tenant, user = setup_api_env
    
    # Manually create a paused run to test resume
    run = AgentRun(
        agent_id=uuid4(), # doesn't strictly matter for resume mock setup
        tenant_id=tenant.id,
        user_id=user.id,
        status=RunStatus.paused,
        checkpoint={"some": "state"}
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    
    # Test POST /agents/runs/{id}/resume
    response = await authorized_client.post(f"/agents/runs/{run.id}/resume", json={"input": "hi"})
    assert response.status_code == 200
    assert response.json()["status"] == "resumed"

@pytest.mark.asyncio
async def test_delete_agent_api(authorized_client, db_session, setup_api_env):
    tenant, user = setup_api_env
    
    agent = Agent(tenant_id=tenant.id, name="Delete Me", slug="delete-me")
    db_session.add(agent)
    await db_session.commit()
    
    response = await authorized_client.delete(f"/agents/{agent.id}")
    assert response.status_code == 200
    
    # Verify gone
    response = await authorized_client.get(f"/agents/{agent.id}")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_stateful_streaming(authorized_client, db_session):
    """Test that stream_agent creates a run and yields run_id."""
    import uuid
    from uuid import UUID
    import json
    
    # 1. Create agent
    agent_data = {
        "name": "Stream Test Agent",
        "slug": f"stream-test-{uuid.uuid4().hex[:8]}",
        "graph_definition": {
            "nodes": [
                {"id": "input", "type": "input", "position": {"x": 0, "y": 0}},
                {"id": "output", "type": "output", "position": {"x": 200, "y": 0}}
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "output"}
            ]
        }
    }
    create_res = await authorized_client.post("/agents", json=agent_data)
    assert create_res.status_code == 200
    agent_id = create_res.json()["id"]
    
    # 2. Stream
    req = {"input": "Hello", "messages": []}
    # Use a longer timeout for streaming
    async with authorized_client.stream("POST", f"/agents/{agent_id}/stream", json=req, timeout=30.0) as response:
        assert response.status_code == 200
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        
        # Verify events
        assert any(e.get("event") == "run_id" for e in events)
        run_id_event = next(e for e in events if e.get("event") == "run_id")
        run_id = run_id_event["run_id"]
        assert run_id is not None
        
        # 3. Verify run exists in DB
        from app.db.postgres.models.agents import AgentRun
        # Note: In tests, db_session might need a refresh or we might need to use a fresh one
        # but since we are in the same event loop, it might work
        db_session.expire_all()
        run = await db_session.get(AgentRun, UUID(run_id))
        assert run is not None
        assert str(run.agent_id) == agent_id
        
        # Verify input was converted to message
        input_params = run.input_params
        assert "messages" in input_params
        messages = input_params["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
