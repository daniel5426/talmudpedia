"""
Credentials Service - Organization-scoped integration credentials.

Provides lookup helpers for integration credentials used by model resolution
and vector store adapters.
"""
from __future__ import annotations

import os
from typing import Optional, Dict, Tuple
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory


_ENV_API_KEY_BY_CATEGORY_PROVIDER: dict[IntegrationCredentialCategory, dict[str, str]] = {
    IntegrationCredentialCategory.LLM_PROVIDER: {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "xai": "XAI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "together": "TOGETHER_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
    },
    IntegrationCredentialCategory.VECTOR_STORE: {
        "pinecone": "PINECONE_API_KEY",
        "qdrant": "QDRANT_API_KEY",
    },
    IntegrationCredentialCategory.TOOL_PROVIDER: {
        "serper": "SERPER_API_KEY",
        "tavily": "TAVILY_API_KEY",
        "exa": "EXA_API_KEY",
    },
}


def _env_var_for_provider(
    category: IntegrationCredentialCategory,
    provider_key: Optional[str],
) -> Optional[str]:
    key = (provider_key or "").strip().lower()
    return _ENV_API_KEY_BY_CATEGORY_PROVIDER.get(category, {}).get(key)


class CredentialsService:
    def __init__(self, db: AsyncSession, organization_id: Optional[UUID]):
        self._db = db
        self._organization_id = organization_id
        self._cache: Dict[Tuple, Optional[IntegrationCredential]] = {}

    async def get_by_id(self, credential_id: Optional[UUID]) -> Optional[IntegrationCredential]:
        if not credential_id:
            return None
        cache_key = ("id", str(credential_id))
        if cache_key in self._cache:
            return self._cache[cache_key]

        scope_filter = (
            IntegrationCredential.organization_id == self._organization_id
            if self._organization_id is not None
            else IntegrationCredential.organization_id == None
        )
        stmt = select(IntegrationCredential).where(IntegrationCredential.id == credential_id, scope_filter)
        res = await self._db.execute(stmt)
        credential = res.scalar_one_or_none()
        self._cache[cache_key] = credential
        return credential

    async def get_by_provider(
        self,
        category: IntegrationCredentialCategory,
        provider_key: str,
        provider_variant: Optional[str] = None,
    ) -> Optional[IntegrationCredential]:
        cache_key = ("provider", category.value, provider_key, provider_variant or "")
        if cache_key in self._cache:
            return self._cache[cache_key]

        organization_filter = (
            IntegrationCredential.organization_id == self._organization_id
            if self._organization_id is not None
            else IntegrationCredential.organization_id == None
        )
        stmt = select(IntegrationCredential).where(
            organization_filter,
            IntegrationCredential.category == category,
            IntegrationCredential.provider_key == provider_key,
            IntegrationCredential.provider_variant == provider_variant,
        )
        stmt = stmt.order_by(IntegrationCredential.updated_at.desc())
        res = await self._db.execute(stmt)
        credential = res.scalar_one_or_none()
        self._cache[cache_key] = credential
        return credential

    async def get_default_provider_credential(
        self,
        category: IntegrationCredentialCategory,
        provider_key: str,
        provider_variant: Optional[str] = None,
    ) -> Optional[IntegrationCredential]:
        cache_key = ("default-provider", category.value, provider_key, provider_variant or "")
        if cache_key in self._cache:
            return self._cache[cache_key]

        scope_filter = (
            IntegrationCredential.organization_id == self._organization_id
            if self._organization_id is not None
            else IntegrationCredential.organization_id == None
        )
        default_stmt = (
            select(IntegrationCredential)
            .where(
                scope_filter,
                IntegrationCredential.category == category,
                IntegrationCredential.provider_key == provider_key,
                IntegrationCredential.provider_variant == provider_variant,
                IntegrationCredential.is_enabled == True,
                IntegrationCredential.is_default == True,
            )
            .order_by(IntegrationCredential.updated_at.desc())
        )
        credential = (await self._db.execute(default_stmt)).scalar_one_or_none()
        if credential is None:
            # Safety fallback for pre-migration rows missing a single marked default.
            fallback_stmt = (
                select(IntegrationCredential)
                .where(
                    scope_filter,
                    IntegrationCredential.category == category,
                    IntegrationCredential.provider_key == provider_key,
                    IntegrationCredential.provider_variant == provider_variant,
                    IntegrationCredential.is_enabled == True,
                )
                .order_by(IntegrationCredential.updated_at.desc())
            )
            credential = (await self._db.execute(fallback_stmt)).scalar_one_or_none()

        self._cache[cache_key] = credential
        return credential

    @staticmethod
    def get_platform_env_credentials(
        category: Optional[IntegrationCredentialCategory],
        provider_key: Optional[str],
    ) -> Dict[str, object]:
        if category is None or not provider_key:
            return {}
        env_var = _env_var_for_provider(category, provider_key)
        if not env_var:
            return {}
        api_key = os.getenv(env_var)
        if not api_key:
            return {}
        return {"api_key": api_key}

    async def has_effective_provider_credentials(
        self,
        *,
        category: IntegrationCredentialCategory,
        provider_key: str,
        provider_variant: Optional[str] = None,
    ) -> bool:
        credential = await self.get_default_provider_credential(
            category=category,
            provider_key=provider_key,
            provider_variant=provider_variant,
        )
        if credential and credential.is_enabled and isinstance(credential.credentials, dict):
            if credential.credentials.get("api_key") or credential.credentials.get("token"):
                return True
        env_payload = self.get_platform_env_credentials(category, provider_key)
        return bool(env_payload.get("api_key") or env_payload.get("token"))

    async def enforce_single_default(
        self,
        credential: IntegrationCredential,
    ) -> None:
        """Ensure only one default credential exists per scope/category/provider[/variant]."""
        if not credential.is_default:
            return
        await self._db.execute(
            update(IntegrationCredential)
            .where(
                IntegrationCredential.id != credential.id,
                IntegrationCredential.category == credential.category,
                IntegrationCredential.provider_key == credential.provider_key,
                IntegrationCredential.provider_variant == credential.provider_variant,
                (
                    IntegrationCredential.organization_id == credential.organization_id
                    if credential.organization_id is not None
                    else IntegrationCredential.organization_id == None
                ),
            )
            .values(is_default=False)
        )

    async def resolve_backend_config(
        self,
        base_config: Dict[str, object],
        credentials_ref: Optional[UUID],
        *,
        category: Optional[IntegrationCredentialCategory] = None,
        provider_key: Optional[str] = None,
        provider_variant: Optional[str] = None,
    ) -> Dict[str, object]:
        merged = dict(base_config or {})
        credential: Optional[IntegrationCredential] = None
        # Keep routing/binding fields controlled by the resource itself.
        protected_keys = {"index_name", "collection_name", "namespace"}
        if credentials_ref:
            credential = await self.get_by_id(credentials_ref)
            if not credential:
                raise ValueError(f"Credentials not found: {credentials_ref}")
            if not credential.is_enabled:
                raise ValueError(f"Credentials disabled: {credentials_ref}")
        elif category and provider_key:
            credential = await self.get_default_provider_credential(
                category=category,
                provider_key=provider_key,
                provider_variant=provider_variant,
            )

        if credential is None:
            env_payload = self.get_platform_env_credentials(category, provider_key)
            for key, value in env_payload.items():
                if key in protected_keys and key in merged:
                    continue
                merged[key] = value
            return merged

        for key, value in (credential.credentials or {}).items():
            if key in protected_keys and key in merged:
                continue
            merged[key] = value
        return merged
