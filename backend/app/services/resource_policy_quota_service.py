from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.resource_policies import (
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaCounter,
    ResourcePolicyQuotaReservation,
    ResourcePolicyQuotaWindow,
)
from app.services.model_accounting import billable_total_tokens
from app.services.resource_policy_service import ResourcePolicyPrincipalRef, ResourcePolicySnapshot
from app.services.usage_quota_service import UsageQuotaService


class ResourcePolicyQuotaExceeded(PermissionError):
    def to_payload(self) -> dict[str, str]:
        return {
            "code": "RESOURCE_POLICY_QUOTA_EXCEEDED",
            "detail": str(self),
        }


@dataclass
class ResourcePolicyQuotaReservationResult:
    max_output_cap: int | None = None
    reserved_tokens: int = 0


class ResourcePolicyQuotaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _month_bounds_utc(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
        now_utc = now_utc or datetime.now(timezone.utc)
        start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end

    async def reserve_for_run(
        self,
        *,
        run_id: UUID,
        tenant_id: UUID,
        snapshot: ResourcePolicySnapshot | None,
        model_id: UUID | None,
        input_params: dict[str, object],
    ) -> ResourcePolicyQuotaReservationResult:
        if snapshot is None or snapshot.principal is None or model_id is None:
            return ResourcePolicyQuotaReservationResult()
        quota = snapshot.get_model_quota(model_id)
        if quota is None:
            return ResourcePolicyQuotaReservationResult()

        period_start, period_end = self._month_bounds_utc()
        counter = await self._find_counter(
            principal=snapshot.principal,
            tenant_id=tenant_id,
            model_id=model_id,
            period_start=period_start,
        )
        prompt_tokens = UsageQuotaService.estimate_prompt_tokens(input_params)
        max_output_cap = UsageQuotaService._resolve_cap(input_params)
        requested_reserve = max(1, int(prompt_tokens + max_output_cap))
        projected = int((counter.used_tokens if counter is not None else 0) or 0) + int(
            (counter.reserved_tokens if counter is not None else 0) or 0
        ) + requested_reserve
        if projected > int(quota.limit_tokens):
            raise ResourcePolicyQuotaExceeded(f"Model quota exceeded for model {model_id}")
        if counter is None:
            counter = await self._create_counter(
                principal=snapshot.principal,
                tenant_id=tenant_id,
                model_id=model_id,
                period_start=period_start,
                period_end=period_end,
            )

        counter.reserved_tokens = int(counter.reserved_tokens or 0) + requested_reserve
        reservation = ResourcePolicyQuotaReservation(
            run_id=run_id,
            tenant_id=tenant_id,
            principal_type=snapshot.principal.principal_type,
            user_id=snapshot.principal.user_id,
            published_app_account_id=snapshot.principal.published_app_account_id,
            embedded_agent_id=snapshot.principal.embedded_agent_id,
            external_user_id=snapshot.principal.external_user_id,
            model_id=model_id,
            quota_window=ResourcePolicyQuotaWindow.MONTHLY,
            period_start=period_start,
            reserved_tokens=requested_reserve,
        )
        self.db.add(reservation)
        await self.db.flush()
        return ResourcePolicyQuotaReservationResult(max_output_cap=max_output_cap, reserved_tokens=requested_reserve)

    async def settle_for_run(self, *, run: AgentRun) -> None:
        if run.resolved_model_id is None:
            return
        result = await self.db.execute(
            select(ResourcePolicyQuotaReservation)
            .where(ResourcePolicyQuotaReservation.run_id == run.id)
            .limit(1)
        )
        reservation = result.scalar_one_or_none()
        if reservation is None or reservation.settled_at is not None:
            return
        counter = await self._lock_counter(
            principal=ResourcePolicyPrincipalRef(
                principal_type=reservation.principal_type,
                tenant_id=run.tenant_id,
                user_id=reservation.user_id,
                published_app_account_id=reservation.published_app_account_id,
                embedded_agent_id=reservation.embedded_agent_id,
                external_user_id=reservation.external_user_id,
            ),
            tenant_id=run.tenant_id,
            model_id=reservation.model_id,
            period_start=reservation.period_start,
            period_end=self._month_bounds_utc(reservation.period_start)[1],
        )
        actual_usage_tokens = int(billable_total_tokens(run))
        counter.reserved_tokens = max(0, int(counter.reserved_tokens or 0) - int(reservation.reserved_tokens or 0))
        counter.used_tokens = int(counter.used_tokens or 0) + actual_usage_tokens
        reservation.settled_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _find_counter(
        self,
        *,
        principal: ResourcePolicyPrincipalRef,
        tenant_id: UUID,
        model_id: UUID,
        period_start: datetime,
    ) -> ResourcePolicyQuotaCounter | None:
        for collection in (self.db.new, self.db.identity_map.values()):
            for item in collection:
                if not isinstance(item, ResourcePolicyQuotaCounter):
                    continue
                if (
                    item.tenant_id == tenant_id
                    and item.principal_type == principal.principal_type
                    and item.user_id == principal.user_id
                    and item.published_app_account_id == principal.published_app_account_id
                    and item.embedded_agent_id == principal.embedded_agent_id
                    and item.external_user_id == principal.external_user_id
                    and item.model_id == model_id
                    and item.quota_window == ResourcePolicyQuotaWindow.MONTHLY
                    and item.period_start == period_start
                ):
                    return item

        result = await self.db.execute(
            select(ResourcePolicyQuotaCounter)
            .where(
                and_(
                    ResourcePolicyQuotaCounter.tenant_id == tenant_id,
                    ResourcePolicyQuotaCounter.principal_type == principal.principal_type,
                    ResourcePolicyQuotaCounter.user_id == principal.user_id,
                    ResourcePolicyQuotaCounter.published_app_account_id == principal.published_app_account_id,
                    ResourcePolicyQuotaCounter.embedded_agent_id == principal.embedded_agent_id,
                    ResourcePolicyQuotaCounter.external_user_id == principal.external_user_id,
                    ResourcePolicyQuotaCounter.model_id == model_id,
                    ResourcePolicyQuotaCounter.quota_window == ResourcePolicyQuotaWindow.MONTHLY,
                    ResourcePolicyQuotaCounter.period_start == period_start,
                )
            )
            .with_for_update()
            .limit(1)
        )
        counter = result.scalar_one_or_none()
        return counter

    async def _create_counter(
        self,
        *,
        principal: ResourcePolicyPrincipalRef,
        tenant_id: UUID,
        model_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> ResourcePolicyQuotaCounter:
        counter = ResourcePolicyQuotaCounter(
            tenant_id=tenant_id,
            principal_type=principal.principal_type,
            user_id=principal.user_id,
            published_app_account_id=principal.published_app_account_id,
            embedded_agent_id=principal.embedded_agent_id,
            external_user_id=principal.external_user_id,
            model_id=model_id,
            quota_window=ResourcePolicyQuotaWindow.MONTHLY,
            period_start=period_start,
            period_end=period_end,
            used_tokens=0,
            reserved_tokens=0,
        )
        self.db.add(counter)
        await self.db.flush()
        return counter

    async def _lock_counter(
        self,
        *,
        principal: ResourcePolicyPrincipalRef,
        tenant_id: UUID,
        model_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> ResourcePolicyQuotaCounter:
        counter = await self._find_counter(
            principal=principal,
            tenant_id=tenant_id,
            model_id=model_id,
            period_start=period_start,
        )
        if counter is not None:
            return counter
        return await self._create_counter(
            principal=principal,
            tenant_id=tenant_id,
            model_id=model_id,
            period_start=period_start,
            period_end=period_end,
        )
