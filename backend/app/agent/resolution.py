import logging
from uuid import UUID
from typing import Optional, Dict, Any
from sqlalchemy import select, text, and_, or_
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import ArtifactKind
from app.db.postgres.models.registry import ToolRegistry
from app.db.postgres.models.rag import ExecutablePipeline, VisualPipeline, PipelineType
from app.services.artifact_runtime.registry_service import ArtifactRegistryService

logger = logging.getLogger(__name__)

class ResolutionError(Exception):
    pass

class ComponentResolver:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _parse_uuid(value: Any) -> UUID | None:
        if value in (None, ""):
            return None
        try:
            return UUID(str(value))
        except Exception:
            return None

class ToolResolver(ComponentResolver):
    async def _tool_registry_columns(self) -> set[str]:
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'tool_registry'
                      AND column_name IN ('artifact_id', 'artifact_version', 'artifact_revision_id')
                    """
                )
            )
            return {row[0] for row in result.all()}
        except Exception:
            # SQLite fallback
            try:
                result = await self.db.execute(text("PRAGMA table_info(tool_registry)"))
                return {row[1] for row in result.all()}
            except Exception:
                return set()

    async def resolve(self, tool_id: UUID, require_published: bool = False) -> Dict[str, Any]:
        """
        Verify tool exists and return minimal execution metadata.
        """
        tool = None
        try:
            columns = await self._tool_registry_columns()
            if "artifact_id" in columns and "artifact_version" in columns:
                if self.tenant_id is None:
                    scope_condition = ToolRegistry.tenant_id == None
                else:
                    scope_condition = or_(
                        ToolRegistry.tenant_id == self.tenant_id,
                        ToolRegistry.tenant_id == None,
                    )
                stmt = select(ToolRegistry).where(
                    and_(
                        ToolRegistry.id == tool_id,
                        scope_condition,
                    )
                )
                result = await self.db.execute(stmt)
                tool = result.scalar_one_or_none()
            else:
                raise ProgrammingError("tool_registry missing artifact columns", None, None)
        except ProgrammingError as e:
            # Fallback for older schemas missing artifact columns
            logger.warning(f"ToolResolver falling back to raw query due to schema mismatch: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            raw = await self.db.execute(
                text(
                    """
                    SELECT id, name, is_active
                    FROM tool_registry
                    WHERE id = :tool_id
                    """
                ),
                {"tool_id": str(tool_id)},
            )
            row = raw.first()
            if row:
                class _Tool:
                    def __init__(self, id, name, is_active):
                        self.id = id
                        self.name = name
                        self.is_active = is_active
                tool = _Tool(row[0], row[1], row[2])
        
        if not tool:
            raise ResolutionError(f"Tool {tool_id} not found")
            
        # Optional: Check if active?
        if not tool.is_active:
             raise ResolutionError(f"Tool {tool_id} is inactive")

        if require_published:
            status_val = getattr(tool, "status", None)
            status_text = str(getattr(status_val, "value", status_val or "")).lower()
            if status_text != "published":
                raise ResolutionError(f"Tool {tool_id} must be published for production execution")
            artifact_revision_id = getattr(tool, "artifact_revision_id", None)
            artifact_id = getattr(tool, "artifact_id", None)
            config_schema = getattr(tool, "config_schema", {}) or {}
            implementation_type = getattr(tool, "implementation_type", None)
            implementation_type_text = str(getattr(implementation_type, "value", implementation_type or "")).lower()
            implementation_artifact_id = None
            if isinstance(config_schema, dict):
                implementation = config_schema.get("implementation") or {}
                if isinstance(implementation, dict):
                    implementation_artifact_id = implementation.get("artifact_id")
            if artifact_revision_id is None and (
                self._parse_uuid(artifact_id) is not None
                or (
                    implementation_type_text == "artifact"
                    and self._parse_uuid(implementation_artifact_id) is not None
                )
            ):
                raise ResolutionError(f"Tool {tool_id} must pin artifact_revision_id for production execution")
             
        impl_type = getattr(tool, "implementation_type", None)
        if hasattr(impl_type, "value"):
            impl_type = impl_type.value
        if not impl_type:
            config_schema = getattr(tool, "config_schema", {}) or {}
            impl_type = (config_schema.get("implementation") or {}).get("type", "internal")

        return {
            "id": str(tool.id),
            "name": tool.name,
            "implementation_type": impl_type,
            "status": str(getattr(getattr(tool, "status", None), "value", getattr(tool, "status", ""))),
            "artifact_id": getattr(tool, "artifact_id", None),
            "artifact_revision_id": str(getattr(tool, "artifact_revision_id", None)) if getattr(tool, "artifact_revision_id", None) else None,
        }


class ArtifactResolver(ComponentResolver):
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        super().__init__(db, tenant_id)
        self._registry = ArtifactRegistryService(db)

    async def resolve(self, artifact_ref: str, require_published: bool = False) -> Dict[str, Any]:
        artifact_uuid = self._parse_uuid(artifact_ref)
        if artifact_uuid is None:
            raise ResolutionError("Artifact nodes now require UUID artifact ids")

        if self.tenant_id is None:
            raise ResolutionError("Tenant context required for tenant artifact resolution")

        artifact = await self._registry.get_tenant_artifact(
            artifact_id=artifact_uuid,
            tenant_id=self.tenant_id,
        )
        if artifact is None:
            raise ResolutionError(f"Artifact {artifact_ref} not found")
        if artifact.kind != ArtifactKind.AGENT_NODE:
            raise ResolutionError(f"Artifact {artifact_ref} is not an agent_node artifact")

        revision = artifact.latest_published_revision
        if not require_published:
            revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if revision is None:
            raise ResolutionError(f"Artifact {artifact_ref} has no executable revision")
        if require_published and (not revision.is_published or revision.is_ephemeral):
            raise ResolutionError(f"Artifact {artifact_ref} requires a published immutable revision")

        return {
            "artifact_kind": "tenant",
            "artifact_id": str(artifact.id),
            "artifact_revision_id": str(revision.id),
            "status": str(getattr(getattr(artifact, "status", None), "value", getattr(artifact, "status", ""))),
            "display_name": str(getattr(artifact, "display_name", artifact.id)),
            "config_schema": dict(revision.config_schema or {}) if revision.config_schema is not None else {},
            "agent_contract": dict(revision.agent_contract or {}) if revision.agent_contract is not None else {},
        }

class RAGPipelineResolver(ComponentResolver):
    async def resolve(self, pipeline_id: UUID) -> Dict[str, Any]:
        """
        Verify pipeline exists.
        For RAG, we link to 'ExecutablePipeline' or 'Pipeline' definition?
        The node config field is 'pipeline_id'. 
        If it refers to a generic 'Pipeline', we might need to find the active 'ExecutablePipeline'.
        For Phase 1/2 we've been using 'ExecutablePipeline' directly or assuming we can find it.
        Let's assume the ID passed is the ID of the ExecutablePipeline (compiled artifact).
        """
        # Accept both ExecutablePipeline IDs and VisualPipeline IDs (builder uses visual IDs).
        exec_stmt = select(ExecutablePipeline).where(ExecutablePipeline.id == pipeline_id)
        exec_result = await self.db.execute(exec_stmt)
        exec_pipeline = exec_result.scalar_one_or_none()

        if exec_pipeline:
            return {
                "id": str(exec_pipeline.id),
                "name": f"RAG Executable {exec_pipeline.id}",
                "resolved_type": "executable",
            }

        visual_stmt = select(VisualPipeline).where(
            VisualPipeline.id == pipeline_id,
            VisualPipeline.tenant_id == self.tenant_id,
            VisualPipeline.pipeline_type == PipelineType.RETRIEVAL,
        )
        visual_result = await self.db.execute(visual_stmt)
        visual_pipeline = visual_result.scalar_one_or_none()

        if not visual_pipeline:
            raise ResolutionError(f"RAG Pipeline {pipeline_id} not found or not executable")

        latest_exec_stmt = (
            select(ExecutablePipeline)
            .where(
                ExecutablePipeline.visual_pipeline_id == visual_pipeline.id,
                ExecutablePipeline.is_valid == True,
            )
            .order_by(ExecutablePipeline.version.desc())
            .limit(1)
        )
        latest_exec = (await self.db.execute(latest_exec_stmt)).scalar_one_or_none()
        if not latest_exec:
            raise ResolutionError(f"No executable pipeline found for visual pipeline {pipeline_id}")

        return {
            "id": str(visual_pipeline.id),
            "name": visual_pipeline.name,
            "resolved_type": "visual",
            "executable_id": str(latest_exec.id),
        }
