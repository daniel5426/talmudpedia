from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadTurn
from app.db.postgres.models.agents import Agent, AgentRun
from app.db.postgres.models.identity import Tenant, User
from app.services.thread_service import ThreadService


async def _seed_thread_context(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Thread Tenant {suffix}", slug=f"thread-tenant-{suffix}")
    user = User(email=f"thread-user-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    agent = Agent(
        tenant_id=tenant.id,
        name="Thread Test Agent",
        slug=f"thread-test-agent-{suffix}",
        description="Thread test agent",
    )
    db_session.add(agent)
    await db_session.flush()
    return tenant, user, agent


@pytest.mark.asyncio
async def test_start_turn_increments_after_existing_zero_index(db_session):
    tenant, user, agent = await _seed_thread_context(db_session)
    thread = AgentThread(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        surface=AgentThreadSurface.internal,
        title="Thread ordering",
    )
    db_session.add(thread)
    await db_session.flush()

    first_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=thread.id,
        input_params={"input": "first"},
    )
    second_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=thread.id,
        input_params={"input": "second"},
    )
    db_session.add_all([first_run, second_run])
    await db_session.flush()

    db_session.add(
        AgentThreadTurn(
            thread_id=thread.id,
            run_id=first_run.id,
            turn_index=0,
            user_input_text="first",
        )
    )
    await db_session.commit()

    service = ThreadService(db_session)
    turn = await service.start_turn(
        thread_id=thread.id,
        run_id=second_run.id,
        user_input_text="second",
    )

    assert turn.turn_index == 1


@pytest.mark.asyncio
async def test_repair_thread_turn_indices_resequences_duplicate_zero_turns(db_session):
    tenant, user, agent = await _seed_thread_context(db_session)
    thread = AgentThread(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        surface=AgentThreadSurface.internal,
        title="Repair ordering",
    )
    db_session.add(thread)
    await db_session.flush()

    older_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=thread.id,
        input_params={"input": "older"},
    )
    newer_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=thread.id,
        input_params={"input": "newer"},
    )
    db_session.add_all([older_run, newer_run])
    await db_session.flush()

    older_created_at = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    newer_created_at = older_created_at + timedelta(minutes=1)
    db_session.add_all(
        [
            AgentThreadTurn(
                thread_id=thread.id,
                run_id=older_run.id,
                turn_index=0,
                user_input_text="older",
                created_at=older_created_at,
            ),
            AgentThreadTurn(
                thread_id=thread.id,
                run_id=newer_run.id,
                turn_index=0,
                user_input_text="newer",
                created_at=newer_created_at,
            ),
        ]
    )
    await db_session.commit()

    service = ThreadService(db_session)
    changed = await service.repair_thread_turn_indices(thread_id=thread.id)
    await db_session.commit()

    assert changed is True

    repaired = await service.get_thread_with_turns(
        tenant_id=tenant.id,
        thread_id=thread.id,
        user_id=user.id,
    )

    assert repaired is not None
    assert [turn.user_input_text for turn in repaired.turns] == ["older", "newer"]
    assert [turn.turn_index for turn in repaired.turns] == [0, 1]
