import pytest
import pytest_asyncio
import json
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.api.routers.agent import chat_agent

@pytest_asyncio.fixture
async def setup_chat_data(db_session):
    """Setup a tenant and user for testing."""
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()
    
    user = User(id=uuid4(), email="chat@example.com", full_name="Chat User", role="user")
    db_session.add(user)
    await db_session.commit()
    
    return tenant, user

@pytest.mark.asyncio
async def test_chat_endpoint_new_chat(client, db_session, setup_chat_data):
    tenant, user = setup_chat_data
    
    # Mock authentication to return our user
    # Note: client fixture in conftest already overrides get_db, 
    # but we need to ensure current_user is mocked correctly if not using real JWT
    from app.api.routers.auth import get_current_user
    async def mock_get_current_user():
        return user
    from main import app
    app.dependency_overrides[get_current_user] = mock_get_current_user

    # Mock agent astream_events
    class MockChunk:
        def __init__(self, content):
            self.content = content
            self.tool_call_chunks = []
    
    mock_events = [
        {"event": "on_custom_event", "name": "reasoning_step", "data": {"step": "Analysis", "status": "complete"}},
        {"event": "on_chat_model_stream", "data": {"chunk": MockChunk("Hello")}},
        {"event": "on_chat_model_stream", "data": {"chunk": MockChunk(" world")}},
    ]
    
    async def mock_astream_events(*args, **kwargs):
        for event in mock_events:
            yield event

    with patch.object(chat_agent, "astream_events", side_effect=mock_astream_events):
        payload = {"message": "Hello agent"}
        response = await client.post("/chat", json=payload)
        
        assert response.status_code == 200
        
        # Collect streaming response
        tokens = []
        async for line in response.aiter_lines():
            if line:
                data = json.loads(line)
                if data["type"] == "token":
                    tokens.append(data["content"])
        
        assert "".join(tokens) == "Hello world"
        
        # Verify DB records
        from sqlalchemy import select
        result = await db_session.execute(select(Chat).where(Chat.user_id == user.id))
        chat = result.scalar_one()
        assert chat.title.startswith("Hello agent")
        
        result = await db_session.execute(select(Message).where(Message.chat_id == chat.id).order_by(Message.index))
        messages = result.scalars().all()
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[0].content == "Hello agent"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content == "Hello world"

    app.dependency_overrides.pop(get_current_user)

@pytest.mark.asyncio
async def test_chat_endpoint_existing_chat(client, db_session, setup_chat_data):
    tenant, user = setup_chat_data
    
    chat = Chat(tenant_id=tenant.id, user_id=user.id, title="Existing Chat")
    db_session.add(chat)
    await db_session.commit()
    
    from app.api.routers.auth import get_current_user
    async def mock_get_current_user():
        return user
    from main import app
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    class MockChunk:
        def __init__(self, content):
            self.content = content
            self.tool_call_chunks = []

    mock_events = [
        {"event": "on_chat_model_stream", "data": {"chunk": MockChunk("Response")}},
    ]
    async def mock_astream_events(*args, **kwargs):
        for event in mock_events:
            yield event

    with patch.object(chat_agent, "astream_events", side_effect=mock_astream_events):
        payload = {"message": "Follow up", "chatId": str(chat.id)}
        response = await client.post("/chat", json=payload)
        assert response.status_code == 200
        
        result = await db_session.execute(select(Message).where(Message.chat_id == chat.id).order_by(Message.index))
        messages = result.scalars().all()
        # Should have 2 now (User: Follow up, Assistant: Response)
        assert len(messages) == 2
        assert messages[0].content == "Follow up"
        assert messages[1].content == "Response"

    app.dependency_overrides.pop(get_current_user)
