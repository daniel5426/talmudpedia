from __future__ import annotations

import asyncio
import contextlib
import os
import time
import uuid
from pathlib import Path
from uuid import UUID

import pytest
from dotenv import load_dotenv
from sqlalchemy import select

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, User
from app.db.postgres.models.rag import ExecutablePipeline, PipelineJob, PipelineJobStatus
from app.db.postgres.models.registry import ModelRegistry
from app.rag.pipeline.executor import PipelineExecutor
from app.services.model_resolver import ModelResolver
from tests.agent_builder_helpers import cleanup_retrieval_setup, create_retrieval_setup


def _load_live_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env.test", override=True)
    os.environ["TALMUDPEDIA_ENV_PROFILE"] = "test"
    os.environ["TALMUDPEDIA_ENV_FILE"] = str(backend_dir / ".env.test")


def _require_enabled() -> None:
    _load_live_env()
    if os.getenv("RAG_EXTREME_ENABLE_LIVE_EMBEDDING_TESTS") != "1":
        pytest.skip("Set RAG_EXTREME_ENABLE_LIVE_EMBEDDING_TESTS=1 to run deep live retrieval diagnostics.")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for deep live retrieval diagnostics.")


async def _resolve_tenant_context(db_session) -> tuple[UUID, UUID]:
    email = os.getenv("TEST_TENANT_EMAIL")
    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None, f"Expected TEST_TENANT_EMAIL user to exist: {email}"
    membership = await db_session.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.status == MembershipStatus.active,
        )
    )
    assert membership is not None, f"Expected active membership for {email}"
    return membership.organization_id, user.id


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_live_embedding_resolution_and_call_complete_within_budget(db_session):
    _require_enabled()

    organization_id, _user_id = await _resolve_tenant_context(db_session)
    model_id = os.getenv("TEST_EMBED_MODEL_SLUG")
    assert model_id, "TEST_EMBED_MODEL_SLUG must be set"

    model = await db_session.get(ModelRegistry, model_id)
    assert model is not None

    resolver = ModelResolver(db_session, organization_id)

    start = time.perf_counter()
    embedder = await asyncio.wait_for(resolver.resolve_embedding(model_id), timeout=15)
    resolve_s = time.perf_counter() - start

    start = time.perf_counter()
    embedded = await asyncio.wait_for(
        embedder.embed("rag extreme live embedding diagnostic"),
        timeout=30,
    )
    embed_s = time.perf_counter() - start

    assert embedded.values
    assert len(embedded.values) > 100
    assert resolve_s < 15
    assert embed_s < 30


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_live_retrieval_pipeline_job_completes_within_budget(db_session):
    _require_enabled()

    organization_id, user_id = await _resolve_tenant_context(db_session)
    run_prefix = f"diag-{uuid.uuid4().hex[:8]}"
    pipeline_id, _store_id, collection_name = await create_retrieval_setup(
        db_session, organization_id, user_id, run_prefix
    )

    try:
        executable = await db_session.scalar(
            select(ExecutablePipeline).where(ExecutablePipeline.visual_pipeline_id == UUID(pipeline_id))
        )
        assert executable is not None

        job = PipelineJob(
            organization_id=organization_id,
            executable_pipeline_id=executable.id,
            status=PipelineJobStatus.QUEUED,
            input_params={"text": "hello retrieval", "top_k": 3},
            triggered_by=user_id,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        start = time.perf_counter()
        await asyncio.wait_for(
            PipelineExecutor(db_session).execute_job(job.id, artifact_queue_class="artifact_prod_interactive"),
            timeout=45,
        )
        runtime_s = time.perf_counter() - start
        await db_session.refresh(job)

        if job.status != PipelineJobStatus.COMPLETED:
            pytest.fail(f"Live retrieval pipeline job failed: {job.error_message}")
        assert job.status == PipelineJobStatus.COMPLETED
        assert isinstance(job.output, dict)
        assert job.output.get("results")
        assert runtime_s < 45
    finally:
        with contextlib.suppress(Exception):
            await db_session.rollback()
        with contextlib.suppress(Exception):
            await cleanup_retrieval_setup(db_session, pipeline_id, _store_id, collection_name)
