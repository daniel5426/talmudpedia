from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.resource_policies import (
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaCounter,
    ResourcePolicyQuotaReservation,
)
from app.services.resource_policy_quota_service import ResourcePolicyQuotaExceeded, ResourcePolicyQuotaService
from app.services.resource_policy_service import ResourcePolicyPrincipalRef, ResourcePolicyQuotaRule


@pytest.mark.asyncio
async def test_reservation_is_noop_without_snapshot_principal_or_model(
    db_session,
    tenant_context,
    resource_factory,
    make_snapshot,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    model = await resource_factory.model(organization_id=tenant.id, name="Noop Model")
    snapshot_without_principal = make_snapshot()
    snapshot_without_quota = make_snapshot(
        principal=ResourcePolicyPrincipalRef(
            principal_type=ResourcePolicyPrincipalType.TENANT_USER,
            organization_id=tenant.id,
            user_id=user.id,
        )
    )
    service = ResourcePolicyQuotaService(db_session)

    result_none = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=None,
        model_id=model.id,
        input_params={"input": "hello"},
    )
    result_no_principal = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot_without_principal,
        model_id=model.id,
        input_params={"input": "hello"},
    )
    result_no_quota = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot_without_quota,
        model_id=model.id,
        input_params={"input": "hello"},
    )

    assert result_none.reserved_tokens == 0
    assert result_no_principal.reserved_tokens == 0
    assert result_no_quota.reserved_tokens == 0


@pytest.mark.asyncio
async def test_reservation_accumulates_by_principal_model_and_month(
    db_session,
    tenant_context,
    resource_factory,
    make_snapshot,
    monkeypatch,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    model = await resource_factory.model(organization_id=tenant.id, name="Quota Model")
    second_model = await resource_factory.model(organization_id=tenant.id, name="Quota Model 2")
    principal = ResourcePolicyPrincipalRef(
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        organization_id=tenant.id,
        user_id=user.id,
    )
    snapshot = make_snapshot(
        principal=principal,
        model_quotas={
            str(model.id): ResourcePolicyQuotaRule(model_id=str(model.id), limit_tokens=200),
            str(second_model.id): ResourcePolicyQuotaRule(model_id=str(second_model.id), limit_tokens=300),
        },
    )
    period_start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 4, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        ResourcePolicyQuotaService,
        "_month_bounds_utc",
        staticmethod(lambda now_utc=None: (period_start, period_end)),
    )
    monkeypatch.setattr(
        "app.services.resource_policy_quota_service.UsageQuotaService.estimate_prompt_tokens",
        staticmethod(lambda _input_params: 10),
    )

    service = ResourcePolicyQuotaService(db_session)
    first = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot,
        model_id=model.id,
        input_params={"context": {"quota_max_output_tokens": 5}},
    )
    second = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot,
        model_id=model.id,
        input_params={"context": {"quota_max_output_tokens": 5}},
    )
    third = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot,
        model_id=second_model.id,
        input_params={"context": {"quota_max_output_tokens": 10}},
    )
    await db_session.commit()

    counters = list(
        (
            await db_session.execute(
                select(ResourcePolicyQuotaCounter).order_by(ResourcePolicyQuotaCounter.model_id.asc())
            )
        ).scalars()
    )
    reservations = list((await db_session.execute(select(ResourcePolicyQuotaReservation))).scalars())

    assert first.reserved_tokens == 15
    assert second.reserved_tokens == 15
    assert third.reserved_tokens == 20
    assert len(counters) == 2
    assert sum(counter.reserved_tokens for counter in counters if counter.model_id == model.id) == 30
    assert sum(counter.reserved_tokens for counter in counters if counter.model_id == second_model.id) == 20
    assert len(reservations) == 3


@pytest.mark.asyncio
async def test_reservation_rejects_projected_overage_and_month_rollover_starts_new_counter(
    db_session,
    tenant_context,
    resource_factory,
    make_snapshot,
    monkeypatch,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    model = await resource_factory.model(organization_id=tenant.id, name="Overage Model")
    principal = ResourcePolicyPrincipalRef(
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        organization_id=tenant.id,
        user_id=user.id,
    )
    snapshot = make_snapshot(
        principal=principal,
        model_quotas={str(model.id): ResourcePolicyQuotaRule(model_id=str(model.id), limit_tokens=20)},
    )
    march = datetime(2026, 3, 1, tzinfo=timezone.utc)
    april = datetime(2026, 4, 1, tzinfo=timezone.utc)
    may = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bounds = iter([(march, april), (march, april), (april, may)])
    monkeypatch.setattr(
        ResourcePolicyQuotaService,
        "_month_bounds_utc",
        staticmethod(lambda now_utc=None: next(bounds)),
    )
    monkeypatch.setattr(
        "app.services.resource_policy_quota_service.UsageQuotaService.estimate_prompt_tokens",
        staticmethod(lambda _input_params: 10),
    )
    service = ResourcePolicyQuotaService(db_session)

    await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot,
        model_id=model.id,
        input_params={"context": {"quota_max_output_tokens": 5}},
    )
    await db_session.commit()
    with pytest.raises(ResourcePolicyQuotaExceeded):
        await service.reserve_for_run(
            run_id=uuid4(),
            organization_id=tenant.id,
            snapshot=snapshot,
            model_id=model.id,
            input_params={"context": {"quota_max_output_tokens": 6}},
        )

    april_reservation = await service.reserve_for_run(
        run_id=uuid4(),
        organization_id=tenant.id,
        snapshot=snapshot,
        model_id=model.id,
        input_params={"context": {"quota_max_output_tokens": 5}},
    )
    await db_session.commit()

    counters = list(
        (
            await db_session.execute(
                select(ResourcePolicyQuotaCounter).where(ResourcePolicyQuotaCounter.model_id == model.id)
            )
        ).scalars()
    )
    normalized_periods = {counter.period_start.replace(tzinfo=timezone.utc) for counter in counters}
    assert len(normalized_periods) == 2
    assert april_reservation.reserved_tokens == 15
    assert normalized_periods == {march, april}


@pytest.mark.asyncio
async def test_settlement_uses_total_tokens_is_idempotent_and_noops_without_model_or_reservation(
    db_session,
    tenant_context,
    resource_factory,
    make_snapshot,
    monkeypatch,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    agent = await resource_factory.agent(organization_id=tenant.id, created_by=user.id, name="Quota Agent")
    model = await resource_factory.model(organization_id=tenant.id, name="Settle Model")
    principal = ResourcePolicyPrincipalRef(
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        organization_id=tenant.id,
        user_id=user.id,
    )
    snapshot = make_snapshot(
        principal=principal,
        model_quotas={str(model.id): ResourcePolicyQuotaRule(model_id=str(model.id), limit_tokens=200)},
    )
    period_start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 4, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        ResourcePolicyQuotaService,
        "_month_bounds_utc",
        staticmethod(lambda now_utc=None: (period_start, period_end)),
    )
    monkeypatch.setattr(
        "app.services.resource_policy_quota_service.UsageQuotaService.estimate_prompt_tokens",
        staticmethod(lambda _input_params: 10),
    )

    service = ResourcePolicyQuotaService(db_session)
    run = await resource_factory.run(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        resolved_model_id=model.id,
        total_tokens=12,
        usage_tokens=999,
    )
    await service.reserve_for_run(
        run_id=run.id,
        organization_id=tenant.id,
        snapshot=snapshot,
        model_id=model.id,
        input_params={"context": {"quota_max_output_tokens": 5}},
    )
    await db_session.commit()
    await service.settle_for_run(run=run)
    await service.settle_for_run(run=run)

    counters = list(
        (
            await db_session.execute(
                select(ResourcePolicyQuotaCounter).where(ResourcePolicyQuotaCounter.model_id == model.id)
            )
        ).scalars()
    )
    reservation = await db_session.scalar(
        select(ResourcePolicyQuotaReservation).where(ResourcePolicyQuotaReservation.run_id == run.id).limit(1)
    )
    assert counters
    assert reservation is not None
    assert max(counter.used_tokens for counter in counters) == 12
    assert min(counter.reserved_tokens for counter in counters) == 0
    assert reservation.settled_at is not None

    no_model_run = await resource_factory.run(organization_id=tenant.id, agent_id=agent.id, user_id=user.id)
    no_reservation_run = await resource_factory.run(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        resolved_model_id=model.id,
    )
    await service.settle_for_run(run=no_model_run)
    await service.settle_for_run(run=no_reservation_run)
