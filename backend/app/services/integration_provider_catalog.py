from __future__ import annotations

from dataclasses import dataclass

from app.db.postgres.models.registry import (
    IntegrationCredentialCategory,
    ModelCapabilityType,
    ModelProviderType,
)


@dataclass(frozen=True)
class ModelProviderCatalogEntry:
    provider: ModelProviderType
    label: str
    supported_capabilities: frozenset[ModelCapabilityType]
    required_credential_keys: tuple[str, ...] = ("api_key",)


TOOL_PROVIDER_KEYS: tuple[str, ...] = ("serper", "tavily", "exa")
VECTOR_PROVIDER_KEYS: tuple[str, ...] = ("pinecone", "qdrant", "pgvector", "postgres", "postgresql")

_LLM_STYLE_CAPABILITIES = frozenset(
    {
        ModelCapabilityType.CHAT,
        ModelCapabilityType.COMPLETION,
        ModelCapabilityType.VISION,
    }
)

MODEL_PROVIDER_CATALOG: dict[ModelProviderType, ModelProviderCatalogEntry] = {
    ModelProviderType.OPENAI: ModelProviderCatalogEntry(
        provider=ModelProviderType.OPENAI,
        label="OpenAI",
        supported_capabilities=_LLM_STYLE_CAPABILITIES | frozenset({ModelCapabilityType.EMBEDDING}),
    ),
    ModelProviderType.GOOGLE: ModelProviderCatalogEntry(
        provider=ModelProviderType.GOOGLE,
        label="Google AI",
        supported_capabilities=_LLM_STYLE_CAPABILITIES,
    ),
    ModelProviderType.ANTHROPIC: ModelProviderCatalogEntry(
        provider=ModelProviderType.ANTHROPIC,
        label="Anthropic",
        supported_capabilities=_LLM_STYLE_CAPABILITIES,
    ),
    ModelProviderType.XAI: ModelProviderCatalogEntry(
        provider=ModelProviderType.XAI,
        label="xAI",
        supported_capabilities=_LLM_STYLE_CAPABILITIES,
    ),
}


def allowed_provider_keys(category: IntegrationCredentialCategory) -> set[str] | None:
    if category == IntegrationCredentialCategory.LLM_PROVIDER:
        return {provider.value for provider in MODEL_PROVIDER_CATALOG}
    if category == IntegrationCredentialCategory.VECTOR_STORE:
        return set(VECTOR_PROVIDER_KEYS)
    if category == IntegrationCredentialCategory.TOOL_PROVIDER:
        return set(TOOL_PROVIDER_KEYS)
    if category == IntegrationCredentialCategory.CUSTOM:
        return None
    return None


def is_provider_key_allowed(category: IntegrationCredentialCategory, provider_key: str) -> bool:
    allowed = allowed_provider_keys(category)
    if allowed is None:
        return True
    return (provider_key or "").strip().lower() in allowed


def get_model_provider_catalog_entry(
    provider: ModelProviderType | str,
) -> ModelProviderCatalogEntry | None:
    normalized = provider if isinstance(provider, ModelProviderType) else ModelProviderType(str(provider).strip().lower())
    return MODEL_PROVIDER_CATALOG.get(normalized)


def is_model_provider_supported(
    *,
    provider: ModelProviderType,
    capability: ModelCapabilityType,
) -> bool:
    entry = MODEL_PROVIDER_CATALOG.get(provider)
    if entry is None:
        return False
    return capability in entry.supported_capabilities


def supported_model_providers_for_capability(
    capability: ModelCapabilityType,
) -> tuple[ModelProviderCatalogEntry, ...]:
    return tuple(
        entry
        for entry in MODEL_PROVIDER_CATALOG.values()
        if capability in entry.supported_capabilities
    )
