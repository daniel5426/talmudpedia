from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import normalize_scope_list
from app.core.security import get_password_hash, verify_password
from app.db.postgres.models.security import OrganizationAPIKey, OrganizationAPIKeyStatus


class OrganizationAPIKeyError(Exception):
    pass


class OrganizationAPIKeyAuthError(OrganizationAPIKeyError):
    pass


class OrganizationAPIKeyNotFoundError(OrganizationAPIKeyError):
    pass


class OrganizationAPIKeyService:
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
        organization_id: UUID,
        name: str,
        scopes: Sequence[str],
        created_by: UUID | None,
    ) -> tuple[OrganizationAPIKey, str]:
        normalized_scopes = normalize_scope_list(list(scopes))
        if not normalized_scopes:
            raise OrganizationAPIKeyError("At least one scope is required")

        key_prefix, token = self.create_key_material()
        api_key = OrganizationAPIKey(
            organization_id=organization_id,
            name=str(name).strip(),
            key_prefix=key_prefix,
            secret_hash=get_password_hash(token),
            scopes=normalized_scopes,
            status=OrganizationAPIKeyStatus.ACTIVE,
            created_by=created_by,
        )
        self.db.add(api_key)
        await self.db.flush()
        return api_key, token

    async def list_api_keys(self, *, organization_id: UUID) -> list[OrganizationAPIKey]:
        result = await self.db.execute(
            select(OrganizationAPIKey)
            .where(OrganizationAPIKey.organization_id == organization_id)
            .order_by(OrganizationAPIKey.created_at.desc(), OrganizationAPIKey.id.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(self, *, organization_id: UUID, key_id: UUID) -> OrganizationAPIKey:
        api_key = await self.db.get(OrganizationAPIKey, key_id)
        if api_key is None or api_key.organization_id != organization_id:
            raise OrganizationAPIKeyNotFoundError("API key not found")
        if api_key.status != OrganizationAPIKeyStatus.REVOKED:
            api_key.status = OrganizationAPIKeyStatus.REVOKED
            api_key.revoked_at = datetime.now(timezone.utc)
            await self.db.flush()
        return api_key

    async def delete_api_key(self, *, organization_id: UUID, key_id: UUID) -> None:
        api_key = await self.db.get(OrganizationAPIKey, key_id)
        if api_key is None or api_key.organization_id != organization_id:
            raise OrganizationAPIKeyNotFoundError("API key not found")
        await self.db.delete(api_key)
        await self.db.flush()

    async def authenticate_token(self, token: str) -> OrganizationAPIKey:
        token_text = str(token or "").strip()
        prefix, separator, _ = token_text.partition(".")
        if not prefix or separator != ".":
            raise OrganizationAPIKeyAuthError("Invalid API key format")

        result = await self.db.execute(
            select(OrganizationAPIKey).where(OrganizationAPIKey.key_prefix == prefix).limit(1)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise OrganizationAPIKeyAuthError("API key not found")
        if api_key.status != OrganizationAPIKeyStatus.ACTIVE or api_key.revoked_at is not None:
            raise OrganizationAPIKeyAuthError("API key revoked")
        if not verify_password(token_text, api_key.secret_hash):
            raise OrganizationAPIKeyAuthError("Invalid API key")

        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return api_key
