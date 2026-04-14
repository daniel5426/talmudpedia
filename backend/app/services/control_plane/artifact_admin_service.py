from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.db.postgres.models.artifact_runtime import Artifact, ArtifactOwnerType
from app.services.artifact_runtime.deployment_service import ArtifactDeploymentService
from app.services.artifact_runtime.execution_service import ArtifactConcurrencyLimitExceeded, ArtifactExecutionService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListPage, ListQuery, OperationResult
from app.services.control_plane.errors import conflict, not_found, rate_limited, validation
from app.services.tool_binding_service import ToolBindingService


@dataclass(frozen=True)
class ArtifactRuntimeInput:
    language: str = "python"
    source_files: list[dict[str, Any]] | None = None
    entry_module_path: str = "main.py"
    dependencies: list[str] | None = None
    runtime_target: str = "cloudflare_workers"


@dataclass(frozen=True)
class CreateArtifactInput:
    display_name: str
    description: str | None = None
    kind: str = "tool_impl"
    runtime: ArtifactRuntimeInput = ArtifactRuntimeInput()
    capabilities: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None
    agent_contract: dict[str, Any] | None = None
    rag_contract: dict[str, Any] | None = None
    tool_contract: dict[str, Any] | None = None


@dataclass(frozen=True)
class UpdateArtifactInput:
    display_name: str | None = None
    description: str | None = None
    runtime: ArtifactRuntimeInput | None = None
    capabilities: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None
    agent_contract: dict[str, Any] | None = None
    rag_contract: dict[str, Any] | None = None
    tool_contract: dict[str, Any] | None = None


class ArtifactAdminService:
    def __init__(self, db):
        self.db = db
        self.registry = ArtifactRegistryService(db)
        self.revisions = ArtifactRevisionService(db)

    async def list_artifacts(self, *, ctx: ControlPlaneContext, query: ListQuery) -> ListPage:
        artifacts = await self.registry.list_accessible_artifacts(tenant_id=ctx.tenant_id)
        items = [self.serialize_artifact(item, view=query.view) for item in artifacts[query.skip: query.skip + query.limit]]
        return ListPage(items=items, total=len(artifacts), query=query)

    async def get_artifact(self, *, ctx: ControlPlaneContext, artifact_id: UUID) -> dict[str, Any]:
        artifact = await self.registry.get_accessible_artifact(artifact_id=artifact_id, tenant_id=ctx.tenant_id)
        if artifact is None:
            raise not_found("Artifact not found", artifact_id=str(artifact_id))
        return self.serialize_artifact(artifact, include_code=True)

    async def create_artifact(self, *, ctx: ControlPlaneContext, params: CreateArtifactInput) -> dict[str, Any]:
        display_name = str(params.display_name or "").strip()
        if not display_name:
            raise validation("display_name is required", field="display_name")
        try:
            artifact = await self.revisions.create_artifact(
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                display_name=display_name,
                description=params.description,
                kind=params.kind,
                owner_type=ArtifactOwnerType.TENANT.value,
                source_files=list(params.runtime.source_files or []),
                entry_module_path=params.runtime.entry_module_path,
                language=params.runtime.language,
                dependencies=list(params.runtime.dependencies or []),
                runtime_target=params.runtime.runtime_target,
                capabilities=dict(params.capabilities or {}),
                config_schema=dict(params.config_schema or {}),
                agent_contract=params.agent_contract,
                rag_contract=params.rag_contract,
                tool_contract=params.tool_contract,
            )
            await ToolBindingService(self.db).sync_artifact_tool_binding(artifact)
            await self.db.commit()
        except ValueError as exc:
            raise validation(str(exc)) from exc
        refreshed = await self.registry.get_tenant_artifact(artifact_id=artifact.id, tenant_id=ctx.tenant_id)
        return self.serialize_artifact(refreshed, include_code=True)

    async def update_artifact(self, *, ctx: ControlPlaneContext, artifact_id: UUID, params: UpdateArtifactInput) -> dict[str, Any]:
        artifact = await self.registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=ctx.tenant_id)
        if artifact is None:
            raise not_found("Artifact not found", artifact_id=str(artifact_id))
        current_revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if current_revision is None:
            raise conflict("Artifact is missing a current revision", artifact_id=str(artifact_id))
        runtime = params.runtime
        try:
            await self.revisions.update_artifact(
                artifact,
                updated_by=ctx.user_id,
                display_name=params.display_name or artifact.display_name,
                description=params.description if params.description is not None else artifact.description,
                source_files=list(runtime.source_files) if runtime and runtime.source_files is not None else list(current_revision.source_files or []),
                entry_module_path=runtime.entry_module_path if runtime is not None else current_revision.entry_module_path,
                language=runtime.language if runtime is not None else str(getattr(current_revision.language, "value", current_revision.language) or "python"),
                dependencies=list(runtime.dependencies or []) if runtime is not None else list(current_revision.python_dependencies or []),
                runtime_target=runtime.runtime_target if runtime is not None else str(current_revision.runtime_target or "cloudflare_workers"),
                capabilities=dict(params.capabilities if params.capabilities is not None else (current_revision.capabilities or {})),
                config_schema=dict(params.config_schema if params.config_schema is not None else (current_revision.config_schema or {})),
                agent_contract=params.agent_contract if params.agent_contract is not None else (dict(current_revision.agent_contract or {}) if current_revision.agent_contract is not None else None),
                rag_contract=params.rag_contract if params.rag_contract is not None else (dict(current_revision.rag_contract or {}) if current_revision.rag_contract is not None else None),
                tool_contract=params.tool_contract if params.tool_contract is not None else (dict(current_revision.tool_contract or {}) if current_revision.tool_contract is not None else None),
            )
            await ToolBindingService(self.db).sync_artifact_tool_binding(artifact)
            await self.db.commit()
        except ValueError as exc:
            raise validation(str(exc)) from exc
        refreshed = await self.registry.get_tenant_artifact(artifact_id=artifact.id, tenant_id=ctx.tenant_id)
        return self.serialize_artifact(refreshed, include_code=True)

    async def convert_kind(
        self,
        *,
        ctx: ControlPlaneContext,
        artifact_id: UUID,
        kind: str,
        agent_contract: dict[str, Any] | None,
        rag_contract: dict[str, Any] | None,
        tool_contract: dict[str, Any] | None,
    ) -> dict[str, Any]:
        artifact = await self.registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=ctx.tenant_id)
        if artifact is None:
            raise not_found("Artifact not found", artifact_id=str(artifact_id))
        binding_service = ToolBindingService(self.db)
        if getattr(artifact.kind, "value", artifact.kind) == "tool_impl" and str(kind) != "tool_impl":
            await binding_service.delete_artifact_tool_binding(artifact.id)
        try:
            await self.revisions.convert_kind(
                artifact,
                updated_by=ctx.user_id,
                kind=kind,
                agent_contract=agent_contract,
                rag_contract=rag_contract,
                tool_contract=tool_contract,
            )
            await binding_service.sync_artifact_tool_binding(artifact)
            await self.db.commit()
        except ValueError as exc:
            raise validation(str(exc)) from exc
        refreshed = await self.registry.get_tenant_artifact(artifact_id=artifact.id, tenant_id=ctx.tenant_id)
        return self.serialize_artifact(refreshed, include_code=True)

    async def publish_artifact(self, *, ctx: ControlPlaneContext, artifact_id: UUID) -> dict[str, Any]:
        artifact = await self.registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=ctx.tenant_id)
        if artifact is None:
            raise not_found("Artifact not found", artifact_id=str(artifact_id))
        try:
            revision = await self.revisions.publish_latest_draft(artifact)
            await ArtifactDeploymentService(self.db).ensure_deployment(
                revision=revision,
                namespace="production",
                tenant_id=ctx.tenant_id,
            )
            await ToolBindingService(self.db).publish_artifact_tool_binding(
                artifact=artifact,
                revision=revision,
                created_by=ctx.user_id,
            )
            await self.db.commit()
        except ValueError as exc:
            raise validation(str(exc)) from exc
        return {
            "artifact_id": str(artifact.id),
            "revision_id": str(revision.id),
            "version": revision.version_label,
            "status": "published",
        }

    async def delete_artifact(self, *, ctx: ControlPlaneContext, artifact_id: UUID) -> dict[str, Any]:
        artifact = await self.registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=ctx.tenant_id)
        if artifact is None:
            raise not_found("Artifact not found", artifact_id=str(artifact_id))
        await ToolBindingService(self.db).delete_artifact_tool_binding(artifact.id)
        await self.db.delete(artifact)
        await self.db.commit()
        return {"status": "deleted"}

    async def create_test_run(
        self,
        *,
        ctx: ControlPlaneContext,
        artifact_id: UUID | None,
        source_files: list[dict[str, Any]],
        entry_module_path: str | None,
        input_data: Any,
        config: dict[str, Any],
        dependencies: list[str],
        language: str | None,
        kind: str | None,
        runtime_target: str | None,
        capabilities: dict[str, Any],
        config_schema: dict[str, Any],
        agent_contract: dict[str, Any] | None,
        rag_contract: dict[str, Any] | None,
        tool_contract: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            run = await ArtifactExecutionService(self.db).start_test_run(
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                artifact_id=artifact_id,
                source_files=source_files,
                entry_module_path=entry_module_path,
                input_data=input_data,
                config=config,
                dependencies=dependencies,
                language=language,
                kind=kind,
                runtime_target=runtime_target,
                capabilities=capabilities,
                config_schema=config_schema,
                agent_contract=agent_contract,
                rag_contract=rag_contract,
                tool_contract=tool_contract,
            )
        except ArtifactConcurrencyLimitExceeded as exc:
            raise rate_limited(str(exc)) from exc
        except ValueError as exc:
            raise validation(str(exc)) from exc
        return OperationResult(
            operation_id=str(run.id),
            kind="artifact_test_run",
            status=str(getattr(run.status, "value", run.status)).lower(),
        ).to_dict()

    @staticmethod
    def serialize_artifact(artifact: Artifact | None, *, view: str = "full", include_code: bool = False) -> dict[str, Any]:
        if artifact is None:
            raise ValueError("artifact is required")
        revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if revision is None:
            raise ValueError("Artifact is missing a current revision")
        payload = {
            "id": str(artifact.id),
            "display_name": artifact.display_name,
            "description": artifact.description,
            "kind": getattr(artifact.kind, "value", artifact.kind),
            "owner_type": getattr(artifact.owner_type, "value", artifact.owner_type),
            "type": "published" if getattr(artifact.status, "value", artifact.status) == "published" and bool(revision.is_published) else "draft",
            "version": revision.version_label,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
        }
        if view == "summary":
            return payload
        payload.update(
            {
            "config_schema": dict(revision.config_schema or {}),
            "runtime": {
                "language": str(getattr(revision.language, "value", revision.language) or "python"),
                "source_files": list(revision.source_files or []) if include_code else [],
                "entry_module_path": revision.entry_module_path,
                "dependencies": list(revision.python_dependencies or []),
                "runtime_target": str(revision.runtime_target or "cloudflare_workers"),
            },
            "capabilities": dict(revision.capabilities or {}),
            "agent_contract": dict(revision.agent_contract or {}) if revision.agent_contract is not None else None,
            "rag_contract": dict(revision.rag_contract or {}) if revision.rag_contract is not None else None,
            "tool_contract": dict(revision.tool_contract or {}) if revision.tool_contract is not None else None,
            "system_key": artifact.system_key,
            }
        )
        return payload
