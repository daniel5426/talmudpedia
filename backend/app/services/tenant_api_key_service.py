from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import normalize_scope_list
from app.core.security import get_password_hash, verify_password
from app.db.postgres.models.security import TenantAPIKey, TenantAPIKeyStatus


class TenantAPIKeyError(Exception):
    pass


class TenantAPIKeyAuthError(TenantAPIKeyError):
    pass


class TenantAPIKeyNotFoundError(TenantAPIKeyError):
    pass


class TenantAPIKeyService:
    TOKEN_PREFIX = "tpk"

    def __init__(self, db: AsyncSession):
        self.db = db

    def create_key_material(self) -> tuple[str, str]:
        key_prefix = f"{self.TOKEN_PREFIX}_{secrets.token_urlsafe(9)}"
        token_secret = secrets.token_urlsafe(24)
        token = f"{key_prefix}.{token_secret}"
        return key_prefix, token

    async def create_api_key(
        self,
        *,
        tenant_id: UUID,
        name: str,
        scopes: Sequence[str],
        created_by: UUID | None,
    ) -> tuple[TenantAPIKey, str]:
        normalized_scopes = normalize_scope_list(list(scopes))
        if not normalized_scopes:
            raise TenantAPIKeyError("At least one scope is required")

        key_prefix, token = self.create_key_material()
        api_key = TenantAPIKey(
            tenant_id=tenant_id,
            name=str(name).strip(),
            key_prefix=key_prefix,
            secret_hash=get_password_hash(token),
            scopes=normalized_scopes,
            status=TenantAPIKeyStatus.ACTIVE,
            created_by=created_by,
        )
        self.db.add(api_key)
        await self.db.flush()
        return api_key, token

    async def list_api_keys(self, *, tenant_id: UUID) -> list[TenantAPIKey]:
        result = await self.db.execute(
            select(TenantAPIKey)
            .where(TenantAPIKey.tenant_id == tenant_id)
            .order_by(TenantAPIKey.created_at.desc(), TenantAPIKey.id.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(self, *, tenant_id: UUID, key_id: UUID) -> TenantAPIKey:
        api_key = await self.db.get(TenantAPIKey, key_id)
        if api_key is None or api_key.tenant_id != tenant_id:
            raise TenantAPIKeyNotFoundError("API key not found")
        if api_key.status != TenantAPIKeyStatus.REVOKED:
            api_key.status = TenantAPIKeyStatus.REVOKED
            api_key.revoked_at = datetime.now(timezone.utc)
            await self.db.flush()
        return api_key

    async def authenticate_token(self, token: str) -> TenantAPIKey:
        token_text = str(token or "").strip()
        prefix, separator, _ = token_text.partition(".")
        if not prefix or separator != ".":
            raise TenantAPIKeyAuthError("Invalid API key format")

        result = await self.db.execute(
            select(TenantAPIKey).where(TenantAPIKey.key_prefix == prefix).limit(1)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise TenantAPIKeyAuthError("API key not found")
        if api_key.status != TenantAPIKeyStatus.ACTIVE or api_key.revoked_at is not None:
            raise TenantAPIKeyAuthError("API key revoked")
        if not verify_password(token_text, api_key.secret_hash):
            raise TenantAPIKeyAuthError("Invalid API key")

        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return api_key
