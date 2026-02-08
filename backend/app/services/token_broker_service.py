from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workload_jwt import issue_workload_token
from app.db.postgres.models.security import (
    DelegationGrant,
    DelegationGrantStatus,
    TokenJTIRegistry,
)


class TokenBrokerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_grant(self, grant_id: UUID) -> Optional[DelegationGrant]:
        res = await self.db.execute(select(DelegationGrant).where(DelegationGrant.id == grant_id))
        return res.scalar_one_or_none()

    async def mint_workload_token(
        self,
        *,
        grant_id: UUID,
        audience: str,
        scope_subset: Iterable[str] | None = None,
    ) -> tuple[str, dict]:
        grant = await self.get_grant(grant_id)
        if grant is None:
            raise ValueError("Delegation grant not found")
        if grant.status != DelegationGrantStatus.ACTIVE:
            raise ValueError("Delegation grant is not active")
        if grant.expires_at <= datetime.now(timezone.utc):
            grant.status = DelegationGrantStatus.EXPIRED
            await self.db.flush()
            raise ValueError("Delegation grant expired")

        allowed_scopes = set(grant.effective_scopes or [])
        if not allowed_scopes:
            raise PermissionError("Delegation grant has no effective scopes")

        requested = set(scope_subset or allowed_scopes)
        scoped = sorted(allowed_scopes.intersection(requested))
        if not scoped:
            raise PermissionError("Requested scope subset is not allowed")

        token, payload = issue_workload_token(
            audience=audience,
            tenant_id=str(grant.tenant_id),
            principal_id=str(grant.principal_id),
            grant_id=str(grant.id),
            initiator_user_id=str(grant.initiator_user_id) if grant.initiator_user_id else None,
            scopes=scoped,
            run_id=str(grant.run_id) if grant.run_id else None,
        )

        self.db.add(
            TokenJTIRegistry(
                jti=payload["jti"],
                grant_id=grant.id,
                expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            )
        )
        await self.db.flush()
        return token, payload

    async def is_jti_active(self, jti: str) -> bool:
        res = await self.db.execute(select(TokenJTIRegistry).where(TokenJTIRegistry.jti == jti))
        item = res.scalar_one_or_none()
        if item is None:
            return False
        if item.revoked_at is not None:
            return False
        expires_at = item.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at <= datetime.now(timezone.utc):
            return False
        return True

    async def revoke_grant(self, grant_id: UUID, reason: str = "policy_update") -> None:
        grant = await self.get_grant(grant_id)
        if grant is None:
            return
        grant.status = DelegationGrantStatus.REVOKED

        tokens_res = await self.db.execute(
            select(TokenJTIRegistry).where(TokenJTIRegistry.grant_id == grant_id)
        )
        now = datetime.now(timezone.utc)
        for token in tokens_res.scalars().all():
            token.revoked_at = now
            token.revocation_reason = reason
        await self.db.flush()
