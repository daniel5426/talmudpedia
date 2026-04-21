from __future__ import annotations
import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.execution.service import AgentExecutorService
from app.api.routers.published_apps_admin_routes_coding_agent_v2 import _build_remote_session_catchup_events
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingChatSession,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.services.opencode_server_client import OpenCodeServerClient
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_chat_session_service import PublishedAppCodingChatSessionService
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent
from types import SimpleNamespace


def test_opencode_runs_skip_model_registry_resolution_for_context_only_model_refs():
    assert AgentExecutorService._should_skip_model_registry_resolution(
        {"execution_engine": "opencode", "requested_model_id": "opencode/gpt-5"}
    )


def test_non_opencode_runs_keep_model_registry_resolution_enabled():
    assert not AgentExecutorService._should_skip_model_registry_resolution(
        {"execution_engine": "langgraph", "requested_model_id": "opencode/gpt-5"}
    )


async def _create_app_and_draft_revision(db_session, *, organization_id: UUID, user_id: UUID, agent_id: UUID) -> str:
    app = PublishedApp(
        organization_id=organization_id,
        agent_id=agent_id,
        name=f"Coding Agent V2 App {uuid4().hex[:6]}",
        slug=f"coding-agent-v2-{uuid4().hex[:10]}",
        status=PublishedAppStatus.draft,
        visibility=PublishedAppVisibility.public,
        auth_enabled=True,
        auth_providers=["password"],
        auth_template_key="auth-classic",
        template_key="classic-chat",
        created_by=user_id,
    )
    db_session.add(app)
    await db_session.flush()

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key="classic-chat",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default function App() { return null; }\n"},
        manifest_json={},
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        origin_kind="app_init",
        created_by=user_id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_draft_revision_id = revision.id
    await db_session.commit()
    return str(app.id)


async def _create_chat_session(
    db_session,
    *,
    app_id: UUID,
    user_id: UUID,
    title: str = "Test Session",
    opencode_session_id: str | None = None,
) -> PublishedAppCodingChatSession:
    session = PublishedAppCodingChatSession(
        published_app_id=app_id,
        user_id=user_id,
        title=title,
        opencode_session_id=opencode_session_id,
        opencode_sandbox_id="sandbox-1" if opencode_session_id else None,
        opencode_workspace_path="/workspace" if opencode_session_id else None,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_v2_chat_session_create_and_list_routes(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )

    create_response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions",
        headers=headers,
        json={"title": "Session A"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["title"] == "Session A"

    list_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions",
        headers=headers,
    )
    assert list_response.status_code == 200
    sessions = list_response.json()
    assert any(item["id"] == created["id"] for item in sessions)

    removed_route = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/prompts",
        headers=headers,
        json={"input": "hello"},
    )
    assert removed_route.status_code == 404


@pytest.mark.asyncio
async def test_v2_chat_session_submit_message_and_list_history(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    session = await _create_chat_session(db_session, app_id=UUID(app_id), user_id=user.id)

    async def _fake_submit_message(self, **kwargs):
        _ = self, kwargs
        return {
            "submission_status": "accepted",
            "chat_session_id": str(session.id),
            "message": {
                "id": "msg-1",
                "role": "user",
                "content": "Hello there",
                "parts": [{"id": "msg-1-part-1", "type": "text", "text": "Hello there"}],
                "created_at": "2026-04-17T00:00:00Z",
            },
        }

    async def _fake_list_remote_messages(self, *, chat_session, limit=200):
        _ = self, limit
        assert str(chat_session.id) == str(session.id)
        return [
            {
                "id": "msg-1",
                "role": "user",
                "content": "Hello there",
                "parts": [{"id": "msg-1-part-1", "type": "text", "text": "Hello there"}],
                "created_at": "2026-04-17T00:00:00Z",
            },
            {
                "id": "msg-2",
                "role": "assistant",
                "content": "Hi!",
                "parts": [{"id": "msg-2-part-1", "type": "text", "text": "Hi!"}],
                "created_at": "2026-04-17T00:00:01Z",
            },
        ]

    monkeypatch.setattr(PublishedAppCodingChatSessionService, "submit_message", _fake_submit_message)
    monkeypatch.setattr(PublishedAppCodingChatSessionService, "list_remote_messages", _fake_list_remote_messages)

    submit_response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}/messages",
        headers=headers,
        json={"message_id": "msg-1", "parts": [{"type": "text", "text": "Hello there"}]},
    )
    assert submit_response.status_code == 200
    payload = submit_response.json()
    assert payload["submission_status"] == "accepted"
    assert payload["chat_session_id"] == str(session.id)
    assert "run_id" not in payload

    history_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}",
        headers=headers,
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert [item["role"] for item in history["messages"]] == ["user", "assistant"]
    assert history["paging"]["has_more"] is False


@pytest.mark.asyncio
async def test_v2_chat_session_history_route_survives_expired_updated_at(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    session = await _create_chat_session(db_session, app_id=UUID(app_id), user_id=user.id, opencode_session_id="ses-1")

    async def _fake_list_remote_messages(self, *, chat_session, limit=200):
        _ = limit
        self.db.sync_session.expire(chat_session, ["updated_at"])
        return [
            {
                "id": "msg-1",
                "role": "assistant",
                "content": "hello",
                "parts": [{"id": "part-1", "type": "text", "text": "hello"}],
                "created_at": "2026-04-17T00:00:01Z",
            },
        ]

    monkeypatch.setattr(PublishedAppCodingChatSessionService, "list_remote_messages", _fake_list_remote_messages)

    history_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}",
        headers=headers,
    )
    assert history_response.status_code == 200
    payload = history_response.json()
    assert payload["session"]["id"] == str(session.id)
    assert payload["messages"][0]["content"] == "hello"


@pytest.mark.asyncio
async def test_remote_session_catchup_skips_previous_assistant_when_new_user_turn_exists(db_session):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        opencode_session_id="ses-1",
    )
    service = PublishedAppCodingChatSessionService(db_session)

    async def _fake_list_messages(**kwargs):
        _ = kwargs
        return [
            {
                "info": {"id": "msg-user-1", "role": "user", "sessionID": "ses-1", "time": {"created": 1}},
                "parts": [{"id": "part-user-1", "type": "text", "text": "first", "messageID": "msg-user-1"}],
            },
            {
                "info": {
                    "id": "msg-assistant-1",
                    "parentID": "msg-user-1",
                    "role": "assistant",
                    "sessionID": "ses-1",
                    "time": {"created": 2, "completed": 3},
                    "finish": "stop",
                },
                "parts": [{"id": "part-assistant-1", "type": "text", "text": "done", "messageID": "msg-assistant-1"}],
            },
            {
                "info": {"id": "msg-user-2", "role": "user", "sessionID": "ses-1", "time": {"created": 4}},
                "parts": [{"id": "part-user-2", "type": "text", "text": "next", "messageID": "msg-user-2"}],
            },
        ]

    service.client = SimpleNamespace(list_messages=_fake_list_messages)
    events = await _build_remote_session_catchup_events(service=service, chat_session=session)
    assert events == []


@pytest.mark.asyncio
async def test_chat_session_lookup_reloads_remote_session_updates(db_session):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    session = await _create_chat_session(db_session, app_id=UUID(app_id), user_id=user.id)

    reader_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    writer_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async with reader_factory() as reader_session:
        history = PublishedAppCodingChatHistoryService(reader_session)
        first = await history.get_session_for_user(
            app_id=UUID(app_id),
            user_id=user.id,
            session_id=session.id,
        )
        assert first is not None
        assert first.opencode_session_id is None

        async with writer_factory() as writer_session:
            await writer_session.execute(
                update(PublishedAppCodingChatSession)
                .where(PublishedAppCodingChatSession.id == session.id)
                .values(
                    opencode_session_id="ses-live",
                    opencode_sandbox_id="sandbox-1",
                    opencode_workspace_path="/workspace",
                )
            )
            await writer_session.commit()

        reloaded = await history.get_session_for_user(
            app_id=UUID(app_id),
            user_id=user.id,
            session_id=session.id,
        )
        assert reloaded is not None
        assert reloaded.opencode_session_id == "ses-live"
        assert reloaded.opencode_sandbox_id == "sandbox-1"
        assert reloaded.opencode_workspace_path == "/workspace"


@pytest.mark.asyncio
async def test_v2_chat_session_events_abort_and_permission_routes(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        opencode_session_id="ses-123",
    )

    async def _fake_stream_session_events(self, *, session_id, sandbox_id=None, workspace_path=None):
        _ = self, sandbox_id, workspace_path
        assert session_id == "ses-123"
        yield {"event": "message.part.updated", "session_id": str(session.id), "payload": {"delta": "A", "part": {"id": "p1", "messageID": "m1", "type": "text"}}}
        yield {"event": "session.idle", "session_id": str(session.id), "payload": {}}

    async def _fake_list_messages(self, *, session_id, sandbox_id=None, workspace_path=None, limit=None):
        _ = self, session_id, sandbox_id, workspace_path, limit
        return []

    async def _fake_abort(self, *, chat_session):
        _ = self
        assert str(chat_session.id) == str(session.id)
        return True

    async def _fake_reply_request(self, *, chat_session, request_id, answers):
        _ = self
        assert str(chat_session.id) == str(session.id)
        assert request_id == "perm-1"
        assert answers == [["Allow"]]
        return True

    monkeypatch.setattr(OpenCodeServerClient, "list_messages", _fake_list_messages)
    monkeypatch.setattr(OpenCodeServerClient, "stream_session_events", _fake_stream_session_events)
    monkeypatch.setattr(PublishedAppCodingChatSessionService, "abort_chat_session", _fake_abort)
    monkeypatch.setattr(PublishedAppCodingChatSessionService, "reply_request", _fake_reply_request)

    events_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}/events",
        headers=headers,
    )
    assert events_response.status_code == 200
    text = events_response.text
    assert '"event": "session.connected"' in text
    assert '"event": "message.part.updated"' in text
    assert '"event": "session.idle"' in text

    abort_response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}/abort",
        headers=headers,
        json={},
    )
    assert abort_response.status_code == 200
    assert abort_response.json() == {"ok": True}

    permission_response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}/permissions/perm-1",
        headers=headers,
        json={"answers": [["Allow"]]},
    )
    assert permission_response.status_code == 200
    assert permission_response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_v2_chat_session_events_do_not_emit_heartbeat_catchup_during_live_turn(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id = await _create_app_and_draft_revision(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
    )
    session = await _create_chat_session(
        db_session,
        app_id=UUID(app_id),
        user_id=user.id,
        opencode_session_id="ses-123",
    )
    list_calls = {"count": 0}

    async def _fake_stream_session_events(self, *, session_id, sandbox_id=None, workspace_path=None):
        _ = self, sandbox_id, workspace_path
        assert session_id == "ses-123"
        await asyncio.sleep(1.2)
        yield {
            "event": "message.part.updated",
            "session_id": str(session.id),
            "payload": {
                "part": {
                    "id": "assistant-text-1",
                    "messageID": "assistant-1",
                    "type": "text",
                    "text": "live text",
                },
            },
        }
        yield {"event": "session.idle", "session_id": str(session.id), "payload": {}}

    async def _fake_list_messages(self, *, session_id, sandbox_id=None, workspace_path=None, limit=None):
        _ = self, session_id, sandbox_id, workspace_path, limit
        list_calls["count"] += 1
        if list_calls["count"] == 1:
            return []
        return [
            {
                "info": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "sessionID": "ses-123",
                    "time": {"created": 10, "completed": 20},
                    "finish": "stop",
                },
                "parts": [
                    {
                        "id": "assistant-text-1",
                        "messageID": "assistant-1",
                        "type": "text",
                        "text": "catchup text",
                    }
                ],
            }
        ]

    monkeypatch.setattr(OpenCodeServerClient, "list_messages", _fake_list_messages)
    monkeypatch.setattr(OpenCodeServerClient, "stream_session_events", _fake_stream_session_events)

    events_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}/events",
        headers=headers,
    )
    assert events_response.status_code == 200
    text = events_response.text
    assert '"event": "session.connected"' in text
    assert '"text": "live text"' in text
    assert '"text": "catchup text"' not in text
    assert list_calls["count"] == 1
