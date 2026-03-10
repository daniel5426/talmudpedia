from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    Artifact,
    ArtifactRevision,
    ArtifactScope,
    ArtifactStatus,
)

from .bundle_builder import ArtifactBundleBuilder
from .bundle_storage import ArtifactBundleStorage, ArtifactBundleStorageNotConfigured


class ArtifactRevisionService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._bundle_builder = ArtifactBundleBuilder()
        try:
            self._bundle_storage = ArtifactBundleStorage.from_env()
        except ArtifactBundleStorageNotConfigured:
            self._bundle_storage = None

    async def create_artifact(
        self,
        *,
        tenant_id: UUID,
        created_by: UUID | None,
        name: str,
        display_name: str,
        description: str | None,
        category: str,
        scope: str,
        input_type: str,
        output_type: str,
        source_code: str,
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
    ) -> Artifact:
        artifact_id = uuid4()
        revision_id = uuid4()
        scope_value = self._normalize_scope(scope)
        artifact = Artifact(
            id=artifact_id,
            tenant_id=tenant_id,
            slug=name,
            display_name=display_name,
            description=description,
            category=category,
            input_type=input_type,
            output_type=output_type,
            scope=scope_value,
            status=ArtifactStatus.DRAFT,
            created_by=created_by,
        )
        self._db.add(artifact)
        await self._db.flush()

        revision = ArtifactRevision(
            id=revision_id,
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            revision_number=1,
            version_label="draft",
            is_published=False,
            is_ephemeral=False,
            display_name=display_name,
            description=description,
            category=category,
            input_type=input_type,
            output_type=output_type,
            scope=scope_value,
            source_code=source_code,
            manifest_json=self._build_manifest(
                artifact_id=artifact_id,
                scope=scope_value,
                category=category,
                input_type=input_type,
                output_type=output_type,
            ),
            config_schema=list(config_schema or []),
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            reads=list(reads or []),
            writes=list(writes or []),
            created_by=created_by,
        )
        self._db.add(revision)
        await self._hydrate_bundle(revision)
        await self._db.flush()
        artifact.latest_draft_revision_id = revision.id
        artifact.latest_draft_revision = revision
        await self._db.flush()
        return artifact

    async def update_artifact(
        self,
        artifact: Artifact,
        *,
        updated_by: UUID | None,
        display_name: str,
        description: str | None,
        category: str,
        scope: str,
        input_type: str,
        output_type: str,
        source_code: str,
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
    ) -> ArtifactRevision:
        next_revision_number = await self._next_revision_number(artifact.id)
        revision_id = uuid4()
        scope_value = self._normalize_scope(scope)
        artifact.display_name = display_name
        artifact.description = description
        artifact.category = category
        artifact.scope = scope_value
        artifact.input_type = input_type
        artifact.output_type = output_type
        revision = ArtifactRevision(
            id=revision_id,
            artifact_id=artifact.id,
            tenant_id=artifact.tenant_id,
            revision_number=next_revision_number,
            version_label="draft",
            is_published=False,
            is_ephemeral=False,
            display_name=display_name,
            description=description,
            category=category,
            input_type=input_type,
            output_type=output_type,
            scope=scope_value,
            source_code=source_code,
            manifest_json=self._build_manifest(
                artifact_id=artifact.id,
                scope=scope_value,
                category=category,
                input_type=input_type,
                output_type=output_type,
            ),
            config_schema=list(config_schema or []),
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            reads=list(reads or []),
            writes=list(writes or []),
            created_by=updated_by,
        )
        self._db.add(revision)
        await self._hydrate_bundle(revision)
        await self._db.flush()
        artifact.latest_draft_revision_id = revision.id
        artifact.latest_draft_revision = revision
        await self._db.flush()
        return revision

    async def create_ephemeral_revision(
        self,
        *,
        tenant_id: UUID,
        created_by: UUID | None,
        artifact: Artifact | None,
        display_name: str,
        description: str | None,
        category: str,
        scope: str,
        input_type: str,
        output_type: str,
        source_code: str,
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
    ) -> ArtifactRevision:
        revision = ArtifactRevision(
            id=uuid4(),
            artifact_id=artifact.id if artifact else None,
            tenant_id=tenant_id,
            revision_number=await self._next_revision_number(artifact.id) if artifact else 0,
            version_label="draft",
            is_published=False,
            is_ephemeral=True,
            display_name=display_name,
            description=description,
            category=category,
            input_type=input_type,
            output_type=output_type,
            scope=self._normalize_scope(scope),
            source_code=source_code,
            manifest_json=self._build_manifest(
                artifact_id=artifact.id if artifact else None,
                scope=scope,
                category=category,
                input_type=input_type,
                output_type=output_type,
            ),
            config_schema=list(config_schema or []),
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            reads=list(reads or []),
            writes=list(writes or []),
            created_by=created_by,
        )
        self._db.add(revision)
        await self._hydrate_bundle(revision)
        await self._db.flush()
        return revision

    async def publish_latest_draft(self, artifact: Artifact) -> ArtifactRevision:
        revision = artifact.latest_draft_revision
        if revision is None:
            raise ValueError("Artifact has no draft revision to publish")
        if revision.is_ephemeral:
            raise ValueError("Ephemeral revisions cannot be published")
        revision.is_published = True
        revision.version_label = f"v{int(revision.revision_number or 1)}"
        artifact.latest_published_revision_id = revision.id
        artifact.latest_published_revision = revision
        artifact.status = ArtifactStatus.PUBLISHED
        await self._db.flush()
        return revision

    async def _next_revision_number(self, artifact_id: UUID | None) -> int:
        if artifact_id is None:
            return 1
        current = await self._db.scalar(
            select(func.max(ArtifactRevision.revision_number)).where(ArtifactRevision.artifact_id == artifact_id)
        )
        return int(current or 0) + 1

    async def _hydrate_bundle(self, revision: ArtifactRevision) -> None:
        built = self._bundle_builder.build_revision_bundle(revision)
        revision.bundle_hash = built.bundle_hash
        revision.dependency_hash = ""
        if self._bundle_storage is None:
            revision.bundle_inline_bytes = built.payload
            revision.bundle_storage_key = None
            return
        location = self._bundle_storage.write_bundle(
            tenant_id=str(revision.tenant_id),
            artifact_id=str(revision.artifact_id) if revision.artifact_id else None,
            revision_id=str(revision.id),
            bundle_hash=built.bundle_hash,
            payload=built.payload,
        )
        revision.bundle_storage_key = location.storage_key
        revision.bundle_inline_bytes = None

    @staticmethod
    def _normalize_scope(scope: str | ArtifactScope) -> ArtifactScope:
        raw = getattr(scope, "value", scope)
        try:
            return ArtifactScope(str(raw or "rag").strip().lower())
        except Exception:
            return ArtifactScope.RAG

    @staticmethod
    def _build_manifest(
        *,
        artifact_id: UUID | None,
        scope: str | ArtifactScope,
        category: str,
        input_type: str,
        output_type: str,
    ) -> dict[str, Any]:
        return {
            "artifact_id": str(artifact_id) if artifact_id else None,
            "scope": getattr(scope, "value", scope),
            "category": category,
            "input_type": input_type,
            "output_type": output_type,
        }
