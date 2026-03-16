from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.agent_threads import AgentThread
from app.services.tenant_api_key_service import TenantAPIKeyService
from tests.published_apps._helpers import seed_admin_tenant_and_agent


def _embed_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_embed_key(db_session, *, tenant_id, created_by, scopes=None):
    api_key, token = await TenantAPIKeyService(db_session).create_api_key(
        tenant_id=tenant_id,
        name="Embed Runtime",
        scopes=scopes or ["agents.embed"],
        created_by=created_by,
    )
    await db_session.commit()
    return api_key, token


@pytest.mark.asyncio
async def test_embedded_agent_stream_persists_and_scopes_threads(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    api_key, token = await _create_embed_key(db_session, tenant_id=tenant.id, created_by=owner.id)

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "hello from embed"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.services.embedded_agent_runtime_service.AgentExecutorService.run_and_stream", fake_run_and_stream)

    stream_resp = await client.post(
        f"/public/embed/agents/{agent.id}/chat/stream",
        headers=_embed_headers(token),
        json={"input": "hi", "external_user_id": "customer-user-1"},
    )
    assert stream_resp.status_code == 200
    assert "hello from embed" in stream_resp.text
    thread_id = stream_resp.headers.get("X-Thread-ID")
    assert thread_id

    thread_count = await db_session.scalar(
        select(func.count(AgentThread.id)).where(AgentThread.agent_id == agent.id)
    )
    assert thread_count == 1

    stored_thread = await db_session.get(AgentThread, thread_id)
    assert stored_thread is not None
    assert stored_thread.external_user_id == "customer-user-1"
    assert str(stored_thread.tenant_api_key_id) == str(api_key.id)

    list_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["id"] == thread_id

    detail_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == thread_id

    await db_session.refresh(stored_thread)
    await db_session.refresh(api_key)
    assert stored_thread.last_activity_at is not None
    assert api_key.last_used_at is not None


@pytest.mark.asyncio
async def test_embedded_agent_routes_reject_wrong_scope_revoked_keys_and_cross_user_access(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    _, token = await _create_embed_key(db_session, tenant_id=tenant.id, created_by=owner.id)
    _, wrong_scope_token = await _create_embed_key(
        db_session,
        tenant_id=tenant.id,
        created_by=owner.id,
        scopes=["agents.read"],
    )
    revoked_key, revoked_token = await _create_embed_key(
        db_session,
        tenant_id=tenant.id,
        created_by=owner.id,
        scopes=["agents.embed"],
    )
    await TenantAPIKeyService(db_session).revoke_api_key(tenant_id=tenant.id, key_id=revoked_key.id)
    await db_session.commit()

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {"event": "token", "data": {"content": "ok"}, "visibility": "client_safe"}

    monkeypatch.setattr("app.services.embedded_agent_runtime_service.AgentExecutorService.run_and_stream", fake_run_and_stream)

    resp = await client.post(
        f"/public/embed/agents/{agent.id}/chat/stream",
        headers=_embed_headers(token),
        json={"input": "hi", "external_user_id": "customer-user-1"},
    )
    thread_id = resp.headers["X-Thread-ID"]

    cross_user = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-2"},
    )
    assert cross_user.status_code == 404

    wrong_scope_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads",
        headers=_embed_headers(wrong_scope_token),
        params={"external_user_id": "customer-user-1"},
    )
    assert wrong_scope_resp.status_code == 403

    revoked_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads",
        headers=_embed_headers(revoked_token),
        params={"external_user_id": "customer-user-1"},
    )
    assert revoked_resp.status_code == 401


@pytest.mark.asyncio
async def test_embedded_agent_runtime_rejects_draft_agents(client, db_session):
    tenant, owner, _, _ = await seed_admin_tenant_and_agent(db_session)
    _, token = await _create_embed_key(db_session, tenant_id=tenant.id, created_by=owner.id)

    draft_agent = Agent(
        tenant_id=tenant.id,
        name="Draft Agent",
        slug="draft-agent-embed",
        status=AgentStatus.draft,
        graph_definition={"nodes": [], "edges": []},
        created_by=owner.id,
    )
    db_session.add(draft_agent)
    await db_session.commit()

    resp = await client.post(
        f"/public/embed/agents/{draft_agent.id}/chat/stream",
        headers=_embed_headers(token),
        json={"input": "hi", "external_user_id": "customer-user-1"},
    )
    assert resp.status_code == 404
