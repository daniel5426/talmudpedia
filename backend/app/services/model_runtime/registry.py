from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.db.postgres.models.registry import ModelCapabilityType, ModelProviderType


RuntimeFactory = Callable[..., Awaitable[Any]]


class ModelRuntimeAdapterRegistry:
    _factories: dict[tuple[ModelCapabilityType, ModelProviderType], RuntimeFactory] = {}

    @classmethod
    def register(
        cls,
        *,
        capability: ModelCapabilityType,
        provider: ModelProviderType,
        factory: RuntimeFactory,
    ) -> None:
        cls._factories[(capability, provider)] = factory

    @classmethod
    def get(
        cls,
        *,
        capability: ModelCapabilityType,
        provider: ModelProviderType,
    ) -> RuntimeFactory | None:
        return cls._factories.get((capability, provider))

    @classmethod
    def supports(
        cls,
        *,
        capability: ModelCapabilityType,
        provider: ModelProviderType,
    ) -> bool:
        return (capability, provider) in cls._factories
