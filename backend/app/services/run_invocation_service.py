from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, AgentRunInvocation
from app.services.context_window_service import ContextWindowService
from app.services.model_accounting import (
    EXACT_USAGE_SOURCES,
    ESTIMATED_USAGE_SOURCES,
    USAGE_SOURCE_ESTIMATED,
    USAGE_SOURCE_EXACT,
    USAGE_SOURCE_UNKNOWN,
    NormalizedUsage,
)


class RunInvocationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except Exception:
            return None
        return parsed if parsed >= 0 else None

    @classmethod
    def _normalize_source(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in EXACT_USAGE_SOURCES:
            return USAGE_SOURCE_EXACT
        if normalized in ESTIMATED_USAGE_SOURCES:
            return USAGE_SOURCE_ESTIMATED
        return USAGE_SOURCE_UNKNOWN

    @classmethod
    def estimate_output_tokens(cls, message: Any) -> int:
        return ContextWindowService.estimate_tokens_from_value(message)

    @classmethod
    def usage_from_payload(cls, payload: dict[str, Any] | None) -> NormalizedUsage:
        payload = dict(payload or {})
        return NormalizedUsage(
            input_tokens=cls._safe_int(payload.get("input_tokens")),
            output_tokens=cls._safe_int(payload.get("output_tokens")),
            total_tokens=cls._safe_int(payload.get("total_tokens")),
            cached_input_tokens=cls._safe_int(payload.get("cached_input_tokens")),
            cached_output_tokens=cls._safe_int(payload.get("cached_output_tokens")),
            reasoning_tokens=cls._safe_int(payload.get("reasoning_tokens")),
        ).finalize()

    @classmethod
    def build_invocation_payload(
        cls,
        *,
        model_id: str | None,
        resolved_provider: str | None,
        resolved_provider_model_id: str | None,
        node_id: str | None,
        node_name: str | None,
        node_type: str | None,
        max_context_tokens: int | None,
        max_context_tokens_source: str,
        context_input_tokens: int | None,
        context_source: str | None,
        exact_usage_payload: dict[str, Any] | None,
        estimated_output_tokens: int | None,
    ) -> dict[str, Any]:
        exact_usage = cls.usage_from_payload(exact_usage_payload)
        has_exact_usage = bool(exact_usage.to_json())
        usage_source = USAGE_SOURCE_EXACT if has_exact_usage else (
            USAGE_SOURCE_ESTIMATED if context_input_tokens is not None or estimated_output_tokens is not None else USAGE_SOURCE_UNKNOWN
        )

        if has_exact_usage:
            usage = exact_usage
        else:
            usage = NormalizedUsage(
                input_tokens=cls._safe_int(context_input_tokens),
                output_tokens=cls._safe_int(estimated_output_tokens),
            ).finalize()

        normalized_context_input = cls._safe_int(context_input_tokens)
        normalized_context_source = str(context_source or "").strip() or USAGE_SOURCE_UNKNOWN
        if normalized_context_input is None and usage.input_tokens is not None and has_exact_usage:
            normalized_context_input = usage.input_tokens
            if normalized_context_source == USAGE_SOURCE_UNKNOWN:
                normalized_context_source = USAGE_SOURCE_EXACT
        context_window = ContextWindowService.build_window(
            source=normalized_context_source,
            model_id=model_id,
            max_tokens=max_context_tokens,
            max_tokens_source=max_context_tokens_source,
            input_tokens=normalized_context_input,
        )
        return {
            "model_id": str(model_id or "").strip() or None,
            "resolved_provider": str(resolved_provider or "").strip() or None,
            "resolved_provider_model_id": str(resolved_provider_model_id or "").strip() or None,
            "node_id": str(node_id or "").strip() or None,
            "node_name": str(node_name or "").strip() or None,
            "node_type": str(node_type or "").strip() or None,
            "usage": {
                "source": usage_source,
                **usage.to_json(),
            },
            "context_window": context_window,
            "estimated_input_tokens": normalized_context_input,
            "estimated_output_tokens": cls._safe_int(estimated_output_tokens),
        }

    async def reset_run_invocations(self, run_id: UUID) -> None:
        await self.db.execute(delete(AgentRunInvocation).where(AgentRunInvocation.run_id == run_id))

    async def append_from_payload(self, *, run: AgentRun, payload: dict[str, Any]) -> AgentRunInvocation:
        seq_result = await self.db.execute(
            select(AgentRunInvocation.sequence)
            .where(AgentRunInvocation.run_id == run.id)
            .order_by(AgentRunInvocation.sequence.desc())
            .limit(1)
        )
        next_sequence = int(seq_result.scalar_one_or_none() or 0) + 1

        usage = self.usage_from_payload((payload.get("usage") or {}) if isinstance(payload.get("usage"), dict) else {})
        context_window = payload.get("context_window") if isinstance(payload.get("context_window"), dict) else {}
        record = AgentRunInvocation(
            id=uuid4(),
            run_id=run.id,
            sequence=next_sequence,
            node_id=str(payload.get("node_id") or "").strip() or None,
            node_name=str(payload.get("node_name") or "").strip() or None,
            node_type=str(payload.get("node_type") or "").strip() or None,
            model_id=str(payload.get("model_id") or "").strip() or None,
            resolved_provider=str(payload.get("resolved_provider") or "").strip() or None,
            resolved_provider_model_id=str(payload.get("resolved_provider_model_id") or "").strip() or None,
            usage_source=self._normalize_source((payload.get("usage") or {}).get("source")),
            context_source=str(context_window.get("source") or "").strip() or None,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cached_output_tokens=usage.cached_output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            context_input_tokens=self._safe_int(context_window.get("input_tokens")),
            max_context_tokens=self._safe_int(context_window.get("max_tokens")),
            max_context_tokens_source=str(context_window.get("max_tokens_source") or "").strip() or None,
            payload_json=payload,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def recompute_run_aggregates(self, run: AgentRun) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        result = await self.db.execute(
            select(AgentRunInvocation)
            .where(AgentRunInvocation.run_id == run.id)
            .order_by(AgentRunInvocation.sequence.asc())
        )
        invocations = list(result.scalars().all())
        if not invocations:
            run.usage_source = USAGE_SOURCE_UNKNOWN
            run.input_tokens = None
            run.output_tokens = None
            run.total_tokens = None
            run.cached_input_tokens = None
            run.cached_output_tokens = None
            run.reasoning_tokens = None
            run.usage_breakdown_json = None
            run.usage_tokens = 0
            ContextWindowService.write_to_run(run, None)
            return None, None

        totals = NormalizedUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cached_input_tokens=0,
            cached_output_tokens=0,
            reasoning_tokens=0,
        )
        all_exact = True
        any_numeric = False
        for invocation in invocations:
            source = self._normalize_source(invocation.usage_source)
            if source != USAGE_SOURCE_EXACT:
                all_exact = False
            for field_name in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cached_input_tokens",
                "cached_output_tokens",
                "reasoning_tokens",
            ):
                value = getattr(invocation, field_name, None)
                if value is None:
                    continue
                any_numeric = True
                setattr(totals, field_name, int(getattr(totals, field_name, 0) or 0) + int(value))
        totals = totals.finalize()
        usage_source = USAGE_SOURCE_EXACT if all_exact and any_numeric else (
            USAGE_SOURCE_ESTIMATED if any_numeric else USAGE_SOURCE_UNKNOWN
        )

        run.usage_source = usage_source
        run.input_tokens = totals.input_tokens
        run.output_tokens = totals.output_tokens
        run.total_tokens = totals.total_tokens
        run.cached_input_tokens = totals.cached_input_tokens
        run.cached_output_tokens = totals.cached_output_tokens
        run.reasoning_tokens = totals.reasoning_tokens
        run.usage_breakdown_json = totals.to_json() or None
        run.usage_tokens = int(totals.total_tokens or 0)

        latest = invocations[-1]
        context_window = ContextWindowService.build_window(
            source=str(latest.context_source or "").strip() or USAGE_SOURCE_UNKNOWN,
            model_id=latest.model_id,
            max_tokens=latest.max_context_tokens,
            max_tokens_source=str(latest.max_context_tokens_source or "unknown").strip() or "unknown",
            input_tokens=latest.context_input_tokens,
        )
        ContextWindowService.write_to_run(run, context_window)
        return totals.to_json() or None, context_window
