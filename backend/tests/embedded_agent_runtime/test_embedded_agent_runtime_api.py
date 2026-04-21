from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn, AgentThreadTurnStatus
from app.db.postgres.models.runtime_attachments import (
    AgentThreadTurnAttachment,
    RuntimeAttachment,
    RuntimeAttachmentStatus,
)
from app.services.organization_api_key_service import OrganizationAPIKeyService
from tests.published_apps._helpers import install_stub_agent_worker, seed_admin_tenant_and_agent


def _embed_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_embed_key(db_session, *, organization_id, created_by, scopes=None):
    api_key, token = await OrganizationAPIKeyService(db_session).create_api_key(
        organization_id=organization_id,
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
    api_key, token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)
    install_stub_agent_worker(monkeypatch, content="hello from embed")

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
    _, token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)
    install_stub_agent_worker(monkeypatch, content="hello from embed")

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
            metadata_={"final_output": {"answer": "machine-facing embed output"}},
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
    assert turn["assistant_output_text"] == "hello from embed"
    assert turn["final_output"] == {"answer": "machine-facing embed output"}
    assert turn["response_blocks"] == []
    assert [item["event"] for item in turn["run_events"]] == [
        "tool.started",
        "reasoning.update",
        "tool.completed",
        "reasoning.update",
    ]
    assert [item["run_id"] for item in turn["run_events"]] == [str(run_id)] * 4

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
async def test_embedded_agent_thread_detail_returns_subthread_tree_when_requested(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    _, token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)
    install_stub_agent_worker(monkeypatch, content="hello from embed")

    stream_resp = await client.post(
        f"/public/embed/agents/{agent.id}/chat/stream",
        headers=_embed_headers(token),
        json={"input": "hi", "external_user_id": "customer-user-1"},
    )
    thread_id = UUID(str(stream_resp.headers["X-Thread-ID"]))
    root_thread = await db_session.get(AgentThread, thread_id)
    assert root_thread is not None
    root_run = await db_session.scalar(select(AgentRun).where(AgentRun.thread_id == root_thread.id).limit(1))
    assert root_run is not None
    root_turn = await db_session.scalar(select(AgentThreadTurn).where(AgentThreadTurn.run_id == root_run.id).limit(1))
    if root_turn is None:
        root_turn = AgentThreadTurn(
            thread_id=root_thread.id,
            run_id=root_run.id,
            turn_index=0,
            user_input_text="hi",
            assistant_output_text="hello from embed",
            status=AgentThreadTurnStatus.completed,
        )
        db_session.add(root_turn)
        await db_session.flush()

    child_thread = AgentThread(
        organization_id=tenant.id,
        agent_id=agent.id,
        external_user_id="customer-user-1",
        surface=root_thread.surface,
        title="Embedded child thread",
        root_thread_id=root_thread.id,
        parent_thread_id=root_thread.id,
        parent_thread_turn_id=root_turn.id,
        spawned_by_run_id=root_run.id,
        lineage_depth=1,
    )
    db_session.add(child_thread)
    await db_session.flush()
    child_run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        thread_id=child_thread.id,
        input_params={"input": "child hi"},
        parent_run_id=root_run.id,
        root_run_id=root_run.id,
        depth=1,
    )
    db_session.add(child_run)
    await db_session.flush()
    db_session.add(
        AgentThreadTurn(
            thread_id=child_thread.id,
            run_id=child_run.id,
            turn_index=0,
            user_input_text="child hi",
            assistant_output_text="embedded child reply",
            status=AgentThreadTurnStatus.completed,
        )
    )
    await db_session.commit()

    detail_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{thread_id}",
        headers=_embed_headers(token),
        params={"external_user_id": "customer-user-1", "include_subthreads": "true"},
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()
    assert payload["lineage"]["root_thread_id"] == str(root_thread.id)
    assert payload["subthread_tree"]["thread"]["id"] == str(root_thread.id)
    assert payload["subthread_tree"]["children"][0]["thread"]["id"] == str(child_thread.id)
    assert payload["subthread_tree"]["children"][0]["lineage"]["parent_thread_id"] == str(root_thread.id)


@pytest.mark.asyncio
async def test_embedded_agent_routes_reject_wrong_scope_revoked_keys_and_cross_user_access(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    _, token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)
    _, wrong_scope_token = await _create_embed_key(
        db_session,
        organization_id=tenant.id,
        created_by=owner.id,
        scopes=["agents.read"],
    )
    revoked_key, revoked_token = await _create_embed_key(
        db_session,
        organization_id=tenant.id,
        created_by=owner.id,
        scopes=["agents.embed"],
    )
    await OrganizationAPIKeyService(db_session).revoke_api_key(organization_id=tenant.id, key_id=revoked_key.id)
    await db_session.commit()

    install_stub_agent_worker(monkeypatch, content="ok")

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
    _, token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)

    draft_agent = Agent(
        organization_id=tenant.id,
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
    _, token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)

    install_stub_agent_worker(monkeypatch, content="processed attachment")

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


def test_extract_turn_metadata_returns_none_without_ui_metadata():
    assert AgentExecutorService._extract_turn_metadata({"messages": []}) is None
