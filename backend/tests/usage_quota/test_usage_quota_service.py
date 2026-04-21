from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus
from app.db.postgres.models.identity import Organization, OrganizationStatus, User
from app.db.postgres.models.usage_quota import (
    UsageQuotaCounter,
    UsageQuotaPeriodType,
    UsageQuotaPolicy,
    UsageQuotaReservation,
    UsageQuotaReservationStatus,
    UsageQuotaScopeType,
)
from app.services.usage_quota_service import QuotaExceededError, UsageQuotaService


async def _seed_tenant_user_agent(db_session):
    tenant = Organization(
        name="Quota Organization",
        slug=f"quota-tenant-{uuid4().hex[:8]}",
        status=OrganizationStatus.active,
        settings={},
    )
    user = User(
        email=f"quota-user-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Quota User",
        role="user",
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    agent = Agent(
        organization_id=tenant.id,
        name="Quota Agent",
        slug=f"quota-agent-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
        status=AgentStatus.published,
    )
    db_session.add(agent)
    await db_session.flush()
    return tenant, user, agent


async def _add_policy(db_session, *, organization_id, user_id, scope_type, limit_tokens: int):
    policy = UsageQuotaPolicy(
        organization_id=organization_id,
        user_id=user_id,
        scope_type=scope_type,
        period_type=UsageQuotaPeriodType.monthly,
        limit_tokens=limit_tokens,
        timezone="UTC",
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()


@pytest.mark.asyncio
async def test_reserve_for_run_success_both_scopes(db_session, monkeypatch):
    monkeypatch.setenv("QUOTA_ENFORCEMENT_ENABLED", "1")
    monkeypatch.setenv("QUOTA_DEFAULT_MAX_OUTPUT_TOKENS", "120")
    tenant, user, _ = await _seed_tenant_user_agent(db_session)

    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=None,
        scope_type=UsageQuotaScopeType.tenant,
        limit_tokens=10_000,
    )
    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        scope_type=UsageQuotaScopeType.user,
        limit_tokens=10_000,
    )
    await db_session.commit()

    service = UsageQuotaService(db_session)
    run_id = uuid4()
    metadata = await service.reserve_for_run(
        run_id=run_id,
        organization_id=tenant.id,
        user_id=user.id,
        input_params={"input": "hello world " * 40, "context": {"max_output_cap": 64}},
    )
    await db_session.commit()

    assert metadata["reserved_tokens"] > 0
    assert metadata["max_output_cap"] == 64

    reservation = await db_session.scalar(
        select(UsageQuotaReservation).where(UsageQuotaReservation.run_id == run_id)
    )
    assert reservation is not None
    assert reservation.status == UsageQuotaReservationStatus.active
    assert reservation.reserved_tokens_tenant == metadata["reserved_tokens"]
    assert reservation.reserved_tokens_user == metadata["reserved_tokens"]

    counters = (
        (
            await db_session.execute(
                select(UsageQuotaCounter).where(
                    UsageQuotaCounter.scope_type == UsageQuotaScopeType.tenant,
                    UsageQuotaCounter.scope_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(counters) == 1
    assert counters[0].reserved_tokens == metadata["reserved_tokens"]


@pytest.mark.asyncio
async def test_reserve_for_run_rejects_user_scope_when_over_limit(db_session, monkeypatch):
    monkeypatch.setenv("QUOTA_ENFORCEMENT_ENABLED", "1")
    tenant, user, _ = await _seed_tenant_user_agent(db_session)

    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=None,
        scope_type=UsageQuotaScopeType.tenant,
        limit_tokens=10_000,
    )
    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        scope_type=UsageQuotaScopeType.user,
        limit_tokens=10,
    )
    await db_session.commit()

    service = UsageQuotaService(db_session)
    run_id = uuid4()
    with pytest.raises(QuotaExceededError) as exc_info:
        await service.reserve_for_run(
            run_id=run_id,
            organization_id=tenant.id,
            user_id=user.id,
            input_params={"input": "x" * 200, "context": {"max_output_cap": 40}},
        )
    await db_session.rollback()

    failures = exc_info.value.scope_failures
    assert any(f["scope_type"] == "user" for f in failures)

    persisted = await db_session.scalar(
        select(func.count(UsageQuotaReservation.id)).where(UsageQuotaReservation.run_id == run_id)
    )
    assert int(persisted or 0) == 0


@pytest.mark.asyncio
async def test_reserve_for_run_rejects_tenant_scope_when_over_limit(db_session, monkeypatch):
    monkeypatch.setenv("QUOTA_ENFORCEMENT_ENABLED", "1")
    tenant, user, _ = await _seed_tenant_user_agent(db_session)

    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=None,
        scope_type=UsageQuotaScopeType.tenant,
        limit_tokens=20,
    )
    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        scope_type=UsageQuotaScopeType.user,
        limit_tokens=10_000,
    )
    await db_session.commit()

    service = UsageQuotaService(db_session)
    with pytest.raises(QuotaExceededError) as exc_info:
        await service.reserve_for_run(
            run_id=uuid4(),
            organization_id=tenant.id,
            user_id=user.id,
            input_params={"input": "y" * 200, "context": {"max_output_cap": 40}},
        )
    await db_session.rollback()

    failures = exc_info.value.scope_failures
    assert any(f["scope_type"] == "tenant" for f in failures)


@pytest.mark.asyncio
async def test_settle_for_run_is_idempotent_and_moves_reserved_to_used(db_session, monkeypatch):
    monkeypatch.setenv("QUOTA_ENFORCEMENT_ENABLED", "1")
    tenant, user, _ = await _seed_tenant_user_agent(db_session)

    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=None,
        scope_type=UsageQuotaScopeType.tenant,
        limit_tokens=10_000,
    )
    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        scope_type=UsageQuotaScopeType.user,
        limit_tokens=10_000,
    )
    await db_session.commit()

    service = UsageQuotaService(db_session)
    run_id = uuid4()
    metadata = await service.reserve_for_run(
        run_id=run_id,
        organization_id=tenant.id,
        user_id=user.id,
        input_params={"input": "settle" * 30, "context": {"max_output_cap": 50}},
    )
    await db_session.commit()

    changed = await service.settle_for_run(run_id=run_id, actual_usage_tokens=77)
    await db_session.commit()
    assert changed is True

    reservation = await db_session.scalar(
        select(UsageQuotaReservation).where(UsageQuotaReservation.run_id == run_id)
    )
    assert reservation is not None
    assert reservation.status == UsageQuotaReservationStatus.settled

    tenant_counter = await db_session.scalar(
        select(UsageQuotaCounter).where(
            UsageQuotaCounter.scope_type == UsageQuotaScopeType.tenant,
            UsageQuotaCounter.scope_id == tenant.id,
            UsageQuotaCounter.period_start == reservation.period_start,
        )
    )
    assert tenant_counter is not None
    assert tenant_counter.reserved_tokens == 0
    assert tenant_counter.used_tokens == 77

    changed_again = await service.settle_for_run(run_id=run_id, actual_usage_tokens=999)
    await db_session.commit()
    assert changed_again is False

    tenant_counter_after = await db_session.scalar(
        select(UsageQuotaCounter).where(
            UsageQuotaCounter.scope_type == UsageQuotaScopeType.tenant,
            UsageQuotaCounter.scope_id == tenant.id,
            UsageQuotaCounter.period_start == reservation.period_start,
        )
    )
    assert tenant_counter_after is not None
    assert tenant_counter_after.used_tokens == 77
    assert tenant_counter_after.reserved_tokens == 0
    assert metadata["reserved_tokens"] > 0


@pytest.mark.asyncio
async def test_release_and_expire_clear_reserved_tokens(db_session, monkeypatch):
    monkeypatch.setenv("QUOTA_ENFORCEMENT_ENABLED", "1")
    tenant, user, _ = await _seed_tenant_user_agent(db_session)

    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=None,
        scope_type=UsageQuotaScopeType.tenant,
        limit_tokens=10_000,
    )
    await _add_policy(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        scope_type=UsageQuotaScopeType.user,
        limit_tokens=10_000,
    )
    await db_session.commit()

    service = UsageQuotaService(db_session)

    run_release = uuid4()
    await service.reserve_for_run(
        run_id=run_release,
        organization_id=tenant.id,
        user_id=user.id,
        input_params={"input": "release" * 20, "context": {"max_output_cap": 20}},
    )
    await db_session.commit()

    released = await service.release_for_run(run_id=run_release)
    await db_session.commit()
    assert released is True

    released_row = await db_session.scalar(
        select(UsageQuotaReservation).where(UsageQuotaReservation.run_id == run_release)
    )
    assert released_row is not None
    assert released_row.status == UsageQuotaReservationStatus.released

    run_expire = uuid4()
    await service.reserve_for_run(
        run_id=run_expire,
        organization_id=tenant.id,
        user_id=user.id,
        input_params={"input": "expire" * 20, "context": {"max_output_cap": 20}},
    )
    await db_session.commit()

    exp_row = await db_session.scalar(
        select(UsageQuotaReservation).where(UsageQuotaReservation.run_id == run_expire)
    )
    assert exp_row is not None
    exp_row.created_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    await db_session.commit()

    expired_count = await service.expire_stale_reservations(older_than_minutes=30)
    await db_session.commit()
    assert expired_count >= 1

    exp_row = await db_session.scalar(
        select(UsageQuotaReservation).where(UsageQuotaReservation.run_id == run_expire)
    )
    assert exp_row is not None
    assert exp_row.status == UsageQuotaReservationStatus.expired


@pytest.mark.asyncio
async def test_reconcile_counter_from_ledger_updates_used_tokens(db_session):
    tenant, user, agent = await _seed_tenant_user_agent(db_session)
    service = UsageQuotaService(db_session)
    period_start, period_end = service._month_bounds_utc(tz_name="UTC")

    run_one = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        status="completed",
        usage_tokens=55,
        created_at=datetime.now(timezone.utc),
    )
    run_two = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        status="completed",
        usage_tokens=45,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([run_one, run_two])
    await db_session.commit()

    used_tokens = await service.reconcile_counter_from_ledger(
        scope_type=UsageQuotaScopeType.user,
        scope_id=user.id,
        period_start=period_start,
        period_end=period_end,
    )
    await db_session.commit()

    assert used_tokens == 100
    counter = await db_session.scalar(
        select(UsageQuotaCounter).where(
            UsageQuotaCounter.scope_type == UsageQuotaScopeType.user,
            UsageQuotaCounter.scope_id == user.id,
            UsageQuotaCounter.period_start == period_start,
        )
    )
    assert counter is not None
    assert counter.used_tokens == 100
