import logging
from uuid import UUID
from typing import Optional, Dict, Any
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import ToolRegistry
from app.db.postgres.models.rag import ExecutablePipeline

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

    async def resolve(self, tool_id: UUID) -> Dict[str, Any]:
        """
        Verify tool exists and return minimal execution metadata.
        """
        tool = None
        try:
            if await self._has_artifact_columns():
                stmt = select(ToolRegistry).where(ToolRegistry.id == tool_id)
                # Note: We should assume tenant check is needed, or allow system tools (tenant_id=None)
                # The existing query in standard executors didn't check tenant carefully enough
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
             
        impl_type = getattr(tool, "implementation_type", None)
        if hasattr(impl_type, "value"):
            impl_type = impl_type.value
        if not impl_type:
            config_schema = getattr(tool, "config_schema", {}) or {}
            impl_type = (config_schema.get("implementation") or {}).get("type", "internal")

        return {
            "id": str(tool.id),
            "name": tool.name,
            "implementation_type": impl_type
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
        # In reality, users pick a "Pipeline" and we run the "Latest Executable".
        # Or they pick a specific Version.
        # Let's verify against ExecutablePipeline for now as that's what executors used.
        stmt = select(ExecutablePipeline).where(ExecutablePipeline.id == pipeline_id)
        result = await self.db.execute(stmt)
        pipeline = result.scalar_one_or_none()
        
        if not pipeline:
             # Try generic pipeline and see if we can resolve latest?
             # For strictness, we require the ID to be resolvable to a specific executable 
             # OR we resolve it now.
             raise ResolutionError(f"RAG Pipeline {pipeline_id} not found or not executable")
             
        return {
            "id": str(pipeline.id),
            "name": f"RAG Pipeline {pipeline.id}"
        }
