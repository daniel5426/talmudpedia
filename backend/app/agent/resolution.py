import logging
from uuid import UUID
from typing import Optional, Dict, Any
from sqlalchemy import select, text, and_, or_
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import ToolRegistry
from app.db.postgres.models.rag import ExecutablePipeline, VisualPipeline, PipelineType

logger = logging.getLogger(__name__)

class ResolutionError(Exception):
    pass

class ComponentResolver:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

class ToolResolver(ComponentResolver):
    async def _has_artifact_columns(self) -> bool:
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'tool_registry'
                      AND column_name IN ('artifact_id', 'artifact_version')
                    """
                )
            )
            cols = {row[0] for row in result.all()}
            return "artifact_id" in cols and "artifact_version" in cols
        except Exception:
            # SQLite fallback
            try:
                result = await self.db.execute(text("PRAGMA table_info(tool_registry)"))
                cols = {row[1] for row in result.all()}
                return "artifact_id" in cols and "artifact_version" in cols
            except Exception:
                return False

    async def resolve(self, tool_id: UUID, require_published: bool = False) -> Dict[str, Any]:
        """
        Verify tool exists and return minimal execution metadata.
        """
        tool = None
        try:
            if await self._has_artifact_columns():
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
