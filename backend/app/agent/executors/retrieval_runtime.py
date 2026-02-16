from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.rag import (
    ExecutablePipeline,
    PipelineJob,
    PipelineJobStatus,
    PipelineType,
    VisualPipeline,
)
from app.rag.pipeline.executor import PipelineExecutor as RAGPipelineExecutor


class RetrievalPipelineRuntime:
    """Shared retrieval-pipeline runtime for RAG nodes and retrieval tools."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self._db = db
        self._tenant_id = tenant_id

    async def resolve_executable_pipeline(self, pipeline_id: UUID) -> ExecutablePipeline:
        executable = (
            await self._db.execute(
                select(ExecutablePipeline).where(
                    ExecutablePipeline.id == pipeline_id,
                    ExecutablePipeline.tenant_id == self._tenant_id,
                    ExecutablePipeline.pipeline_type == PipelineType.RETRIEVAL,
                )
            )
        ).scalar_one_or_none()
        if executable is not None:
            return executable

        visual = (
            await self._db.execute(
                select(VisualPipeline).where(
                    VisualPipeline.id == pipeline_id,
                    VisualPipeline.tenant_id == self._tenant_id,
                    VisualPipeline.pipeline_type == PipelineType.RETRIEVAL,
                )
            )
        ).scalar_one_or_none()
        if visual is None:
            raise ValueError(f"Retrieval pipeline {pipeline_id} not found")

        executable = (
            await self._db.execute(
                select(ExecutablePipeline)
                .where(
                    ExecutablePipeline.visual_pipeline_id == visual.id,
                    ExecutablePipeline.tenant_id == self._tenant_id,
                    ExecutablePipeline.pipeline_type == PipelineType.RETRIEVAL,
                    ExecutablePipeline.is_valid == True,
                )
                .order_by(ExecutablePipeline.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if executable is not None:
            return executable

        executable = (
            await self._db.execute(
                select(ExecutablePipeline)
                .where(
                    ExecutablePipeline.visual_pipeline_id == visual.id,
                    ExecutablePipeline.tenant_id == self._tenant_id,
                    ExecutablePipeline.pipeline_type == PipelineType.RETRIEVAL,
                )
                .order_by(ExecutablePipeline.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if executable is None:
            raise ValueError(f"No executable retrieval pipeline found for {pipeline_id}")
        return executable

    async def run_query(
        self,
        *,
        pipeline_id: UUID,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[Any], PipelineJob]:
        executable = await self.resolve_executable_pipeline(pipeline_id)

        job = PipelineJob(
            id=uuid.uuid4(),
            tenant_id=self._tenant_id,
            executable_pipeline_id=executable.id,
            status=PipelineJobStatus.QUEUED,
            input_params={
                "text": query,
                "query": query,
                "top_k": int(top_k or 10),
                "filters": filters or {},
            },
            triggered_by=None,
        )
        self._db.add(job)
        await self._db.commit()

        executor = RAGPipelineExecutor(self._db)
        await executor.execute_job(job.id)

        await self._db.refresh(job)
        if job.status == PipelineJobStatus.FAILED:
            raise RuntimeError(f"Pipeline execution failed: {job.error_message}")

        return self.normalize_results(job.output), job

    @staticmethod
    def normalize_results(raw_results: Any) -> list[Any]:
        if isinstance(raw_results, list):
            return raw_results
        if isinstance(raw_results, dict) and "results" in raw_results:
            results = raw_results.get("results")
            return results if isinstance(results, list) else [results]
        return [raw_results] if raw_results else []
