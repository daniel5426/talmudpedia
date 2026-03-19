from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn, AgentThreadTurnStatus
from app.db.postgres.models.runtime_attachments import (
    AgentThreadTurnAttachment,
    RuntimeAttachment,
    RuntimeAttachmentStatus,
)
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


def _extract_stream_events(stream_text: str) -> list[dict]:
    events: list[dict] = []
    for block in stream_text.split("\n\n"):
        for line in block.splitlines():
            if not line.startswith("data: "):
                continue
            events.append(json.loads(line[len("data: ") :]))
    return events


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
    stream_events = _extract_stream_events(stream_resp.text)
    assert stream_events[0]["version"] == "run-stream.v2"
    assert stream_events[0]["event"] == "run.accepted"
    assert any(event["event"] == "assistant.delta" for event in stream_events)
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
async def test_embedded_agent_thread_detail_includes_run_events_and_delete_route(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    _, token = await _create_embed_key(db_session, tenant_id=tenant.id, created_by=owner.id)

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
    thread_id = stream_resp.headers["X-Thread-ID"]

    stored_thread = await db_session.get(AgentThread, thread_id)
    assert stored_thread is not None
    run_row = await db_session.scalar(
        select(AgentRun).where(AgentRun.thread_id == UUID(thread_id)).limit(1)
    )
    assert run_row is not None
    db_session.add(
        AgentThreadTurn(
            thread_id=UUID(thread_id),
            run_id=run_row.id,
            turn_index=0,
            user_input_text="hi",
            assistant_output_text="hello from embed",
            status=AgentThreadTurnStatus.completed,
        )
    )
    stored_thread.last_run_id = run_row.id
    await db_session.commit()

    initial_detail_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert initial_detail_resp.status_code == 200
    initial_turn = initial_detail_resp.json()["turns"][0]
    run_id = UUID(initial_turn["run_id"])

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    await recorder.save_event(
        run_id,
        db_session,
        {
            "event": "on_tool_start",
            "name": "lookup_client",
            "span_id": "tool-call-1",
            "visibility": "internal",
            "data": {
                "input": {"client_id": "32001"},
                "display_name": "Lookup client",
                "summary": "Looking up client data",
                "message": "Looking up client data",
            },
        },
    )
    await recorder.save_event(
        run_id,
        db_session,
        {
            "event": "on_tool_end",
            "name": "lookup_client",
            "span_id": "tool-call-1",
            "visibility": "internal",
            "data": {
                "output": {"client_id": "32001"},
                "display_name": "Lookup client",
                "summary": "Client data loaded",
            },
        },
    )
    await recorder.save_event(
        run_id,
        db_session,
        {
            "event": "assistant.widget",
            "visibility": "client_safe",
            "data": {
                "widget_id": "widget-1",
                "widget_type": "bar_chart",
                "title": "Bank concentration",
                "spec": {
                    "data": [
                        {"bank": "Leumi", "share_pct": 42},
                        {"bank": "Hapoalim", "share_pct": 31},
                    ],
                    "xKey": "bank",
                    "yKey": "share_pct",
                    "format": "percent",
                },
                "version": 1,
            },
        },
    )
    await db_session.commit()

    detail_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()
    assert payload["id"] == thread_id
    assert len(payload["turns"]) == 1
    turn = payload["turns"][0]
    assert turn["run_id"] == str(run_id)
    assert [item["event"] for item in turn["run_events"]] == [
        "tool.started",
        "reasoning.update",
        "tool.completed",
        "reasoning.update",
        "assistant.widget",
    ]
    assert [item["run_id"] for item in turn["run_events"]] == [str(run_id)] * 5
    widget_event = turn["run_events"][-1]
    assert widget_event["payload"]["widget_type"] == "bar_chart"
    assert widget_event["payload"]["title"] == "Bank concentration"

    delete_resp = await client.delete(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"deleted": True}

    list_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 0

    missing_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert missing_resp.status_code == 404


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

    cross_user_delete = await client.delete(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-2"},
    )
    assert cross_user_delete.status_code == 404

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


@pytest.mark.asyncio
async def test_embedded_agent_attachment_upload_processing_and_delete_cleanup(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("RUNTIME_ATTACHMENT_STORAGE_DIR", str(tmp_path))
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    _, token = await _create_embed_key(db_session, tenant_id=tenant.id, created_by=owner.id)

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "processed attachment"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.services.embedded_agent_runtime_service.AgentExecutorService.run_and_stream", fake_run_and_stream)

    upload_resp = await client.post(
        f"/public/embed/agents/{agent.id}/attachments/upload",
        headers=_embed_headers(token),
        data={"external_user_id": "customer-user-1"},
        files=[("files", ("brief.txt", b"Quarterly results are strong.", "text/plain"))],
    )
    assert upload_resp.status_code == 200
    upload_payload = upload_resp.json()
    assert len(upload_payload["items"]) == 1
    attachment_id = upload_payload["items"][0]["id"]

    attachment = await db_session.get(RuntimeAttachment, UUID(attachment_id))
    assert attachment is not None
    assert attachment.status == RuntimeAttachmentStatus.uploaded
    storage_path = Path(tmp_path) / str(attachment.storage_key)
    assert storage_path.exists()

    stream_resp = await client.post(
        f"/public/embed/agents/{agent.id}/chat/stream",
        headers=_embed_headers(token),
        json={
            "input": "Summarize the file",
            "attachment_ids": [attachment_id],
            "external_user_id": "customer-user-1",
        },
    )
    assert stream_resp.status_code == 200
    thread_id = stream_resp.headers["X-Thread-ID"]

    await db_session.refresh(attachment)
    assert attachment.thread_id == UUID(thread_id)
    assert attachment.status == RuntimeAttachmentStatus.processed
    assert "Quarterly results are strong." in str(attachment.extracted_text or "")

    run_row = await db_session.scalar(
        select(AgentRun).where(AgentRun.thread_id == UUID(thread_id)).limit(1)
    )
    assert run_row is not None
    turn = AgentThreadTurn(
        thread_id=UUID(thread_id),
        run_id=run_row.id,
        turn_index=0,
        user_input_text="Summarize the file",
        assistant_output_text="processed attachment",
        status=AgentThreadTurnStatus.completed,
    )
    db_session.add(turn)
    await db_session.flush()
    db_session.add(
        AgentThreadTurnAttachment(
            turn_id=turn.id,
            attachment_id=attachment.id,
        )
    )
    await db_session.commit()

    detail_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()
    assert len(payload["turns"]) == 1
    turn = payload["turns"][0]
    assert [item["id"] for item in turn["attachments"]] == [attachment_id]
    assert turn["attachments"][0]["filename"] == "brief.txt"

    delete_resp = await client.delete(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"deleted": True}
    assert not storage_path.exists()
