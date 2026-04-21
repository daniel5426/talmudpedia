from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import normalize_scope_list
from app.core.security import get_password_hash, verify_password
from app.db.postgres.models.security import ProjectAPIKey, ProjectAPIKeyStatus


class ProjectAPIKeyError(Exception):
    pass


class ProjectAPIKeyAuthError(ProjectAPIKeyError):
    pass


class ProjectAPIKeyNotFoundError(ProjectAPIKeyError):
    pass


class ProjectAPIKeyService:
    TOKEN_PREFIX = "ppk"

    def __init__(self, db: AsyncSession):
        self.db = db

    def create_key_material(self) -> tuple[str, str]:
        from app.services.organization_api_key_service import OrganizationAPIKeyService

        key_prefix, token = OrganizationAPIKeyService(self.db).create_key_material()
        key_prefix = key_prefix.replace(f"{OrganizationAPIKeyService.TOKEN_PREFIX}_", f"{self.TOKEN_PREFIX}_", 1)
        token = token.replace(f"{OrganizationAPIKeyService.TOKEN_PREFIX}_", f"{self.TOKEN_PREFIX}_", 1)
        return key_prefix, token

    async def create_api_key(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        name: str,
        scopes: Sequence[str],
        created_by: UUID | None,
    ) -> tuple[ProjectAPIKey, str]:
        normalized_scopes = normalize_scope_list(list(scopes))
        if not normalized_scopes:
            raise ProjectAPIKeyError("At least one scope is required")

        key_prefix, token = self.create_key_material()
        api_key = ProjectAPIKey(
            organization_id=organization_id,
            project_id=project_id,
            name=str(name).strip(),
            key_prefix=key_prefix,
            secret_hash=get_password_hash(token),
            scopes=normalized_scopes,
            status=ProjectAPIKeyStatus.ACTIVE,
            created_by=created_by,
        )
        self.db.add(api_key)
        await self.db.flush()
        return api_key, token

    async def list_api_keys(self, *, organization_id: UUID, project_id: UUID) -> list[ProjectAPIKey]:
        result = await self.db.execute(
            select(ProjectAPIKey)
            .where(
                ProjectAPIKey.organization_id == organization_id,
                ProjectAPIKey.project_id == project_id,
            )
            .order_by(ProjectAPIKey.created_at.desc(), ProjectAPIKey.id.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(self, *, organization_id: UUID, project_id: UUID, key_id: UUID) -> ProjectAPIKey:
        api_key = await self.db.get(ProjectAPIKey, key_id)
        if api_key is None or api_key.organization_id != organization_id or api_key.project_id != project_id:
            raise ProjectAPIKeyNotFoundError("API key not found")
        if api_key.status != ProjectAPIKeyStatus.REVOKED:
            api_key.status = ProjectAPIKeyStatus.REVOKED
            api_key.revoked_at = datetime.now(timezone.utc)
            await self.db.flush()
        return api_key

    async def delete_api_key(self, *, organization_id: UUID, project_id: UUID, key_id: UUID) -> None:
        api_key = await self.db.get(ProjectAPIKey, key_id)
        if api_key is None or api_key.organization_id != organization_id or api_key.project_id != project_id:
            raise ProjectAPIKeyNotFoundError("API key not found")
        await self.db.delete(api_key)
        await self.db.flush()

    async def authenticate_token(self, token: str) -> ProjectAPIKey:
        token_text = str(token or "").strip()
        prefix, separator, _ = token_text.partition(".")
        if not prefix or separator != ".":
            raise ProjectAPIKeyAuthError("Invalid API key format")

        result = await self.db.execute(
            select(ProjectAPIKey).where(ProjectAPIKey.key_prefix == prefix).limit(1)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise ProjectAPIKeyAuthError("API key not found")
        if api_key.status != ProjectAPIKeyStatus.ACTIVE or api_key.revoked_at is not None:
            raise ProjectAPIKeyAuthError("API key revoked")
        if not verify_password(token_text, api_key.secret_hash):
            raise ProjectAPIKeyAuthError("Invalid API key")

        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return api_key
