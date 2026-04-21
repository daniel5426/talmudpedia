from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.rag import (
    ExecutablePipeline,
    PipelineJob,
    PipelineJobStatus,
    PipelineStepExecution,
    PipelineStepStatus,
    PipelineType,
    VisualPipeline,
)
from app.rag.pipeline.executor import PipelineExecutor


async def _seed_tenant_context(db_session):
    tenant = Organization(id=uuid.uuid4(), name="RAG Executor Organization", slug=f"rag-exec-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"rag-exec-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    return tenant, user


async def _create_executable(db_session, organization_id, user_id, dag):
    visual = VisualPipeline(
        id=uuid.uuid4(),
        organization_id=organization_id,
        name="Executor Campaign Pipeline",
        description=None,
        nodes=[],
        edges=[],
        pipeline_type=PipelineType.RETRIEVAL,
        version=1,
        is_published=False,
        created_by=user_id,
    )
    executable = ExecutablePipeline(
        id=uuid.uuid4(),
        visual_pipeline_id=visual.id,
        organization_id=organization_id,
        version=1,
        compiled_graph={"dag": dag},
        pipeline_type=PipelineType.RETRIEVAL,
        is_valid=True,
        compiled_by=user_id,
    )
    db_session.add_all([visual, executable])
    await db_session.commit()
    return executable


@pytest.mark.asyncio
async def test_pipeline_executor_persists_step_inputs_outputs_and_terminal_payload(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    executable = await _create_executable(
        db_session,
        tenant.id,
        user.id,
        [
            {"step_id": "output", "operator": "retrieval_result", "config": {}, "depends_on": []},
        ],
    )
    job = PipelineJob(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        executable_pipeline_id=executable.id,
        status=PipelineJobStatus.QUEUED,
        input_params=[{"id": "doc-1", "text": "hello persistence"}],
        triggered_by=user.id,
    )
    db_session.add(job)
    await db_session.commit()

    await PipelineExecutor(db_session).execute_job(job.id)
    await db_session.refresh(job)

    steps = (
        await db_session.execute(
            select(PipelineStepExecution)
            .where(PipelineStepExecution.job_id == job.id)
            .order_by(PipelineStepExecution.execution_order.asc())
        )
    ).scalars().all()

    assert job.status == PipelineJobStatus.COMPLETED
    assert job.output["final_output"] == [{"id": "doc-1", "text": "hello persistence"}]
    assert job.output["results"] == [{"id": "doc-1", "text": "hello persistence"}]
    assert [step.status for step in steps] == [PipelineStepStatus.COMPLETED]
    assert steps[0].input_data == [{"id": "doc-1", "text": "hello persistence"}]
    assert steps[0].output_data == [{"id": "doc-1", "text": "hello persistence"}]
    assert job.started_at is not None
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_pipeline_executor_marks_job_failed_and_persists_step_error(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    executable = await _create_executable(
        db_session,
        tenant.id,
        user.id,
        [
            {"step_id": "input", "operator": "query_input", "config": {}, "depends_on": []},
            {"step_id": "search", "operator": "vector_search", "config": {}, "depends_on": ["input"]},
        ],
    )
    job = PipelineJob(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        executable_pipeline_id=executable.id,
        status=PipelineJobStatus.QUEUED,
        input_params={"text": "hello failure"},
        triggered_by=user.id,
    )
    db_session.add(job)
    await db_session.commit()

    await PipelineExecutor(db_session).execute_job(job.id)
    await db_session.refresh(job)

    steps = (
        await db_session.execute(
            select(PipelineStepExecution)
            .where(PipelineStepExecution.job_id == job.id)
            .order_by(PipelineStepExecution.execution_order.asc())
        )
    ).scalars().all()

    assert job.status == PipelineJobStatus.FAILED
    assert "index_name is required for search" in (job.error_message or "")
    assert [step.status for step in steps] == [PipelineStepStatus.COMPLETED, PipelineStepStatus.FAILED]
    assert "index_name is required for search" in (steps[1].error_message or "")
    assert steps[1].input_data["text"] == "hello failure"
    assert job.completed_at is not None
