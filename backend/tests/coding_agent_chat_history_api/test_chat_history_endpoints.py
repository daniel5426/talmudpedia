from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, User
from app.db.postgres.models.published_apps import (
    PublishedAppCodingChatMessage,
    PublishedAppCodingChatMessageRole,
    PublishedAppCodingChatSession,
)
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent Chat History App",
            "agent_id": agent_id,
            "template_key": "chat-classic",
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


async def _insert_run(db_session, *, tenant_id, agent_id, user_id, app_id: str, base_revision_id: str) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=RunStatus.completed,
        input_params={"input": "history"},
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
        execution_engine="native",
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
            tenant_id=tenant.id,
            user_id=other_user.id,
            org_unit_id=org_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    await db_session.commit()

    owner_run = await _insert_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
    )
    other_run = await _insert_run(
        db_session,
        tenant_id=tenant.id,
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

    response = await client.get(f"/admin/apps/{app_id}/coding-agent/chat-sessions?limit=50", headers=headers)
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
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
    )
    second_run = await _insert_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
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
        f"/admin/apps/{app_id}/coding-agent/chat-sessions/{session.id}?limit=50",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == str(session.id)
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]
    assert [item["content"] for item in payload["messages"]] == ["First prompt", "Second response"]


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
            tenant_id=tenant.id,
            user_id=other_user.id,
            org_unit_id=org_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
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
        f"/admin/apps/{app_id}/coding-agent/chat-sessions/{foreign_session.id}?limit=20",
        headers=headers,
    )
    assert response.status_code == 404
    assert "not found" in str(response.json()["detail"]).lower()
