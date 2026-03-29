from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.registry import ModelProviderBinding, ModelProviderType, ModelRegistry


_TOKEN_ESTIMATE_DIVISOR = 4
_DEFAULT_OPENCODE_CONTEXT_WINDOW = max(
    32768,
    int(os.getenv("APPS_CODING_AGENT_OPENCODE_DEFAULT_CONTEXT_WINDOW", "256000") or 256000),
)
_KNOWN_PROVIDER_MODEL_WINDOWS: dict[tuple[str, str], int] = {
    ("openai", "gpt-5"): 1_050_000,
    ("openai", "gpt-5-mini"): 400_000,
    ("openai", "gpt-5-nano"): 400_000,
}
_PROMPT_CONTEXT_KEYS = {
    "selected_agent_contract",
    "artifact_payload",
    "draft_snapshot",
    "platform_assets_create_input",
    "platform_assets_update_input",
}
_ROOT_SKIP_KEYS = {
    "attachment_ids",
    "attachments",
    "context",
    "input_display_text",
    "input",
    "messages",
    "state",
    "thread_id",
}


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
        total_chars = 0
        if system_prompt:
            total_chars += cls._text_length({"role": "system", "content": system_prompt})
        if isinstance(messages, list):
            total_chars += cls._text_length(messages)
        if isinstance(tools, list):
            total_chars += cls._text_length(tools)
        if isinstance(extra_context, dict):
            total_chars += cls._text_length(extra_context)
        return cls._estimate_tokens_from_chars(total_chars)

    @classmethod
    def estimate_input_tokens_from_input_params(
        cls,
        *,
        input_params: dict[str, Any],
        runtime_context: dict[str, Any] | None,
    ) -> int:
        total_chars = 0
        raw_input = str(input_params.get("input") or "").strip()
        messages = input_params.get("messages")
        total_chars += cls._text_length(messages)
        if raw_input:
            duplicate_in_messages = False
            if isinstance(messages, list):
                for message in reversed(messages):
                    if not isinstance(message, dict):
                        continue
                    if str(message.get("role") or "").strip().lower() != "user":
                        continue
                    if str(message.get("content") or "").strip() == raw_input:
                        duplicate_in_messages = True
                    break
            if not duplicate_in_messages:
                total_chars += len(raw_input)
        total_chars += cls._text_length(input_params.get("attachments"))
        for key, value in input_params.items():
            if key in _ROOT_SKIP_KEYS:
                continue
            total_chars += cls._text_length(value)
        if isinstance(runtime_context, dict):
            for key in _PROMPT_CONTEXT_KEYS:
                if key in runtime_context:
                    total_chars += cls._text_length(runtime_context.get(key))
        return cls._estimate_tokens_from_chars(total_chars)

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

    async def _resolve_context_window(self, *, tenant_id: UUID | None, model_id: str | None) -> tuple[int | None, str]:
        normalized = str(model_id or "").strip()
        if not normalized:
            return None, "unknown"

        try:
            parsed_uuid = UUID(normalized)
        except Exception:
            parsed_uuid = None

        if self.db is not None and parsed_uuid is not None:
            model = await self.db.get(ModelRegistry, parsed_uuid)
            if model is not None:
                metadata = dict(model.metadata_ or {})
                return self._safe_int(metadata.get("context_window")), "registry"

        if self.db is not None:
            model_result = await self.db.execute(
                select(ModelRegistry).where(ModelRegistry.system_key == normalized).limit(1)
            )
            by_system_key = model_result.scalar_one_or_none()
            if by_system_key is not None:
                metadata = dict(by_system_key.metadata_ or {})
                return self._safe_int(metadata.get("context_window")), "registry_system_key"

        provider_prefix, _, provider_model_id = normalized.partition("/")
        if provider_prefix and provider_model_id:
            provider_value = provider_prefix.strip().lower()
            provider_model_value = provider_model_id.strip()
            if self.db is not None:
                try:
                    provider_enum = ModelProviderType(provider_value)
                except Exception:
                    provider_enum = None
                if provider_enum is not None:
                    binding_query = (
                        select(ModelRegistry.metadata_)
                        .join(ModelProviderBinding, ModelProviderBinding.model_id == ModelRegistry.id)
                        .where(
                            and_(
                                ModelProviderBinding.provider == provider_enum,
                                ModelProviderBinding.provider_model_id == provider_model_value,
                                ModelProviderBinding.is_enabled.is_(True),
                                or_(
                                    ModelProviderBinding.tenant_id == tenant_id,
                                    ModelProviderBinding.tenant_id.is_(None),
                                ),
                            )
                        )
                        .order_by(ModelProviderBinding.tenant_id.is_(None), ModelProviderBinding.priority.asc())
                        .limit(1)
                    )
                    binding_result = await self.db.execute(binding_query)
                    metadata = binding_result.scalar_one_or_none()
                    if isinstance(metadata, dict):
                        return self._safe_int(metadata.get("context_window")), "registry_provider_binding"
            fallback = _KNOWN_PROVIDER_MODEL_WINDOWS.get((provider_value, provider_model_value))
            if fallback is not None:
                return fallback, "provider_fallback"
            if provider_value == "opencode":
                return _DEFAULT_OPENCODE_CONTEXT_WINDOW, "opencode_default"

        if normalized.startswith("opencode/"):
            return _DEFAULT_OPENCODE_CONTEXT_WINDOW, "opencode_default"

        return None, "unknown"

    async def build_pre_run_window(
        self,
        *,
        tenant_id: UUID | None,
        model_id: str | None,
        input_params: dict[str, Any],
        runtime_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        max_tokens, max_tokens_source = await self._resolve_context_window(
            tenant_id=tenant_id,
            model_id=model_id,
        )
        input_tokens = self.estimate_input_tokens_from_input_params(
            input_params=input_params,
            runtime_context=runtime_context,
        )
        return self.build_window(
            source="estimated",
            model_id=model_id,
            max_tokens=max_tokens,
            max_tokens_source=max_tokens_source,
            input_tokens=input_tokens,
        )
