from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.artifact_runtime import Artifact, ArtifactKind, ArtifactOwnerType, ArtifactRevision


class ArtifactRegistryService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_accessible_artifacts(
        self,
        *,
        tenant_id: UUID | None,
        kind: ArtifactKind | str | None = None,
    ) -> list[Artifact]:
        query = (
            select(Artifact)
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
            )
            .order_by(Artifact.updated_at.desc())
        )
        if tenant_id is not None:
            query = query.where(
                or_(
                    Artifact.owner_type == ArtifactOwnerType.SYSTEM,
                    Artifact.tenant_id == tenant_id,
                )
            )
        if kind is not None:
            query = query.where(Artifact.kind == self._normalize_kind(kind))
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def list_tenant_artifacts(self, *, tenant_id: UUID) -> list[Artifact]:
        return await self.list_accessible_artifacts(tenant_id=tenant_id)

    async def get_accessible_artifact(self, *, artifact_id: UUID, tenant_id: UUID | None) -> Artifact | None:
        query = (
            select(Artifact)
            .where(Artifact.id == artifact_id)
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
                selectinload(Artifact.revisions),
            )
        )
        if tenant_id is not None:
            query = query.where(
                or_(
                    Artifact.owner_type == ArtifactOwnerType.SYSTEM,
                    Artifact.tenant_id == tenant_id,
                )
            )
        return await self._db.scalar(query)

    async def get_tenant_artifact(self, *, artifact_id: UUID, tenant_id: UUID) -> Artifact | None:
        return await self._db.scalar(
            select(Artifact)
            .where(
                Artifact.id == artifact_id,
                Artifact.tenant_id == tenant_id,
                Artifact.owner_type == ArtifactOwnerType.TENANT,
            )
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
                selectinload(Artifact.revisions),
            )
        )

    async def get_system_artifact(self, *, system_key: str) -> Artifact | None:
        return await self._db.scalar(
            select(Artifact)
            .where(
                Artifact.owner_type == ArtifactOwnerType.SYSTEM,
                Artifact.system_key == system_key,
            )
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
                selectinload(Artifact.revisions),
            )
        )

    async def get_revision(self, *, revision_id: UUID, tenant_id: UUID | None) -> ArtifactRevision | None:
        query = (
            select(ArtifactRevision)
            .where(ArtifactRevision.id == revision_id)
            .options(selectinload(ArtifactRevision.artifact))
        )
        if tenant_id is not None:
            query = query.join(Artifact, Artifact.id == ArtifactRevision.artifact_id, isouter=True).where(
                or_(
                    Artifact.owner_type == ArtifactOwnerType.SYSTEM,
                    Artifact.tenant_id == tenant_id,
                )
            )
        return await self._db.scalar(query)

    async def get_artifact_for_custom_operator(
        self,
        *,
        tenant_id: UUID,
        custom_operator_id: UUID,
    ) -> Artifact | None:
        return await self._db.scalar(
            select(Artifact)
            .where(
                Artifact.tenant_id == tenant_id,
                Artifact.legacy_custom_operator_id == custom_operator_id,
                Artifact.kind == ArtifactKind.RAG_OPERATOR,
            )
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
            )
        )

    @staticmethod
    def _normalize_kind(kind: ArtifactKind | str) -> ArtifactKind:
        raw = getattr(kind, "value", kind)
        return ArtifactKind(str(raw).strip().lower())
