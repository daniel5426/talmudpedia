from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from anthropic import AsyncAnthropic
from google import genai
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import ModelProviderBinding, ModelProviderType, ModelRegistry


_DEFAULT_OPENCODE_CONTEXT_WINDOW = max(
    32768,
    int(os.getenv("APPS_CODING_AGENT_OPENCODE_DEFAULT_CONTEXT_WINDOW", "256000") or 256000),
)
_KNOWN_PROVIDER_MODEL_WINDOWS: dict[tuple[str, str], int] = {
    ("openai", "gpt-5"): 1_050_000,
    ("openai", "gpt-5-mini"): 400_000,
    ("openai", "gpt-5-nano"): 400_000,
}


class ModelLimitsService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except Exception:
            return None
        return parsed if parsed > 0 else None

    async def resolve_input_limit(
        self,
        *,
        organization_id: UUID | None,
        model_id: str | None,
        resolved_provider: str | None = None,
        resolved_provider_model_id: str | None = None,
        api_key: str | None = None,
    ) -> tuple[int | None, str]:
        provider = str(resolved_provider or "").strip().lower()
        provider_model_id = str(resolved_provider_model_id or "").strip()

        if provider in {"google", "gemini"} and provider_model_id:
            provider_limit = await self._google_input_limit(provider_model_id, api_key=api_key)
            if provider_limit is not None:
                return provider_limit, "provider_model_info"

        if provider == "anthropic" and provider_model_id:
            provider_limit = await self._anthropic_input_limit(provider_model_id, api_key=api_key)
            if provider_limit is not None:
                return provider_limit, "provider_model_info"

        registry_limit, registry_source = await self._registry_context_window(organization_id=organization_id, model_id=model_id)
        if registry_limit is not None:
            return registry_limit, registry_source

        if provider and provider_model_id:
            fallback = _KNOWN_PROVIDER_MODEL_WINDOWS.get((provider, provider_model_id))
            if fallback is not None:
                return fallback, "provider_fallback"
            if provider == "opencode":
                return _DEFAULT_OPENCODE_CONTEXT_WINDOW, "provider_fallback"

        normalized_model = str(model_id or "").strip()
        if normalized_model.startswith("opencode/"):
            return _DEFAULT_OPENCODE_CONTEXT_WINDOW, "provider_fallback"
        return None, "unknown"

    async def _registry_context_window(self, *, organization_id: UUID | None, model_id: str | None) -> tuple[int | None, str]:
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
                return self._safe_int(metadata.get("context_window")), "registry"

        provider_prefix, _, provider_model_id = normalized.partition("/")
        if provider_prefix and provider_model_id and self.db is not None:
            try:
                provider_enum = ModelProviderType(provider_prefix.strip().lower())
            except Exception:
                provider_enum = None
            if provider_enum is not None:
                binding_query = (
                    select(ModelRegistry.metadata_)
                    .join(ModelProviderBinding, ModelProviderBinding.model_id == ModelRegistry.id)
                    .where(
                        and_(
                            ModelProviderBinding.provider == provider_enum,
                            ModelProviderBinding.provider_model_id == provider_model_id.strip(),
                            ModelProviderBinding.is_enabled.is_(True),
                            or_(
                                ModelProviderBinding.organization_id == organization_id,
                                ModelProviderBinding.organization_id.is_(None),
                            ),
                        )
                    )
                    .order_by(ModelProviderBinding.organization_id.is_(None), ModelProviderBinding.priority.asc())
                    .limit(1)
                )
                binding_result = await self.db.execute(binding_query)
                metadata = binding_result.scalar_one_or_none()
                if isinstance(metadata, dict):
                    return self._safe_int(metadata.get("context_window")), "registry"
        return None, "unknown"

    async def _google_input_limit(self, provider_model_id: str, *, api_key: str | None) -> int | None:
        key = str(api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            return None

        def _call() -> int | None:
            client = genai.Client(api_key=key)
            model_name = provider_model_id if str(provider_model_id).startswith("models/") else f"models/{provider_model_id}"
            info = client.models.get(model=model_name)
            return self._safe_int(getattr(info, "input_token_limit", None))

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            return None

    async def _anthropic_input_limit(self, provider_model_id: str, *, api_key: str | None) -> int | None:
        key = str(api_key or os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            return None
        client = AsyncAnthropic(api_key=key)
        try:
            info = await client.models.retrieve(provider_model_id)
        except Exception:
            return None
        return self._safe_int(getattr(info, "max_input_tokens", None))
