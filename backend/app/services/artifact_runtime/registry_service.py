from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.artifact_runtime import Artifact
from app.services.artifact_registry import get_artifact_registry


class ArtifactRegistryService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo_registry = get_artifact_registry()

    async def list_tenant_artifacts(self, *, tenant_id: UUID) -> list[Artifact]:
        result = await self._db.execute(
            select(Artifact)
            .where(Artifact.tenant_id == tenant_id)
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
            )
            .order_by(Artifact.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_tenant_artifact(self, *, artifact_id: UUID, tenant_id: UUID) -> Artifact | None:
        return await self._db.scalar(
            select(Artifact)
            .where(Artifact.id == artifact_id, Artifact.tenant_id == tenant_id)
            .options(
                selectinload(Artifact.latest_draft_revision),
                selectinload(Artifact.latest_published_revision),
                selectinload(Artifact.revisions),
            )
        )

    def list_repo_artifacts(self):
        return self._repo_registry.get_all_artifacts()

    def get_repo_artifact(self, artifact_id: str):
        return self._repo_registry.get_artifact(artifact_id)

    def get_repo_artifact_path(self, artifact_id: str):
        return self._repo_registry.get_artifact_path(artifact_id)

    def get_repo_artifact_code(self, artifact_id: str):
        return self._repo_registry.get_artifact_code(artifact_id)
