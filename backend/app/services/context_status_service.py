from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.registry import ModelProviderBinding, ModelProviderType, ModelRegistry


_TOKEN_ESTIMATE_DIVISOR = 4
_NEAR_LIMIT_RATIO = float(os.getenv("CONTEXT_STATUS_NEAR_LIMIT_RATIO", "0.8") or 0.8)
_COMPACTION_RECOMMENDED_RATIO = float(
    os.getenv("CONTEXT_STATUS_COMPACTION_RECOMMENDED_RATIO", "0.9") or 0.9
)
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
_TURN_CONTEXT_RUNTIME_KEY = "context_runtime"
_TURN_CONTEXT_STATUS_KEY = "context_status"
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


class ContextStatusService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    @staticmethod
    def read_from_input_params(input_params: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(input_params, dict):
            return None
        context = input_params.get("context")
        if not isinstance(context, dict):
            return None
        payload = context.get("context_status")
        return dict(payload) if isinstance(payload, dict) else None

    @staticmethod
    def read_from_run(run: AgentRun | None) -> dict[str, Any] | None:
        if run is None or not isinstance(run.input_params, dict):
            return None
        return ContextStatusService.read_from_input_params(run.input_params)

    @staticmethod
    def attach_to_input_params(
        input_params: dict[str, Any] | None,
        context_status: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(input_params or {})
        context = payload.get("context")
        context_payload = dict(context or {}) if isinstance(context, dict) else {}
        if context_status is None:
            context_payload.pop("context_status", None)
        else:
            context_payload["context_status"] = dict(context_status)
        payload["context"] = context_payload
        return payload

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except Exception:
            return None
        return parsed if parsed >= 0 else None

    @classmethod
    def _estimate_tokens_from_chars(cls, char_count: int, *, minimum_one: bool = False) -> int:
        if char_count <= 0:
            return 0
        estimated = char_count // _TOKEN_ESTIMATE_DIVISOR
        if estimated <= 0 and minimum_one:
            return 1
        return max(0, estimated)

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
                if str(key or "").strip() == "context_status":
                    continue
                total += cls._text_length(item)
            return total
        return len(str(value))

    @classmethod
    def _estimate_input_tokens(
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
                    content = message.get("content")
                    if isinstance(content, str) and content.strip() == raw_input:
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
    def _default_reserved_output_tokens(cls, max_tokens: int | None) -> int | None:
        if max_tokens is None or max_tokens <= 0:
            return None
        return min(8192, max(1024, max_tokens // 16))

    @classmethod
    def _derive_reserved_output_tokens(
        cls,
        *,
        max_tokens: int | None,
        runtime_context: dict[str, Any] | None,
        input_params: dict[str, Any],
    ) -> int | None:
        candidates = []
        if isinstance(runtime_context, dict):
            candidates.extend(
                [
                    runtime_context.get("quota_max_output_tokens"),
                    runtime_context.get("max_output_tokens"),
                    runtime_context.get("max_completion_tokens"),
                    runtime_context.get("max_tokens"),
                ]
            )
        candidates.extend(
            [
                input_params.get("max_output_tokens"),
                input_params.get("max_completion_tokens"),
                input_params.get("max_tokens"),
            ]
        )
        for candidate in candidates:
            parsed = cls._safe_int(candidate)
            if parsed and parsed > 0:
                return parsed
        return cls._default_reserved_output_tokens(max_tokens)

    @classmethod
    def _build_status(
        cls,
        *,
        model_id: str | None,
        max_tokens: int | None,
        max_tokens_source: str,
        reserved_output_tokens: int | None,
        estimated_input_tokens: int,
        actual_usage: dict[str, Any] | None = None,
        source_override: str | None = None,
    ) -> dict[str, Any]:
        estimated_total_tokens = estimated_input_tokens + int(reserved_output_tokens or 0)
        estimated_remaining_tokens = (
            max(0, int(max_tokens) - estimated_total_tokens)
            if max_tokens is not None and max_tokens > 0
            else None
        )
        estimated_usage_ratio = (
            min(1.0, estimated_total_tokens / max_tokens)
            if max_tokens is not None and max_tokens > 0
            else None
        )
        source = source_override or (
            "estimated_plus_actual" if isinstance(actual_usage, dict) and actual_usage else "estimated_pre_run"
        )
        usage_ratio_for_flags = estimated_usage_ratio or 0.0
        return {
            "model_id": model_id,
            "max_tokens": max_tokens,
            "max_tokens_source": max_tokens_source,
            "reserved_output_tokens": reserved_output_tokens,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_total_tokens": estimated_total_tokens,
            "estimated_remaining_tokens": estimated_remaining_tokens,
            "estimated_usage_ratio": estimated_usage_ratio,
            "near_limit": usage_ratio_for_flags >= _NEAR_LIMIT_RATIO,
            "compaction_recommended": usage_ratio_for_flags >= _COMPACTION_RECOMMENDED_RATIO,
            "source": source,
            "actual_usage": actual_usage or None,
        }

    @classmethod
    def _normalize_event_name(cls, event_name: Any) -> str:
        return str(event_name or "").strip().lower()

    @classmethod
    def _event_payload_for_context_increment(
        cls,
        *,
        event_name: str,
        data: dict[str, Any] | None,
    ) -> Any:
        payload = data or {}
        if event_name in {"on_tool_start", "tool.started"}:
            return {
                "input": payload.get("input"),
                "message": payload.get("message"),
            }
        if event_name in {"on_tool_end", "tool.completed"}:
            return payload.get("output")
        if event_name == "tool.failed":
            return {
                "input": payload.get("input"),
                "error": payload.get("error"),
            }
        if event_name == "retrieval":
            return payload.get("results")
        return None

    @classmethod
    def estimate_event_increment_tokens(
        cls,
        *,
        event_name: Any,
        data: dict[str, Any] | None,
    ) -> int:
        normalized_event_name = cls._normalize_event_name(event_name)
        payload = cls._event_payload_for_context_increment(
            event_name=normalized_event_name,
            data=data,
        )
        return cls._estimate_tokens_from_chars(
            cls._text_length(payload),
            minimum_one=True,
        )

    @classmethod
    def advance_for_event(
        cls,
        *,
        existing_status: dict[str, Any] | None,
        event_name: Any,
        data: dict[str, Any] | None,
        existing_runtime_metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if not isinstance(existing_status, dict):
            return None, None

        increment_tokens = cls.estimate_event_increment_tokens(
            event_name=event_name,
            data=data,
        )
        if increment_tokens <= 0:
            return None, None

        next_status = cls._build_status(
            model_id=str(existing_status.get("model_id") or "").strip() or None,
            max_tokens=cls._safe_int(existing_status.get("max_tokens")),
            max_tokens_source=str(existing_status.get("max_tokens_source") or "unknown").strip() or "unknown",
            reserved_output_tokens=cls._safe_int(existing_status.get("reserved_output_tokens")),
            estimated_input_tokens=(cls._safe_int(existing_status.get("estimated_input_tokens")) or 0) + increment_tokens,
            source_override="estimated_in_flight",
        )

        runtime_metadata = dict(existing_runtime_metadata or {})
        runtime_metadata["inflight_added_input_tokens"] = (
            cls._safe_int(runtime_metadata.get("inflight_added_input_tokens")) or 0
        ) + increment_tokens
        runtime_metadata["context_update_event_count"] = (
            cls._safe_int(runtime_metadata.get("context_update_event_count")) or 0
        ) + 1
        runtime_metadata["last_context_event"] = cls._normalize_event_name(event_name) or None
        runtime_metadata["last_increment_tokens"] = increment_tokens
        return next_status, runtime_metadata

    @classmethod
    def attach_runtime_metadata_to_context(
        cls,
        input_params: dict[str, Any] | None,
        runtime_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(input_params or {})
        context = payload.get("context")
        context_payload = dict(context or {}) if isinstance(context, dict) else {}
        if runtime_metadata:
            context_payload[_TURN_CONTEXT_RUNTIME_KEY] = dict(runtime_metadata)
        else:
            context_payload.pop(_TURN_CONTEXT_RUNTIME_KEY, None)
        payload["context"] = context_payload
        return payload

    @classmethod
    def read_runtime_metadata_from_input_params(cls, input_params: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(input_params, dict):
            return None
        context = input_params.get("context")
        if not isinstance(context, dict):
            return None
        payload = context.get(_TURN_CONTEXT_RUNTIME_KEY)
        return dict(payload) if isinstance(payload, dict) else None

    @classmethod
    def attach_turn_context_status(
        cls,
        metadata: dict[str, Any] | None,
        *,
        context_status: dict[str, Any] | None,
        runtime_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        next_metadata = dict(metadata or {})
        if context_status is None:
            next_metadata.pop(_TURN_CONTEXT_STATUS_KEY, None)
        else:
            next_metadata[_TURN_CONTEXT_STATUS_KEY] = dict(context_status)
        if runtime_metadata:
            next_metadata[_TURN_CONTEXT_RUNTIME_KEY] = dict(runtime_metadata)
        else:
            next_metadata.pop(_TURN_CONTEXT_RUNTIME_KEY, None)
        return next_metadata

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

    async def build_pre_run_status(
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
        estimated_input_tokens = self._estimate_input_tokens(
            input_params=input_params,
            runtime_context=runtime_context,
        )
        reserved_output_tokens = self._derive_reserved_output_tokens(
            max_tokens=max_tokens,
            runtime_context=runtime_context,
            input_params=input_params,
        )
        return self._build_status(
            model_id=str(model_id or "").strip() or None,
            max_tokens=max_tokens,
            max_tokens_source=max_tokens_source,
            reserved_output_tokens=reserved_output_tokens,
            estimated_input_tokens=estimated_input_tokens,
        )

    @classmethod
    def finalize_for_run(
        cls,
        *,
        existing_status: dict[str, Any] | None,
        run: AgentRun,
        resolved_model_id: str | None = None,
        resolved_context_window: int | None = None,
    ) -> dict[str, Any] | None:
        if existing_status is None and resolved_model_id is None and resolved_context_window is None:
            return None

        base = dict(existing_status or {})
        model_id = resolved_model_id or str(base.get("model_id") or "").strip() or None
        max_tokens = cls._safe_int(base.get("max_tokens"))
        max_tokens_source = str(base.get("max_tokens_source") or "unknown").strip() or "unknown"
        if resolved_context_window is not None and resolved_context_window > 0:
            max_tokens = resolved_context_window
            max_tokens_source = "resolved_execution"

        actual_usage = {
            "input_tokens": cls._safe_int(getattr(run, "input_tokens", None)),
            "output_tokens": cls._safe_int(getattr(run, "output_tokens", None)),
            "total_tokens": cls._safe_int(
                getattr(run, "total_tokens", None)
                if getattr(run, "total_tokens", None) is not None
                else getattr(run, "usage_tokens", None)
            ),
            "cached_input_tokens": cls._safe_int(getattr(run, "cached_input_tokens", None)),
            "cached_output_tokens": cls._safe_int(getattr(run, "cached_output_tokens", None)),
            "reasoning_tokens": cls._safe_int(getattr(run, "reasoning_tokens", None)),
        }
        if not any(value is not None for value in actual_usage.values()):
            actual_usage = None

        return cls._build_status(
            model_id=model_id,
            max_tokens=max_tokens,
            max_tokens_source=max_tokens_source,
            reserved_output_tokens=cls._safe_int(base.get("reserved_output_tokens")),
            estimated_input_tokens=cls._safe_int(base.get("estimated_input_tokens")) or 0,
            actual_usage=actual_usage,
        )
