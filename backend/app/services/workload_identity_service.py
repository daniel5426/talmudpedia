from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.security import (
    WorkloadPrincipal,
    WorkloadPrincipalType,
    WorkloadPrincipalBinding,
    WorkloadResourceType,
    WorkloadScopePolicy,
    WorkloadPolicyStatus,
)


class WorkloadIdentityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_principal_by_id(self, principal_id: UUID) -> Optional[WorkloadPrincipal]:
        res = await self.db.execute(select(WorkloadPrincipal).where(WorkloadPrincipal.id == principal_id))
        return res.scalar_one_or_none()

    async def get_principal_by_slug(self, tenant_id: UUID, slug: str) -> Optional[WorkloadPrincipal]:
        res = await self.db.execute(
            select(WorkloadPrincipal).where(
                WorkloadPrincipal.tenant_id == tenant_id,
                WorkloadPrincipal.slug == slug,
            )
        )
        return res.scalar_one_or_none()

    async def ensure_principal(
        self,
        *,
        tenant_id: UUID,
        slug: str,
        name: str,
        principal_type: WorkloadPrincipalType,
        created_by: UUID | None,
        requested_scopes: Iterable[str] | None = None,
        auto_approve_system: bool = True,
    ) -> WorkloadPrincipal:
        principal = await self.get_principal_by_slug(tenant_id, slug)
        if principal is None:
            principal = WorkloadPrincipal(
                tenant_id=tenant_id,
                slug=slug,
                name=name,
                principal_type=principal_type,
                created_by=created_by,
                is_active=True,
            )
            self.db.add(principal)
            await self.db.flush()

        policy = await self.get_latest_policy(principal.id)
        requested = sorted(set(requested_scopes or []))
        if policy is None:
            status = WorkloadPolicyStatus.PENDING
            approved_scopes: list[str] = []
            approved_by = None
            approved_at = None
            if auto_approve_system and principal_type == WorkloadPrincipalType.SYSTEM:
                status = WorkloadPolicyStatus.APPROVED
                approved_scopes = requested
                approved_by = created_by
                approved_at = datetime.now(timezone.utc)

            policy = WorkloadScopePolicy(
                principal_id=principal.id,
                requested_scopes=requested,
                approved_scopes=approved_scopes,
                status=status,
                approved_by=approved_by,
                approved_at=approved_at,
                version=1,
            )
            self.db.add(policy)
            await self.db.flush()

        return principal

    async def ensure_binding(
        self,
        *,
        tenant_id: UUID,
        principal_id: UUID,
        resource_type: WorkloadResourceType,
        resource_id: str,
    ) -> WorkloadPrincipalBinding:
        res = await self.db.execute(
            select(WorkloadPrincipalBinding).where(
                WorkloadPrincipalBinding.tenant_id == tenant_id,
                WorkloadPrincipalBinding.resource_type == resource_type,
                WorkloadPrincipalBinding.resource_id == str(resource_id),
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        binding = WorkloadPrincipalBinding(
            tenant_id=tenant_id,
            principal_id=principal_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
        )
        self.db.add(binding)
        await self.db.flush()
        return binding

    async def get_latest_policy(self, principal_id: UUID) -> Optional[WorkloadScopePolicy]:
        res = await self.db.execute(
            select(WorkloadScopePolicy)
            .where(WorkloadScopePolicy.principal_id == principal_id)
            .order_by(WorkloadScopePolicy.version.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def list_pending_policies(self, tenant_id: UUID) -> list[WorkloadScopePolicy]:
        latest_policy_version = (
            select(
                WorkloadScopePolicy.principal_id.label("principal_id"),
                func.max(WorkloadScopePolicy.version).label("max_version"),
            )
            .group_by(WorkloadScopePolicy.principal_id)
            .subquery()
        )

        res = await self.db.execute(
            select(WorkloadScopePolicy)
            .join(WorkloadPrincipal, WorkloadPrincipal.id == WorkloadScopePolicy.principal_id)
            .join(
                latest_policy_version,
                and_(
                    latest_policy_version.c.principal_id == WorkloadScopePolicy.principal_id,
                    latest_policy_version.c.max_version == WorkloadScopePolicy.version,
                ),
            )
            .where(
                WorkloadPrincipal.tenant_id == tenant_id,
                WorkloadScopePolicy.status == WorkloadPolicyStatus.PENDING,
            )
            .order_by(WorkloadScopePolicy.created_at.asc())
        )
        return list(res.scalars().all())

    async def approve_policy(
        self,
        *,
        principal_id: UUID,
        approved_by: UUID,
        approved_scopes: Iterable[str],
    ) -> WorkloadScopePolicy:
        current = await self.get_latest_policy(principal_id)
        if current is None:
            raise ValueError("No policy found for principal")

        new_policy = WorkloadScopePolicy(
            principal_id=principal_id,
            requested_scopes=current.requested_scopes or [],
            approved_scopes=sorted(set(approved_scopes)),
            status=WorkloadPolicyStatus.APPROVED,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            version=(current.version or 0) + 1,
        )
        self.db.add(new_policy)
        await self.db.flush()
        return new_policy

    async def reject_policy(self, *, principal_id: UUID, approved_by: UUID) -> WorkloadScopePolicy:
        current = await self.get_latest_policy(principal_id)
        if current is None:
            raise ValueError("No policy found for principal")

        new_policy = WorkloadScopePolicy(
            principal_id=principal_id,
            requested_scopes=current.requested_scopes or [],
            approved_scopes=[],
            status=WorkloadPolicyStatus.REJECTED,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            version=(current.version or 0) + 1,
        )
        self.db.add(new_policy)
        await self.db.flush()
        return new_policy
