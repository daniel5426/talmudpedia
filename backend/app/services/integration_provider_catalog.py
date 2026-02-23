from __future__ import annotations

from app.db.postgres.models.registry import (
    IntegrationCredentialCategory,
    ModelProviderType,
)


TOOL_PROVIDER_KEYS: tuple[str, ...] = ("serper", "tavily", "exa")
VECTOR_PROVIDER_KEYS: tuple[str, ...] = ("pinecone", "qdrant", "pgvector", "postgres", "postgresql")


def allowed_provider_keys(category: IntegrationCredentialCategory) -> set[str] | None:
    if category == IntegrationCredentialCategory.LLM_PROVIDER:
        return {provider.value for provider in ModelProviderType}
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

