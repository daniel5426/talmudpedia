from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import Artifact, ArtifactRevision, ArtifactScope, ArtifactStatus

from .source_utils import normalize_artifact_source, source_tree_hash


class ArtifactRevisionService:
    def __init__(self, db: AsyncSession):
        self._db = db

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
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        python_dependencies: list[str],
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
    ) -> Artifact:
        artifact_id = uuid4()
        scope_value = self._normalize_scope(scope)
        source = normalize_artifact_source(
            source_files=source_files,
            entry_module_path=entry_module_path,
        )
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
        revision = self._build_revision(
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
            source_files=source.source_files,
            entry_module_path=source.entry_module_path,
            python_dependencies=python_dependencies,
            config_schema=config_schema,
            inputs=inputs,
            outputs=outputs,
            reads=reads,
            writes=writes,
            created_by=created_by,
        )
        self._db.add(revision)
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
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        python_dependencies: list[str],
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
    ) -> ArtifactRevision:
        source = normalize_artifact_source(
            source_files=source_files,
            entry_module_path=entry_module_path,
        )
        scope_value = self._normalize_scope(scope)
        artifact.display_name = display_name
        artifact.description = description
        artifact.category = category
        artifact.scope = scope_value
        artifact.input_type = input_type
        artifact.output_type = output_type
        revision = self._build_revision(
            artifact_id=artifact.id,
            tenant_id=artifact.tenant_id,
            revision_number=await self._next_revision_number(artifact.id),
            version_label="draft",
            is_published=False,
            is_ephemeral=False,
            display_name=display_name,
            description=description,
            category=category,
            input_type=input_type,
            output_type=output_type,
            scope=scope_value,
            source_files=source.source_files,
            entry_module_path=source.entry_module_path,
            python_dependencies=python_dependencies,
            config_schema=config_schema,
            inputs=inputs,
            outputs=outputs,
            reads=reads,
            writes=writes,
            created_by=updated_by,
        )
        self._db.add(revision)
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
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        python_dependencies: list[str],
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
    ) -> ArtifactRevision:
        source = normalize_artifact_source(
            source_files=source_files,
            entry_module_path=entry_module_path,
        )
        revision = self._build_revision(
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
            source_files=source.source_files,
            entry_module_path=source.entry_module_path,
            python_dependencies=python_dependencies,
            config_schema=config_schema,
            inputs=inputs,
            outputs=outputs,
            reads=reads,
            writes=writes,
            created_by=created_by,
        )
        self._db.add(revision)
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

    def _build_revision(
        self,
        *,
        artifact_id: UUID | None,
        tenant_id: UUID,
        revision_number: int,
        version_label: str,
        is_published: bool,
        is_ephemeral: bool,
        display_name: str,
        description: str | None,
        category: str,
        input_type: str,
        output_type: str,
        scope: ArtifactScope,
        source_files: list[dict[str, str]],
        entry_module_path: str,
        python_dependencies: list[str],
        config_schema: list[dict[str, Any]],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        reads: list[str],
        writes: list[str],
        created_by: UUID | None,
    ) -> ArtifactRevision:
        build_hash = source_tree_hash(
            source_files=source_files,
            entry_module_path=entry_module_path,
            python_dependencies=python_dependencies,
        )
        return ArtifactRevision(
            id=uuid4(),
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            revision_number=revision_number,
            version_label=version_label,
            is_published=is_published,
            is_ephemeral=is_ephemeral,
            display_name=display_name,
            description=description,
            category=category,
            input_type=input_type,
            output_type=output_type,
            scope=scope,
            source_files=list(source_files or []),
            entry_module_path=entry_module_path,
            manifest_json=self._build_manifest(
                artifact_id=artifact_id,
                scope=scope,
                category=category,
                input_type=input_type,
                output_type=output_type,
                python_dependencies=python_dependencies,
                entry_module_path=entry_module_path,
            ),
            python_dependencies=list(python_dependencies or []),
            config_schema=list(config_schema or []),
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            reads=list(reads or []),
            writes=list(writes or []),
            created_by=created_by,
            build_hash=build_hash,
            bundle_hash=build_hash,
            dependency_hash=build_hash,
            bundle_storage_key=None,
            bundle_inline_bytes=None,
        )

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
        python_dependencies: list[str],
        entry_module_path: str,
    ) -> dict[str, Any]:
        return {
            "artifact_id": str(artifact_id) if artifact_id else None,
            "scope": getattr(scope, "value", scope),
            "category": category,
            "input_type": input_type,
            "output_type": output_type,
            "python_dependencies": list(python_dependencies or []),
            "entry_module_path": entry_module_path,
        }
