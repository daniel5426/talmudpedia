import pytest
import pytest_asyncio
from uuid import uuid4
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.agents import Agent, AgentStatus

@pytest_asyncio.fixture
async def setup_data(db_session):
    """Setup a tenant and user for testing."""
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()
    
    user = User(email="test@example.com", full_name="Test User", role="admin")
    db_session.add(user)
    await db_session.flush()
    
    return tenant, user

@pytest.mark.asyncio
async def test_list_agents_empty(client, setup_data):
    response = await client.get("/agents")
    assert response.status_code == 200
    data = response.json()
    assert data["agents"] == []
    assert data["total"] == 0

@pytest.mark.asyncio
async def test_create_agent_api(client, setup_data):
    payload = {
        "name": "API Agent",
        "slug": "api-agent",
        "description": "Created via API"
    }
    response = await client.post("/agents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "API Agent"
    assert data["slug"] == "api-agent"
    assert "id" in data

@pytest.mark.asyncio
async def test_get_agent_api(client, db_session, setup_data):
    tenant, user = setup_data
    agent = Agent(
        tenant_id=tenant.id,
        name="Get API Test",
        slug="get-api-test",
        graph_definition={"nodes": [], "edges": []}
    )
    db_session.add(agent)
    await db_session.commit() # Need to commit to see it in router's session if iso isn't perfect
    
    response = await client.get(f"/agents/{agent.id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Get API Test"

@pytest.mark.asyncio
async def test_update_agent_api(client, db_session, setup_data):
    tenant, user = setup_data
    agent = Agent(
        tenant_id=tenant.id,
        name="Old Name",
        slug="update-api-test",
        graph_definition={"nodes": [], "edges": []}
    )
    db_session.add(agent)
    await db_session.commit()
    
    payload = {"name": "New Name"}
    response = await client.put(f"/agents/{agent.id}", json=payload)
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"

@pytest.mark.asyncio
async def test_publish_agent_api(client, db_session, setup_data):
    tenant, user = setup_data
    agent = Agent(
        tenant_id=tenant.id,
        name="Publish API Test",
        slug="publish-api-test",
        graph_definition={"nodes": [], "edges": []}
    )
    db_session.add(agent)
    await db_session.commit()
    
    response = await client.post(f"/agents/{agent.id}/publish")
    assert response.status_code == 200
    assert response.json()["status"] == "published"

@pytest.mark.asyncio
async def test_delete_agent_api(client, db_session, setup_data):
    tenant, user = setup_data
    agent = Agent(
        tenant_id=tenant.id,
        name="Delete Me",
        slug="delete-me",
        graph_definition={"nodes": [], "edges": []}
    )
    db_session.add(agent)
    await db_session.commit()
    
    response = await client.delete(f"/agents/{agent.id}")
    assert response.status_code == 200
    
    # Try to get it again
    response = await client.get(f"/agents/{agent.id}")
    assert response.status_code == 404
