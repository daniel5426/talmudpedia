import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ToolVersion
from app.api.routers.auth import get_current_user
from main import app

@pytest_asyncio.fixture
async def setup_tools_env(db_session):
    tenant = Tenant(name="Tools Tenant", slug="tools-tenant")
    db_session.add(tenant)
    await db_session.flush()

    user = User(email="tools-test@example.com", full_name="Tools Tester", role="admin")
    db_session.add(user)
    await db_session.flush()

    await db_session.commit()
    return tenant, user

@pytest_asyncio.fixture
async def authorized_client(client, setup_tools_env):
    _, user = setup_tools_env

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_tool_lifecycle_api(authorized_client, db_session):
    # Create tool
    create_data = {
        "name": "HTTP Tool",
        "slug": "http-tool",
        "description": "Test HTTP tool",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "http",
        "implementation_config": {"type": "http", "url": "https://example.com", "method": "POST"}
    }
    response = await authorized_client.post("/tools", json=create_data)
    assert response.status_code == 200
    tool = response.json()
    assert tool["implementation_type"] == "http"
    assert tool["status"] == "draft"
    assert tool["version"] == "1.0.0"
    assert tool["tool_type"] == "custom"

    tool_id = tool["id"]

    # List tools filtered by status
    response = await authorized_client.get("/tools?status=draft")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert any(t["id"] == tool_id for t in tools)

    # Publish tool
    response = await authorized_client.post(f"/tools/{tool_id}/publish")
    assert response.status_code == 200
    published = response.json()
    assert published["status"] == "published"
    assert published["published_at"] is not None

    # Ensure ToolVersion created
    res = await db_session.execute(select(ToolVersion).where(ToolVersion.tool_id == tool_id))
    versions = res.scalars().all()
    assert len(versions) >= 1

    # Create new version
    response = await authorized_client.post(f"/tools/{tool_id}/version?new_version=2.0.0")
    assert response.status_code == 200
    versioned = response.json()
    assert versioned["version"] == "2.0.0"
