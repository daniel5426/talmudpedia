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
    VisualPipeline,
)
from app.rag.pipeline.executor import PipelineExecutor as RAGPipelineExecutor


class PipelineToolRuntime:
    """Shared tenant-scoped runtime for tool-bound executable pipelines."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self._db = db
        self._tenant_id = tenant_id

    async def resolve_executable_pipeline(self, *, executable_pipeline_id: UUID | None = None, visual_pipeline_id: UUID | None = None) -> ExecutablePipeline:
        if executable_pipeline_id is not None:
            executable = (
                await self._db.execute(
                    select(ExecutablePipeline).where(
                        ExecutablePipeline.id == executable_pipeline_id,
                        ExecutablePipeline.tenant_id == self._tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if executable is None:
                raise ValueError(f"Executable pipeline {executable_pipeline_id} not found")
            return executable

        if visual_pipeline_id is None:
            raise ValueError("Pipeline runtime requires executable_pipeline_id or visual_pipeline_id")

        visual = (
            await self._db.execute(
                select(VisualPipeline).where(
                    VisualPipeline.id == visual_pipeline_id,
                    VisualPipeline.tenant_id == self._tenant_id,
                )
            )
        ).scalar_one_or_none()
        if visual is None:
            raise ValueError(f"Pipeline {visual_pipeline_id} not found")

        executable = (
            await self._db.execute(
                select(ExecutablePipeline)
                .where(
                    ExecutablePipeline.visual_pipeline_id == visual.id,
                    ExecutablePipeline.tenant_id == self._tenant_id,
                    ExecutablePipeline.is_valid == True,
                )
                .order_by(ExecutablePipeline.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if executable is None:
            raise ValueError(f"No executable pipeline found for {visual_pipeline_id}")
        return executable

    async def execute(self, *, executable_pipeline_id: UUID, input_params: dict[str, Any]) -> tuple[dict[str, Any], PipelineJob]:
        executable = await self.resolve_executable_pipeline(executable_pipeline_id=executable_pipeline_id)

        job = PipelineJob(
            id=uuid.uuid4(),
            tenant_id=self._tenant_id,
            executable_pipeline_id=executable.id,
            status=PipelineJobStatus.QUEUED,
            input_params=input_params or {},
            triggered_by=None,
        )
        self._db.add(job)
        await self._db.commit()

        executor = RAGPipelineExecutor(self._db)
        await executor.execute_job(job.id, artifact_queue_class="artifact_prod_interactive")

        await self._db.refresh(job)
        if job.status == PipelineJobStatus.FAILED:
            raise RuntimeError(f"Pipeline execution failed: {job.error_message}")

        output = job.output
        if isinstance(output, dict):
            return output, job
        return {"result": output}, job


class RetrievalPipelineRuntime:
    """Shared retrieval-pipeline runtime for RAG nodes and retrieval tools."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self._db = db
        self._tenant_id = tenant_id
        self._runtime = PipelineToolRuntime(db, tenant_id)

    async def resolve_executable_pipeline(self, pipeline_id: UUID) -> ExecutablePipeline:
        executable = (
            await self._db.execute(
                select(ExecutablePipeline).where(
                    ExecutablePipeline.id == pipeline_id,
                    ExecutablePipeline.tenant_id == self._tenant_id,
                    ExecutablePipeline.pipeline_type == "retrieval",
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
                    VisualPipeline.pipeline_type == "retrieval",
                )
            )
        ).scalar_one_or_none()
        if visual is None:
            raise ValueError(f"Retrieval pipeline {pipeline_id} not found")
        executable = await self._runtime.resolve_executable_pipeline(visual_pipeline_id=visual.id)
        if str(getattr(executable.pipeline_type, "value", executable.pipeline_type)) != "retrieval":
            raise ValueError(f"Pipeline {pipeline_id} is not a retrieval pipeline")
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
        await executor.execute_job(job.id, artifact_queue_class="artifact_prod_interactive")

        await self._db.refresh(job)
        if job.status == PipelineJobStatus.FAILED:
            raise RuntimeError(f"Pipeline execution failed: {job.error_message}")

        return self.normalize_results(job.output), job

    @staticmethod
    def normalize_results(raw_results: Any) -> list[Any]:
        if isinstance(raw_results, list):
            return raw_results
        if isinstance(raw_results, dict) and "final_output" in raw_results:
            return RetrievalPipelineRuntime.normalize_results(raw_results.get("final_output"))
        if isinstance(raw_results, dict) and "results" in raw_results:
            results = raw_results.get("results")
            return results if isinstance(results, list) else [results]
        return [raw_results] if raw_results else []
