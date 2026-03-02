import pytest
from sqlalchemy import func, select

from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agent_threads import AgentThread
from app.db.postgres.models.published_apps import PublishedApp
from ._helpers import admin_headers, seed_admin_tenant_and_agent, seed_published_app


@pytest.mark.asyncio
async def test_preview_chat_stream_uses_preview_token_and_persists_thread(client, db_session, monkeypatch):
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
    original_start_run = AgentExecutorService.start_run

    async def wrapped_start_run(self, agent_id, run_payload, **kwargs):
        start_run_calls.append({"agent_id": str(agent_id), "payload": run_payload, "kwargs": kwargs})
        return await original_start_run(self, agent_id, run_payload, **kwargs)

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "Preview response"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.start_run", wrapped_start_run)
    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.run_and_stream", fake_run_and_stream)

    stream_resp = await client.post(
        f"/public/apps/preview/revisions/{draft_revision_id}/chat/stream",
        headers={"Authorization": f"Bearer {preview_token}"},
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
    thread_count = await db_session.scalar(
        select(func.count(AgentThread.id)).where(AgentThread.published_app_id == app.id)
    )
    assert thread_count == 1


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
    preview_token = state_resp.json()["preview_token"]
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    stream_resp = await client.post(
        f"/public/apps/preview/revisions/{draft_revision_id}/chat/stream",
        json={"input": "No token"},
    )
    assert stream_resp.status_code == 401

    query_only_resp = await client.post(
        f"/public/apps/preview/revisions/{draft_revision_id}/chat/stream?preview_token={preview_token}",
        json={"input": "Query token only"},
    )
    assert query_only_resp.status_code == 401
