from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from app.db.postgres.models.registry import ModelCapabilityType, ModelProviderBinding, ModelRegistry


RuntimeT = TypeVar("RuntimeT")


@dataclass
class ResolvedModelRuntimeExecution(Generic[RuntimeT]):
    logical_model: ModelRegistry
    binding: ModelProviderBinding
    runtime_instance: RuntimeT
    binding_scope: str
    merged_config: dict[str, Any]
    credentials_payload: dict[str, Any]
    pricing_snapshot: dict[str, Any]
    capability_flags: dict[str, bool]
    capability_type: ModelCapabilityType

    @property
    def provider_instance(self) -> RuntimeT:
        return self.runtime_instance

    @property
    def resolved_provider(self) -> str:
        return getattr(self.binding.provider, "value", str(self.binding.provider))

    @property
    def context_window(self) -> int | None:
        metadata = dict(getattr(self.logical_model, "metadata_", {}) or {})
        try:
            value = int(metadata.get("context_window"))
        except Exception:
            return None
        return value if value > 0 else None


@dataclass
class ResolvedModelBindingReceipt:
    logical_model: ModelRegistry
    binding: ModelProviderBinding
    binding_scope: str
    merged_config: dict[str, Any]
    credentials_payload: dict[str, Any]
    pricing_snapshot: dict[str, Any]
    capability_flags: dict[str, bool]
    capability_type: ModelCapabilityType

    @property
    def resolved_provider(self) -> str:
        return getattr(self.binding.provider, "value", str(self.binding.provider))

    @property
    def api_key(self) -> str | None:
        value = self.credentials_payload.get("api_key")
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None
