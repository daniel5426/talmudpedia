from __future__ import annotations

from typing import Any


_TEMP_LOCKED_OPENAI_PREFIXES = (
    "gpt-5",
    "o1",
    "o3",
    "o4",
)


def _normalize_provider(provider: Any) -> str:
    value = getattr(provider, "value", provider)
    return str(value or "").strip().lower()


def model_requires_temperature_one(*, provider: Any, model_name: str | None) -> bool:
    normalized_provider = _normalize_provider(provider)
    normalized_model = str(model_name or "").strip().lower()
    if not normalized_model:
        return False
    if normalized_provider not in {"openai", "azure"}:
        return False
    return normalized_model.startswith(_TEMP_LOCKED_OPENAI_PREFIXES)


def normalize_temperature_for_model(
    *,
    provider: Any,
    model_name: str | None,
    temperature: Any,
) -> Any:
    if not model_requires_temperature_one(provider=provider, model_name=model_name):
        return temperature
    return 1.0
