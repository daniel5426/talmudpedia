import pytest
import pytest_asyncio

from uuid import uuid4
from sqlalchemy import select
from app.services.agent_service import AgentService, CreateAgentData, UpdateAgentData
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.agents import Agent, AgentStatus

@pytest_asyncio.fixture
async def setup_tenant_user(db_session):

    """Setup a tenant and user for testing."""
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()
    
    user = User(email="test@example.com", full_name="Test User", role="admin")
    db_session.add(user)
    await db_session.flush()
    
    return tenant, user

@pytest.mark.asyncio
async def test_create_agent(db_session, setup_tenant_user):
    tenant, user = setup_tenant_user
    service = AgentService(db=db_session, tenant_id=tenant.id)
    
    data = CreateAgentData(
        name="Test Agent",
        slug="test-agent",
        description="A test agent",
        graph_definition={"nodes": [], "edges": []}
    )
    
    agent = await service.create_agent(data, user_id=user.id)
    
    assert agent.name == "Test Agent"
    assert agent.slug == "test-agent"
    assert agent.tenant_id == tenant.id
    assert agent.status == AgentStatus.draft

@pytest.mark.asyncio
async def test_get_agent(db_session, setup_tenant_user):
    tenant, user = setup_tenant_user
    service = AgentService(db=db_session, tenant_id=tenant.id)
    
    # Create an agent first
    agent = Agent(
        tenant_id=tenant.id,
        name="Get Test",
        slug="get-test",
        graph_definition={"nodes": [], "edges": []}
    )
    db_session.add(agent)
    await db_session.flush()
    
    fetched = await service.get_agent(agent.id)
    assert fetched.id == agent.id
    assert fetched.name == "Get Test"

@pytest.mark.asyncio
async def test_update_agent(db_session, setup_tenant_user):
    tenant, user = setup_tenant_user
    service = AgentService(db=db_session, tenant_id=tenant.id)
    
    agent = Agent(
        tenant_id=tenant.id,
        name="Update Test",
        slug="update-test",
        graph_definition={"nodes": [], "edges": []}
    )
    db_session.add(agent)
    await db_session.flush()
    
    update_data = UpdateAgentData(name="Updated Name", description="New description")
    updated = await service.update_agent(agent.id, update_data)
    
    assert updated.name == "Updated Name"
    assert updated.description == "New description"

@pytest.mark.asyncio
async def test_publish_agent(db_session, setup_tenant_user):
    tenant, user = setup_tenant_user
    service = AgentService(db=db_session, tenant_id=tenant.id)
    
    agent = Agent(
        tenant_id=tenant.id,
        name="Publish Test",
        slug="publish-test",
        graph_definition={"nodes": [], "edges": []},
        version=1
    )
    db_session.add(agent)
    await db_session.flush()
    
    published = await service.publish_agent(agent.id)
    
    assert published.status == AgentStatus.published
    assert published.version == 2 # According to AgentService implementation
    assert published.published_at is not None
    
    # Check if version record was created
    from app.db.postgres.models.agents import AgentVersion
    result = await db_session.execute(select(AgentVersion).where(AgentVersion.agent_id == agent.id))
    version_record = result.scalars().first()
    assert version_record is not None
    assert version_record.version == 1
