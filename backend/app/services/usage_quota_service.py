from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.usage_quota import (
    UsageQuotaCounter,
    UsageQuotaPeriodType,
    UsageQuotaPolicy,
    UsageQuotaReservation,
    UsageQuotaReservationStatus,
    UsageQuotaScopeType,
)
from app.services.model_accounting import usage_total_expr


class QuotaExceededError(Exception):
    def __init__(self, *, scope_failures: list[dict[str, Any]], period_start: datetime, period_end: datetime):
        super().__init__("Quota exceeded")
        self.scope_failures = scope_failures
        self.period_start = period_start
        self.period_end = period_end

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": "QUOTA_EXCEEDED",
            "scope_failures": self.scope_failures,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
        }


@dataclass
class _ScopePolicy:
    scope_type: UsageQuotaScopeType
    scope_id: UUID
    limit_tokens: int
    timezone: str


class UsageQuotaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def quota_enforcement_enabled() -> bool:
        raw = (os.getenv("QUOTA_ENFORCEMENT_ENABLED") or "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _resolve_cap(input_params: dict[str, Any]) -> int:
        default_cap = int((os.getenv("QUOTA_DEFAULT_MAX_OUTPUT_TOKENS") or "2000").strip() or 2000)
        context = input_params.get("context") if isinstance(input_params, dict) else None
        if not isinstance(context, dict):
            return max(1, default_cap)
        for key in ("max_output_tokens", "max_output_cap", "quota_max_output_tokens"):
            raw = context.get(key)
            try:
                parsed = int(raw)
                if parsed > 0:
                    return parsed
            except Exception:
                continue
        return max(1, default_cap)

    @staticmethod
    def estimate_prompt_tokens(input_params: dict[str, Any]) -> int:
        if not isinstance(input_params, dict):
            return 0
        text_parts: list[str] = []
        raw_input = input_params.get("input")
        if isinstance(raw_input, str) and raw_input.strip():
            text_parts.append(raw_input)
        messages = input_params.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    text_parts.append(content)
        # Cheap deterministic estimate. Real provider usage settles at finalize.
        total_chars = sum(len(part) for part in text_parts)
        return max(0, total_chars // 4)

    @staticmethod
    def _month_bounds_utc(*, tz_name: str, now_utc: Optional[datetime] = None) -> tuple[datetime, datetime]:
        now_utc = now_utc or datetime.now(timezone.utc)
        try:
            tz = ZoneInfo(str(tz_name or "UTC"))
        except Exception:
            tz = ZoneInfo("UTC")
        localized = now_utc.astimezone(tz)
        start_local = localized.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            next_month = start_local.replace(year=start_local.year + 1, month=1)
        else:
            next_month = start_local.replace(month=start_local.month + 1)
        return start_local.astimezone(timezone.utc), next_month.astimezone(timezone.utc)

    async def _resolve_policy(self, *, tenant_id: UUID, user_id: Optional[UUID], scope: UsageQuotaScopeType) -> Optional[_ScopePolicy]:
        if scope == UsageQuotaScopeType.tenant:
            result = await self.db.execute(
                select(UsageQuotaPolicy)
                .where(
                    and_(
                        UsageQuotaPolicy.tenant_id == tenant_id,
                        UsageQuotaPolicy.user_id.is_(None),
                        UsageQuotaPolicy.scope_type == UsageQuotaScopeType.tenant,
                        UsageQuotaPolicy.period_type == UsageQuotaPeriodType.monthly,
                        UsageQuotaPolicy.is_active.is_(True),
                    )
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _ScopePolicy(
                scope_type=UsageQuotaScopeType.tenant,
                scope_id=tenant_id,
                limit_tokens=max(0, int(row.limit_tokens or 0)),
                timezone=str(row.timezone or "UTC"),
            )

        if user_id is None:
            return None
        result = await self.db.execute(
            select(UsageQuotaPolicy)
            .where(
                and_(
                    UsageQuotaPolicy.tenant_id == tenant_id,
                    UsageQuotaPolicy.user_id == user_id,
                    UsageQuotaPolicy.scope_type == UsageQuotaScopeType.user,
                    UsageQuotaPolicy.period_type == UsageQuotaPeriodType.monthly,
                    UsageQuotaPolicy.is_active.is_(True),
                )
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _ScopePolicy(
            scope_type=UsageQuotaScopeType.user,
            scope_id=user_id,
            limit_tokens=max(0, int(row.limit_tokens or 0)),
            timezone=str(row.timezone or "UTC"),
        )

    async def _lock_counter(
        self,
        *,
        scope_type: UsageQuotaScopeType,
        scope_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> UsageQuotaCounter:
        result = await self.db.execute(
            select(UsageQuotaCounter)
            .where(
                and_(
                    UsageQuotaCounter.scope_type == scope_type,
                    UsageQuotaCounter.scope_id == scope_id,
                    UsageQuotaCounter.period_start == period_start,
                )
            )
            .with_for_update()
            .limit(1)
        )
        counter = result.scalar_one_or_none()
        if counter is not None:
            return counter

        counter = UsageQuotaCounter(
            scope_type=scope_type,
            scope_id=scope_id,
            period_start=period_start,
            period_end=period_end,
            used_tokens=0,
            reserved_tokens=0,
        )
        self.db.add(counter)
        await self.db.flush()
        return counter

    async def reserve_for_run(
        self,
        *,
        run_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID],
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.quota_enforcement_enabled():
            return {
                "reserved_tokens": 0,
                "max_output_cap": self._resolve_cap(input_params),
                "period_start": None,
                "period_end": None,
            }

        tenant_policy = await self._resolve_policy(tenant_id=tenant_id, user_id=user_id, scope=UsageQuotaScopeType.tenant)
        user_policy = await self._resolve_policy(tenant_id=tenant_id, user_id=user_id, scope=UsageQuotaScopeType.user)

        if tenant_policy is None and user_policy is None:
            return {
                "reserved_tokens": 0,
                "max_output_cap": self._resolve_cap(input_params),
                "period_start": None,
                "period_end": None,
            }

        active_policies = [p for p in (tenant_policy, user_policy) if p is not None]
        tz_name = active_policies[0].timezone if active_policies else "UTC"
        period_start, period_end = self._month_bounds_utc(tz_name=tz_name)

        prompt_tokens = self.estimate_prompt_tokens(input_params)
        max_output_cap = self._resolve_cap(input_params)
        requested_reserve = max(1, int(prompt_tokens + max_output_cap))

        failures: list[dict[str, Any]] = []
        tenant_counter: Optional[UsageQuotaCounter] = None
        user_counter: Optional[UsageQuotaCounter] = None

        if tenant_policy is not None:
            tenant_counter = await self._lock_counter(
                scope_type=UsageQuotaScopeType.tenant,
                scope_id=tenant_policy.scope_id,
                period_start=period_start,
                period_end=period_end,
            )
            projected = int(tenant_counter.used_tokens or 0) + int(tenant_counter.reserved_tokens or 0) + requested_reserve
            if projected > tenant_policy.limit_tokens:
                failures.append(
                    {
                        "scope_type": "tenant",
                        "scope_id": str(tenant_policy.scope_id),
                        "limit_tokens": int(tenant_policy.limit_tokens),
                        "used_tokens": int(tenant_counter.used_tokens or 0),
                        "reserved_tokens": int(tenant_counter.reserved_tokens or 0),
                        "requested_reserve": requested_reserve,
                    }
                )

        if user_policy is not None:
            user_counter = await self._lock_counter(
                scope_type=UsageQuotaScopeType.user,
                scope_id=user_policy.scope_id,
                period_start=period_start,
                period_end=period_end,
            )
            projected = int(user_counter.used_tokens or 0) + int(user_counter.reserved_tokens or 0) + requested_reserve
            if projected > user_policy.limit_tokens:
                failures.append(
                    {
                        "scope_type": "user",
                        "scope_id": str(user_policy.scope_id),
                        "limit_tokens": int(user_policy.limit_tokens),
                        "used_tokens": int(user_counter.used_tokens or 0),
                        "reserved_tokens": int(user_counter.reserved_tokens or 0),
                        "requested_reserve": requested_reserve,
                    }
                )

        if failures:
            raise QuotaExceededError(
                scope_failures=failures,
                period_start=period_start,
                period_end=period_end,
            )

        if tenant_counter is not None:
            tenant_counter.reserved_tokens = int(tenant_counter.reserved_tokens or 0) + requested_reserve
        if user_counter is not None:
            user_counter.reserved_tokens = int(user_counter.reserved_tokens or 0) + requested_reserve

        reservation = UsageQuotaReservation(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            period_start=period_start,
            reserved_tokens_user=requested_reserve if user_counter is not None else 0,
            reserved_tokens_tenant=requested_reserve if tenant_counter is not None else 0,
            status=UsageQuotaReservationStatus.active,
        )
        self.db.add(reservation)
        await self.db.flush()

        return {
            "reserved_tokens": requested_reserve,
            "max_output_cap": max_output_cap,
            "period_start": period_start,
            "period_end": period_end,
        }

    async def settle_for_run(self, *, run_id: UUID, actual_usage_tokens: int) -> bool:
        reservation_result = await self.db.execute(
            select(UsageQuotaReservation)
            .where(UsageQuotaReservation.run_id == run_id)
            .with_for_update()
            .limit(1)
        )
        reservation = reservation_result.scalar_one_or_none()
        if reservation is None:
            return False
        if reservation.status in {
            UsageQuotaReservationStatus.settled,
            UsageQuotaReservationStatus.released,
            UsageQuotaReservationStatus.expired,
        }:
            return False

        usage_to_apply = max(0, int(actual_usage_tokens or 0))

        if reservation.reserved_tokens_tenant > 0:
            counter_result = await self.db.execute(
                select(UsageQuotaCounter)
                .where(
                    and_(
                        UsageQuotaCounter.scope_type == UsageQuotaScopeType.tenant,
                        UsageQuotaCounter.scope_id == reservation.tenant_id,
                        UsageQuotaCounter.period_start == reservation.period_start,
                    )
                )
                .with_for_update()
                .limit(1)
            )
            counter = counter_result.scalar_one_or_none()
            if counter is not None:
                counter.reserved_tokens = max(0, int(counter.reserved_tokens or 0) - int(reservation.reserved_tokens_tenant or 0))
                counter.used_tokens = int(counter.used_tokens or 0) + usage_to_apply

        if reservation.user_id is not None and reservation.reserved_tokens_user > 0:
            counter_result = await self.db.execute(
                select(UsageQuotaCounter)
                .where(
                    and_(
                        UsageQuotaCounter.scope_type == UsageQuotaScopeType.user,
                        UsageQuotaCounter.scope_id == reservation.user_id,
                        UsageQuotaCounter.period_start == reservation.period_start,
                    )
                )
                .with_for_update()
                .limit(1)
            )
            counter = counter_result.scalar_one_or_none()
            if counter is not None:
                counter.reserved_tokens = max(0, int(counter.reserved_tokens or 0) - int(reservation.reserved_tokens_user or 0))
                counter.used_tokens = int(counter.used_tokens or 0) + usage_to_apply

        reservation.status = UsageQuotaReservationStatus.settled
        reservation.settled_at = datetime.now(timezone.utc)
        return True

    async def release_for_run(self, *, run_id: UUID, status: UsageQuotaReservationStatus = UsageQuotaReservationStatus.released) -> bool:
        reservation_result = await self.db.execute(
            select(UsageQuotaReservation)
            .where(UsageQuotaReservation.run_id == run_id)
            .with_for_update()
            .limit(1)
        )
        reservation = reservation_result.scalar_one_or_none()
        if reservation is None:
            return False
        if reservation.status in {
            UsageQuotaReservationStatus.settled,
            UsageQuotaReservationStatus.released,
            UsageQuotaReservationStatus.expired,
        }:
            return False

        if reservation.reserved_tokens_tenant > 0:
            counter_result = await self.db.execute(
                select(UsageQuotaCounter)
                .where(
                    and_(
                        UsageQuotaCounter.scope_type == UsageQuotaScopeType.tenant,
                        UsageQuotaCounter.scope_id == reservation.tenant_id,
                        UsageQuotaCounter.period_start == reservation.period_start,
                    )
                )
                .with_for_update()
                .limit(1)
            )
            counter = counter_result.scalar_one_or_none()
            if counter is not None:
                counter.reserved_tokens = max(0, int(counter.reserved_tokens or 0) - int(reservation.reserved_tokens_tenant or 0))

        if reservation.user_id is not None and reservation.reserved_tokens_user > 0:
            counter_result = await self.db.execute(
                select(UsageQuotaCounter)
                .where(
                    and_(
                        UsageQuotaCounter.scope_type == UsageQuotaScopeType.user,
                        UsageQuotaCounter.scope_id == reservation.user_id,
                        UsageQuotaCounter.period_start == reservation.period_start,
                    )
                )
                .with_for_update()
                .limit(1)
            )
            counter = counter_result.scalar_one_or_none()
            if counter is not None:
                counter.reserved_tokens = max(0, int(counter.reserved_tokens or 0) - int(reservation.reserved_tokens_user or 0))

        reservation.status = status
        reservation.settled_at = datetime.now(timezone.utc)
        return True

    async def expire_stale_reservations(self, *, older_than_minutes: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, older_than_minutes))
        result = await self.db.execute(
            select(UsageQuotaReservation.run_id)
            .where(
                and_(
                    UsageQuotaReservation.status == UsageQuotaReservationStatus.active,
                    UsageQuotaReservation.created_at < cutoff,
                )
            )
            .limit(1000)
        )
        run_ids = [row[0] for row in result.all()]
        released = 0
        for run_id in run_ids:
            if await self.release_for_run(run_id=run_id, status=UsageQuotaReservationStatus.expired):
                released += 1
        return released

    async def reconcile_counter_from_ledger(
        self,
        *,
        scope_type: UsageQuotaScopeType,
        scope_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> int:
        run_filter = [AgentRun.created_at >= period_start, AgentRun.created_at < period_end]
        if scope_type == UsageQuotaScopeType.tenant:
            run_filter.append(AgentRun.tenant_id == scope_id)
        else:
            run_filter.append(AgentRun.user_id == scope_id)

        usage_total = (
            await self.db.execute(
                select(func.coalesce(func.sum(usage_total_expr(AgentRun)), 0)).where(and_(*run_filter))
            )
        ).scalar() or 0

        counter = await self._lock_counter(
            scope_type=scope_type,
            scope_id=scope_id,
            period_start=period_start,
            period_end=period_end,
        )
        counter.used_tokens = int(max(0, usage_total))
        return counter.used_tokens
