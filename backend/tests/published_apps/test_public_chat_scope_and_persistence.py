import pytest
from sqlalchemy import func, select

from app.db.postgres.models.chat import Chat, Message
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_auth_service import PublishedAppAuthService
from ._helpers import admin_headers, seed_admin_tenant_and_agent, seed_published_app


@pytest.mark.asyncio
async def test_public_chat_stream_persists_messages_when_auth_enabled(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="chat-auth-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        f"/public/apps/{app.slug}/auth/signup",
        json={"email": "chat-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    token = signup_resp.json()["token"]

    async def fake_start_run(self, *args, **kwargs):
        return "run-123"

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "Hello from agent"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.start_run", fake_start_run)
    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.run_and_stream", fake_run_and_stream)

    stream_resp = await client.post(
        f"/public/apps/{app.slug}/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"input": "Hi there"},
    )
    assert stream_resp.status_code == 200
    assert "Hello from agent" in stream_resp.text

    chat_count = await db_session.scalar(
        select(func.count(Chat.id)).where(Chat.published_app_id == app.id)
    )
    assert chat_count == 1

    message_count = await db_session.scalar(
        select(func.count(Message.id)).join(Chat, Message.chat_id == Chat.id).where(Chat.published_app_id == app.id)
    )
    assert message_count == 2  # user + assistant

    list_resp = await client.get(
        f"/public/apps/{app.slug}/chats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    chat_id = list_resp.json()["items"][0]["id"]

    history_resp = await client.get(
        f"/public/apps/{app.slug}/chats/{chat_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history_resp.status_code == 200
    assert len(history_resp.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_public_chat_stream_ephemeral_when_auth_disabled(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="chat-public-app",
        auth_enabled=False,
        auth_providers=["password"],
    )

    async def fake_start_run(self, *args, **kwargs):
        return "run-ephemeral"

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "Public response"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.start_run", fake_start_run)
    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.run_and_stream", fake_run_and_stream)

    stream_resp = await client.post(
        f"/public/apps/{app.slug}/chat/stream",
        json={"input": "Public prompt"},
    )
    assert stream_resp.status_code == 200
    assert "Public response" in stream_resp.text

    chat_count = await db_session.scalar(
        select(func.count(Chat.id)).where(Chat.published_app_id == app.id)
    )
    assert chat_count == 0


@pytest.mark.asyncio
async def test_preview_chat_stream_uses_preview_token_and_runs_without_persistence(client, db_session, monkeypatch):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Preview Chat App",
            "slug": "preview-chat-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    state_payload = state_resp.json()
    draft_revision_id = state_payload["current_draft_revision"]["id"]
    preview_token = state_payload["preview_token"]
    assert preview_token

    start_run_calls = []

    async def fake_start_run(self, agent_id, run_payload, **kwargs):
        start_run_calls.append({"agent_id": str(agent_id), "payload": run_payload, "kwargs": kwargs})
        return "run-preview"

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "Preview response"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.start_run", fake_start_run)
    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.run_and_stream", fake_run_and_stream)

    stream_resp = await client.post(
        f"/public/apps/preview/revisions/{draft_revision_id}/chat/stream?preview_token={preview_token}",
        json={"input": "Preview prompt"},
    )
    assert stream_resp.status_code == 200
    assert "Preview response" in stream_resp.text
    assert start_run_calls
    run_context = start_run_calls[0]["payload"]["context"]
    assert run_context["published_app_preview"] is True
    assert run_context["published_app_preview_revision_id"] == draft_revision_id

    app = await db_session.scalar(select(PublishedApp).where(PublishedApp.slug == "preview-chat-app"))
    assert app is not None
    chat_count = await db_session.scalar(
        select(func.count(Chat.id)).where(Chat.published_app_id == app.id)
    )
    assert chat_count == 0


@pytest.mark.asyncio
async def test_preview_chat_stream_requires_preview_token(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Preview Chat Auth App",
            "slug": "preview-chat-auth-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": False,
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    stream_resp = await client.post(
        f"/public/apps/preview/revisions/{draft_revision_id}/chat/stream",
        json={"input": "No token"},
    )
    assert stream_resp.status_code == 401
