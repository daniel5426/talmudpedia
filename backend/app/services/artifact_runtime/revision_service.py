from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import (
    Artifact,
    ArtifactKind,
    ArtifactOwnerType,
    ArtifactRevision,
    ArtifactStatus,
)

from .source_utils import normalize_artifact_source, source_tree_hash


class ArtifactRevisionService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_artifact(
        self,
        *,
        tenant_id: UUID | None,
        created_by: UUID | None,
        slug: str,
        display_name: str,
        description: str | None,
        kind: str,
        owner_type: str = "tenant",
        system_key: str | None = None,
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        python_dependencies: list[str],
        runtime_target: str,
        capabilities: dict[str, Any],
        config_schema: dict[str, Any],
        agent_contract: dict[str, Any] | None = None,
        rag_contract: dict[str, Any] | None = None,
        tool_contract: dict[str, Any] | None = None,
    ) -> Artifact:
        artifact_id = uuid4()
        kind_value = self._normalize_kind(kind)
        owner_type_value = self._normalize_owner_type(owner_type)
        self._validate_contracts(
            kind=kind_value,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
        )
        source = normalize_artifact_source(
            source_files=source_files,
            entry_module_path=entry_module_path,
        )
        artifact = Artifact(
            id=artifact_id,
            tenant_id=tenant_id,
            slug=slug,
            display_name=display_name,
            description=description,
            kind=kind_value,
            owner_type=owner_type_value,
            status=ArtifactStatus.DRAFT,
            created_by=created_by,
            system_key=system_key,
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
            kind=kind_value,
            source_files=source.source_files,
            entry_module_path=source.entry_module_path,
            python_dependencies=python_dependencies,
            runtime_target=runtime_target,
            capabilities=capabilities,
            config_schema=config_schema,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
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
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        python_dependencies: list[str],
        runtime_target: str,
        capabilities: dict[str, Any],
        config_schema: dict[str, Any],
        agent_contract: dict[str, Any] | None = None,
        rag_contract: dict[str, Any] | None = None,
        tool_contract: dict[str, Any] | None = None,
    ) -> ArtifactRevision:
        source = normalize_artifact_source(
            source_files=source_files,
            entry_module_path=entry_module_path,
        )
        kind_value = self._normalize_kind(artifact.kind)
        self._validate_contracts(
            kind=kind_value,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
        )
        artifact.display_name = display_name
        artifact.description = description
        revision = self._build_revision(
            artifact_id=artifact.id,
            tenant_id=artifact.tenant_id,
            revision_number=await self._next_revision_number(artifact.id),
            version_label="draft",
            is_published=False,
            is_ephemeral=False,
            display_name=display_name,
            description=description,
            kind=kind_value,
            source_files=source.source_files,
            entry_module_path=source.entry_module_path,
            python_dependencies=python_dependencies,
            runtime_target=runtime_target,
            capabilities=capabilities,
            config_schema=config_schema,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
            created_by=updated_by,
        )
        self._db.add(revision)
        await self._db.flush()
        artifact.latest_draft_revision_id = revision.id
        artifact.latest_draft_revision = revision
        await self._db.flush()
        return revision

    async def convert_kind(
        self,
        artifact: Artifact,
        *,
        updated_by: UUID | None,
        kind: str,
        agent_contract: dict[str, Any] | None = None,
        rag_contract: dict[str, Any] | None = None,
        tool_contract: dict[str, Any] | None = None,
    ) -> ArtifactRevision:
        if artifact.latest_published_revision_id is not None:
            raise ValueError("Published artifacts cannot change kind in place")
        target_kind = self._normalize_kind(kind)
        self._validate_contracts(
            kind=target_kind,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
        )
        current_revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if current_revision is None:
            raise ValueError("Artifact is missing a current revision")
        artifact.kind = target_kind
        revision = self._build_revision(
            artifact_id=artifact.id,
            tenant_id=artifact.tenant_id,
            revision_number=await self._next_revision_number(artifact.id),
            version_label="draft",
            is_published=False,
            is_ephemeral=False,
            display_name=artifact.display_name,
            description=artifact.description,
            kind=target_kind,
            source_files=list(current_revision.source_files or []),
            entry_module_path=current_revision.entry_module_path,
            python_dependencies=list(current_revision.python_dependencies or []),
            runtime_target=str(current_revision.runtime_target or "cloudflare_workers"),
            capabilities=dict(current_revision.capabilities or {}),
            config_schema=dict(current_revision.config_schema or {}),
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
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
        tenant_id: UUID | None,
        created_by: UUID | None,
        artifact: Artifact | None,
        display_name: str,
        description: str | None,
        kind: str,
        source_files: list[dict[str, Any]] | None = None,
        entry_module_path: str | None = None,
        python_dependencies: list[str],
        runtime_target: str,
        capabilities: dict[str, Any],
        config_schema: dict[str, Any],
        agent_contract: dict[str, Any] | None = None,
        rag_contract: dict[str, Any] | None = None,
        tool_contract: dict[str, Any] | None = None,
    ) -> ArtifactRevision:
        source = normalize_artifact_source(
            source_files=source_files,
            entry_module_path=entry_module_path,
        )
        kind_value = self._normalize_kind(kind)
        self._validate_contracts(
            kind=kind_value,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
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
            kind=kind_value,
            source_files=source.source_files,
            entry_module_path=source.entry_module_path,
            python_dependencies=python_dependencies,
            runtime_target=runtime_target,
            capabilities=capabilities,
            config_schema=config_schema,
            agent_contract=agent_contract,
            rag_contract=rag_contract,
            tool_contract=tool_contract,
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
        tenant_id: UUID | None,
        revision_number: int,
        version_label: str,
        is_published: bool,
        is_ephemeral: bool,
        display_name: str,
        description: str | None,
        kind: ArtifactKind,
        source_files: list[dict[str, str]],
        entry_module_path: str,
        python_dependencies: list[str],
        runtime_target: str,
        capabilities: dict[str, Any],
        config_schema: dict[str, Any],
        agent_contract: dict[str, Any] | None,
        rag_contract: dict[str, Any] | None,
        tool_contract: dict[str, Any] | None,
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
            kind=kind,
            source_files=list(source_files or []),
            entry_module_path=entry_module_path,
            manifest_json=self._build_manifest(
                artifact_id=artifact_id,
                kind=kind,
                python_dependencies=python_dependencies,
                entry_module_path=entry_module_path,
                runtime_target=runtime_target,
            ),
            python_dependencies=list(python_dependencies or []),
            runtime_target=runtime_target or "cloudflare_workers",
            capabilities=dict(capabilities or {}),
            config_schema=dict(config_schema or {}),
            agent_contract=dict(agent_contract or {}) if agent_contract is not None else None,
            rag_contract=dict(rag_contract or {}) if rag_contract is not None else None,
            tool_contract=dict(tool_contract or {}) if tool_contract is not None else None,
            created_by=created_by,
            build_hash=build_hash,
            bundle_hash=build_hash,
            dependency_hash=build_hash,
            bundle_storage_key=None,
            bundle_inline_bytes=None,
        )

    @staticmethod
    def _normalize_kind(kind: str | ArtifactKind) -> ArtifactKind:
        raw = getattr(kind, "value", kind)
        return ArtifactKind(str(raw or ArtifactKind.RAG_OPERATOR.value).strip().lower())

    @staticmethod
    def _normalize_owner_type(owner_type: str | ArtifactOwnerType) -> ArtifactOwnerType:
        raw = getattr(owner_type, "value", owner_type)
        return ArtifactOwnerType(str(raw or ArtifactOwnerType.TENANT.value).strip().lower())

    @staticmethod
    def _validate_contracts(
        *,
        kind: ArtifactKind,
        agent_contract: dict[str, Any] | None,
        rag_contract: dict[str, Any] | None,
        tool_contract: dict[str, Any] | None,
    ) -> None:
        if kind == ArtifactKind.AGENT_NODE:
            if agent_contract is None or rag_contract is not None or tool_contract is not None:
                raise ValueError("agent_node artifacts require only agent_contract")
            return
        if kind == ArtifactKind.RAG_OPERATOR:
            if rag_contract is None or agent_contract is not None or tool_contract is not None:
                raise ValueError("rag_operator artifacts require only rag_contract")
            return
        if tool_contract is None or agent_contract is not None or rag_contract is not None:
            raise ValueError("tool_impl artifacts require only tool_contract")

    @staticmethod
    def _build_manifest(
        *,
        artifact_id: UUID | None,
        kind: ArtifactKind,
        python_dependencies: list[str],
        entry_module_path: str,
        runtime_target: str,
    ) -> dict[str, Any]:
        return {
            "artifact_id": str(artifact_id) if artifact_id else None,
            "kind": kind.value,
            "python_dependencies": list(python_dependencies or []),
            "entry_module_path": entry_module_path,
            "runtime_target": runtime_target,
        }
