from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, User
from app.db.postgres.models.published_apps import (
    PublishedAppCodingChatMessage,
    PublishedAppCodingChatMessageRole,
    PublishedAppCodingChatSession,
)
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.security_bootstrap_service import SecurityBootstrapService
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent Chat History App",
            "agent_id": agent_id,
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]
    return app_id, draft_revision_id


async def _insert_run(
    db_session,
    *,
    organization_id,
    agent_id,
    user_id,
    app_id: str,
    base_revision_id: str,
    output_result: dict | None = None,
) -> AgentRun:
    run = AgentRun(
        organization_id=organization_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=RunStatus.completed,
        input_params={"input": "history"},
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
        output_result=output_result,
        execution_engine="opencode",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_chat_history_list_scopes_to_current_user(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    other_user = User(email=f"secondary-{owner.id.hex[:8]}@example.com", role="user")
    db_session.add(other_user)
    await db_session.flush()
    db_session.add(
        OrgMembership(
            organization_id=tenant.id,
            user_id=other_user.id,
            org_unit_id=org_unit.id,
            status=MembershipStatus.active,
        )
    )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=tenant.id,
        user_id=other_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    owner_run = await _insert_run(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
    )
    other_run = await _insert_run(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=other_user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
    )

    owner_session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=owner.id,
        title="Owner thread",
        last_message_at=datetime.now(timezone.utc),
    )
    other_session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=other_user.id,
        title="Other thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add_all([owner_session, other_session])
    await db_session.commit()
    await db_session.refresh(owner_session)
    await db_session.refresh(other_session)

    db_session.add_all(
        [
            PublishedAppCodingChatMessage(
                session_id=owner_session.id,
                run_id=owner_run.id,
                role=PublishedAppCodingChatMessageRole.user,
                content="Owner message",
            ),
            PublishedAppCodingChatMessage(
                session_id=other_session.id,
                run_id=other_run.id,
                role=PublishedAppCodingChatMessageRole.user,
                content="Other user message",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions?limit=50", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [str(owner_session.id)]


@pytest.mark.asyncio
async def test_chat_history_detail_returns_ordered_turns(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    first_run = await _insert_run(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
    )
    second_run = await _insert_run(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        output_result={
            "tool_events": [
                {
                    "event": "tool.started",
                    "stage": "tool",
                    "payload": {
                        "tool": "read_file",
                        "span_id": "call-1",
                        "input": {"path": "src/main.tsx"},
                    },
                    "diagnostics": [],
                    "ts": "2026-02-25T10:00:00Z",
                },
                {
                    "event": "tool.completed",
                    "stage": "tool",
                    "payload": {
                        "tool": "read_file",
                        "span_id": "call-1",
                        "output": {"path": "src/main.tsx"},
                    },
                    "diagnostics": [],
                    "ts": "2026-02-25T10:00:01Z",
                },
            ]
        },
    )

    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=owner.id,
        title="Ordered thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    t0 = datetime.now(timezone.utc)
    db_session.add_all(
        [
            PublishedAppCodingChatMessage(
                session_id=session.id,
                run_id=first_run.id,
                role=PublishedAppCodingChatMessageRole.user,
                content="First prompt",
                created_at=t0,
            ),
            PublishedAppCodingChatMessage(
                session_id=session.id,
                run_id=second_run.id,
                role=PublishedAppCodingChatMessageRole.assistant,
                content="Second response",
                created_at=t0 + timedelta(seconds=3),
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}?limit=50",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == str(session.id)
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]
    assert [item["content"] for item in payload["messages"]] == ["First prompt", "Second response"]
    assert [item["event"] for item in payload["run_events"]] == ["tool.started", "tool.completed"]
    assert [item["run_id"] for item in payload["run_events"]] == [str(second_run.id), str(second_run.id)]
    assert payload["run_events"][0]["payload"]["tool"] == "read_file"
    assert payload["paging"] == {"has_more": False, "next_before_message_id": None}


@pytest.mark.asyncio
async def test_chat_history_detail_blocks_cross_user_session_access(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    other_user = User(email=f"blocked-{owner.id.hex[:8]}@example.com", role="user")
    db_session.add(other_user)
    await db_session.flush()
    db_session.add(
        OrgMembership(
            organization_id=tenant.id,
            user_id=other_user.id,
            org_unit_id=org_unit.id,
            status=MembershipStatus.active,
        )
    )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=tenant.id,
        user_id=other_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    foreign_session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=other_user.id,
        title="Hidden thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign_session)
    await db_session.commit()
    await db_session.refresh(foreign_session)

    response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{foreign_session.id}?limit=20",
        headers=headers,
    )
    assert response.status_code == 404
    assert "not found" in str(response.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_chat_history_detail_paginates_from_latest_with_cursor(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=owner.id,
        title="Paged thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    base_time = datetime.now(timezone.utc)
    message_ids: list[str] = []
    for idx in range(12):
        output_result = None
        if idx == 0:
            output_result = {
                "tool_events": [
                    {
                        "event": "tool.started",
                        "stage": "tool",
                        "payload": {"tool": "read_file", "span_id": "call-old", "input": {"path": "src/old.tsx"}},
                        "diagnostics": [],
                    },
                    {
                        "event": "tool.completed",
                        "stage": "tool",
                        "payload": {"tool": "read_file", "span_id": "call-old", "output": {"path": "src/old.tsx"}},
                        "diagnostics": [],
                    },
                ]
            }
        run = await _insert_run(
            db_session,
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=owner.id,
            app_id=app_id,
            base_revision_id=draft_revision_id,
            output_result=output_result,
        )
        message = PublishedAppCodingChatMessage(
            session_id=session.id,
            run_id=run.id,
            role=PublishedAppCodingChatMessageRole.assistant,
            content=f"message-{idx + 1}",
            created_at=base_time + timedelta(seconds=idx),
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)
        message_ids.append(str(message.id))

    latest_page = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}",
        headers=headers,
    )
    assert latest_page.status_code == 200
    latest_payload = latest_page.json()
    assert len(latest_payload["messages"]) == 10
    assert [item["content"] for item in latest_payload["messages"]] == [f"message-{idx}" for idx in range(3, 13)]
    assert latest_payload["paging"]["has_more"] is True
    assert latest_payload["paging"]["next_before_message_id"] == latest_payload["messages"][0]["id"]
    # Oldest run events should not appear in the latest page.
    assert latest_payload["run_events"] == []

    older_page = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}"
        f"?before_message_id={latest_payload['paging']['next_before_message_id']}",
        headers=headers,
    )
    assert older_page.status_code == 200
    older_payload = older_page.json()
    assert [item["content"] for item in older_payload["messages"]] == ["message-1", "message-2"]
    assert older_payload["paging"] == {"has_more": False, "next_before_message_id": None}
    assert [item["event"] for item in older_payload["run_events"]] == ["tool.started", "tool.completed"]


@pytest.mark.asyncio
async def test_chat_history_detail_rejects_invalid_or_foreign_cursor(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=owner.id,
        title="Cursor thread",
        last_message_at=datetime.now(timezone.utc),
    )
    foreign_session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=owner.id,
        title="Other cursor thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add_all([session, foreign_session])
    await db_session.commit()
    await db_session.refresh(session)
    await db_session.refresh(foreign_session)

    run = await _insert_run(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
    )
    foreign_message = PublishedAppCodingChatMessage(
        session_id=foreign_session.id,
        run_id=run.id,
        role=PublishedAppCodingChatMessageRole.user,
        content="foreign cursor message",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign_message)
    await db_session.commit()
    await db_session.refresh(foreign_message)

    missing_cursor_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}?before_message_id={uuid4()}",
        headers=headers,
    )
    assert missing_cursor_response.status_code == 404

    foreign_cursor_response = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}?before_message_id={foreign_message.id}",
        headers=headers,
    )
    assert foreign_cursor_response.status_code == 404
    assert "cursor message" in str(foreign_cursor_response.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_chat_history_detail_pagination_tie_order_is_stable(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=owner.id,
        title="Tie-order thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    tied_time = datetime.now(timezone.utc)
    all_ids: list[str] = []
    for idx in range(4):
        run = await _insert_run(
            db_session,
            organization_id=tenant.id,
            agent_id=agent.id,
            user_id=owner.id,
            app_id=app_id,
            base_revision_id=draft_revision_id,
        )
        message = PublishedAppCodingChatMessage(
            session_id=session.id,
            run_id=run.id,
            role=PublishedAppCodingChatMessageRole.user,
            content=f"tie-{idx + 1}",
            created_at=tied_time,
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)
        all_ids.append(str(message.id))

    page1_resp = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}?limit=2",
        headers=headers,
    )
    assert page1_resp.status_code == 200
    page1 = page1_resp.json()
    cursor_1 = page1["paging"]["next_before_message_id"]
    assert cursor_1

    page2_resp = await client.get(
        f"/admin/apps/{app_id}/coding-agent/v2/chat-sessions/{session.id}?limit=2&before_message_id={cursor_1}",
        headers=headers,
    )
    assert page2_resp.status_code == 200
    page2 = page2_resp.json()
    assert page2["paging"] == {"has_more": False, "next_before_message_id": None}

    fetched_ids = [item["id"] for item in page1["messages"]] + [item["id"] for item in page2["messages"]]
    assert len(fetched_ids) == 4
    assert len(set(fetched_ids)) == 4
    assert set(fetched_ids) == set(all_ids)
