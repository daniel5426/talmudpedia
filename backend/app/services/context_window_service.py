from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.services.model_limits_service import ModelLimitsService
from app.services.prompt_snapshot_service import PromptSnapshotService
from app.services.token_counter_service import TokenCounterService


_TOKEN_ESTIMATE_DIVISOR = max(1, int(os.getenv("TOKEN_COUNTER_CHAR_ESTIMATE_DIVISOR", "4") or 4))


class ContextWindowService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    @staticmethod
    def read_from_run(run: AgentRun | None) -> dict[str, Any] | None:
        payload = getattr(run, "context_window_json", None)
        return dict(payload) if isinstance(payload, dict) else None

    @staticmethod
    def write_to_run(run: AgentRun, payload: dict[str, Any] | None) -> None:
        run.context_window_json = dict(payload) if isinstance(payload, dict) else None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except Exception:
            return None
        return parsed if parsed >= 0 else None

    @classmethod
    def _estimate_tokens_from_chars(cls, char_count: int) -> int:
        if char_count <= 0:
            return 0
        return max(0, int(char_count // _TOKEN_ESTIMATE_DIVISOR))

    @classmethod
    def _text_length(cls, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            return len(value)
        if isinstance(value, (int, float, bool)):
            return len(str(value))
        if isinstance(value, list):
            return sum(cls._text_length(item) for item in value)
        if isinstance(value, dict):
            total = 0
            for key, item in value.items():
                if str(key or "").strip() == "context_window":
                    continue
                total += cls._text_length(item)
            return total
        return len(str(value))

    @classmethod
    def estimate_tokens_from_value(cls, value: Any) -> int:
        return cls._estimate_tokens_from_chars(cls._text_length(value))

    @classmethod
    def estimate_prompt_input_tokens(
        cls,
        *,
        messages: list[Any] | None = None,
        system_prompt: str | None = None,
        tools: list[Any] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> int:
        snapshot = PromptSnapshotService.build_from_langchain(
            messages=list(messages or []),
            system_prompt=system_prompt,
            tools=list(tools or []),
            extra_context=dict(extra_context or {}),
        )
        return cls.estimate_tokens_from_value(snapshot)

    @classmethod
    def estimate_input_tokens_from_input_params(
        cls,
        *,
        input_params: dict[str, Any],
        runtime_context: dict[str, Any] | None,
    ) -> int:
        snapshot = PromptSnapshotService.build_from_input_params(
            input_params=input_params,
            runtime_context=runtime_context,
        )
        return cls.estimate_tokens_from_value(snapshot)

    @classmethod
    def build_window(
        cls,
        *,
        source: str,
        model_id: str | None,
        max_tokens: int | None,
        max_tokens_source: str,
        input_tokens: int | None,
    ) -> dict[str, Any]:
        normalized_input = cls._safe_int(input_tokens)
        normalized_max = cls._safe_int(max_tokens)
        remaining_tokens = (
            max(0, int(normalized_max) - int(normalized_input or 0))
            if normalized_max is not None
            else None
        )
        usage_ratio = (
            min(1.0, int(normalized_input or 0) / int(normalized_max))
            if normalized_max and normalized_max > 0 and normalized_input is not None
            else None
        )
        return {
            "source": str(source or "unknown").strip() or "unknown",
            "model_id": str(model_id or "").strip() or None,
            "max_tokens": normalized_max,
            "max_tokens_source": str(max_tokens_source or "unknown").strip() or "unknown",
            "input_tokens": normalized_input,
            "remaining_tokens": remaining_tokens,
            "usage_ratio": usage_ratio,
        }

    async def build_pre_run_window(
        self,
        *,
        organization_id: UUID | None,
        model_id: str | None,
        resolved_provider: str | None = None,
        resolved_provider_model_id: str | None = None,
        api_key: str | None = None,
        input_params: dict[str, Any],
        runtime_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        snapshot = PromptSnapshotService.build_from_input_params(
            input_params=input_params,
            runtime_context=runtime_context,
        )
        max_tokens, max_tokens_source = await ModelLimitsService(self.db).resolve_input_limit(
            organization_id=organization_id,
            model_id=model_id,
            resolved_provider=resolved_provider,
            resolved_provider_model_id=resolved_provider_model_id,
            api_key=api_key,
        )
        input_tokens, source = await TokenCounterService().count_input_tokens(
            provider=resolved_provider,
            provider_model_id=resolved_provider_model_id,
            snapshot=snapshot,
            api_key=api_key,
        )
        return self.build_window(
            source=source,
            model_id=model_id,
            max_tokens=max_tokens,
            max_tokens_source=max_tokens_source,
            input_tokens=input_tokens,
        )
