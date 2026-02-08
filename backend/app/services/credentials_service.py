"""
Credentials Service - Tenant-scoped integration credentials.

Provides lookup helpers for integration credentials used by model resolution
and vector store adapters.
"""
from __future__ import annotations

from typing import Optional, Dict, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory


class CredentialsService:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self._db = db
        self._tenant_id = tenant_id
        self._cache: Dict[Tuple, Optional[IntegrationCredential]] = {}

    async def get_by_id(self, credential_id: Optional[UUID]) -> Optional[IntegrationCredential]:
        if not credential_id:
            return None
        cache_key = ("id", str(credential_id))
        if cache_key in self._cache:
            return self._cache[cache_key]

        stmt = select(IntegrationCredential).where(
            IntegrationCredential.id == credential_id,
            IntegrationCredential.tenant_id == self._tenant_id,
        )
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

        stmt = select(IntegrationCredential).where(
            IntegrationCredential.tenant_id == self._tenant_id,
            IntegrationCredential.category == category,
            IntegrationCredential.provider_key == provider_key,
            IntegrationCredential.provider_variant == provider_variant,
        )
        res = await self._db.execute(stmt)
        credential = res.scalar_one_or_none()
        self._cache[cache_key] = credential
        return credential

    async def resolve_backend_config(
        self,
        base_config: Dict[str, object],
        credentials_ref: Optional[UUID],
    ) -> Dict[str, object]:
        merged = dict(base_config or {})
        if not credentials_ref:
            return merged

        credential = await self.get_by_id(credentials_ref)
        if not credential:
            raise ValueError(f"Credentials not found: {credentials_ref}")
        if not credential.is_enabled:
            raise ValueError(f"Credentials disabled: {credentials_ref}")

        merged.update(credential.credentials or {})
        return merged
