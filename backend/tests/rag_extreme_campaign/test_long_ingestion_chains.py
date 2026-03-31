from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.rag import (
    ExecutablePipeline,
    KnowledgeStore,
    PipelineJob,
    PipelineJobStatus,
    PipelineStepExecution,
    PipelineStepStatus,
    PipelineType,
    RetrievalPolicy,
    StorageBackend,
    VisualPipeline,
)
from app.rag.pipeline.compiler import PipelineCompiler
from app.rag.pipeline.executor import PipelineExecutor


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="RAG Ingestion Tenant", slug=f"rag-ingest-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"rag-ingest-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="RAG Ingestion Org",
        slug=f"rag-ingest-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _build_long_ingestion_pipeline(tenant_id, store_id):
    return VisualPipeline(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Long Ingestion Chain",
        description=None,
        pipeline_type=PipelineType.INGESTION,
        version=1,
        is_published=False,
        nodes=[
            {"id": "crawl", "category": "source", "operator": "web_crawler", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "pii", "category": "normalization", "operator": "pii_redactor", "position": {"x": 1, "y": 0}, "config": {"replacement_text": "[MASKED]"}},
            {"id": "meta", "category": "enrichment", "operator": "metadata_extractor", "position": {"x": 2, "y": 0}, "config": {}},
            {"id": "chunk", "category": "chunking", "operator": "chunker", "position": {"x": 3, "y": 0}, "config": {"strategy": "recursive", "chunk_size": 100, "chunk_overlap": 0}},
            {"id": "embed", "category": "embedding", "operator": "model_embedder", "position": {"x": 4, "y": 0}, "config": {"model_id": "fake-embedding-model"}},
            {"id": "sink", "category": "storage", "operator": "knowledge_store_sink", "position": {"x": 5, "y": 0}, "config": {"knowledge_store_id": str(store_id), "namespace": "campaign"}},
        ],
        edges=[
            {"id": "e1", "source": "crawl", "target": "pii"},
            {"id": "e2", "source": "pii", "target": "meta"},
            {"id": "e3", "source": "meta", "target": "chunk"},
            {"id": "e4", "source": "chunk", "target": "embed"},
            {"id": "e5", "source": "embed", "target": "sink"},
        ],
    )


@pytest.mark.asyncio
async def test_long_ingestion_chain_executes_end_to_end_with_patched_dependencies(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    store = KnowledgeStore(
        tenant_id=tenant.id,
        name="Long Chain Store",
        description="campaign store",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"long_chain_{uuid.uuid4().hex[:8]}"},
        created_by=user.id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    pipeline = _build_long_ingestion_pipeline(tenant.id, store.id)
    compiled = PipelineCompiler().compile(pipeline, compiled_by=str(user.id), tenant_id=str(tenant.id))
    assert compiled.success is True

    visual = VisualPipeline(
        id=pipeline.id,
        tenant_id=tenant.id,
        name=pipeline.name,
        description=pipeline.description,
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        pipeline_type=pipeline.pipeline_type,
        version=pipeline.version,
        is_published=False,
        created_by=user.id,
    )
    executable = ExecutablePipeline(
        id=uuid.uuid4(),
        visual_pipeline_id=visual.id,
        tenant_id=tenant.id,
        version=1,
        compiled_graph=compiled.executable_pipeline.model_dump(mode="json"),
        pipeline_type=PipelineType.INGESTION,
        is_valid=True,
        compiled_by=user.id,
    )
    job = PipelineJob(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        executable_pipeline_id=executable.id,
        status=PipelineJobStatus.QUEUED,
        input_params={"start_urls": ["https://example.com/doc"]},
        triggered_by=user.id,
    )
    db_session.add_all([visual, executable, job])
    await db_session.commit()

    captured = {}

    class FakeCrawler:
        async def crawl(self, request):
            captured["crawl_request"] = request
            return [
                SimpleNamespace(
                    model_dump=lambda: {
                        "id": "doc-1",
                        "text": "Top Title\nContact me at person@example.com on 2026-03-30.",
                        "metadata": {"source": "crawler"},
                    }
                )
            ]

    class FakeEmbeddingResult:
        def __init__(self, values):
            self.values = values

    class FakeEmbedder:
        async def embed_batch(self, texts):
            captured["embedded_texts"] = list(texts)
            return [FakeEmbeddingResult([float(index + 1), 0.5, 0.25]) for index, _ in enumerate(texts)]

    class FakeModelResolver:
        def __init__(self, db, tenant_id):
            del db, tenant_id

        async def resolve_embedding(self, model_id):
            captured["model_id"] = model_id
            return FakeEmbedder()

    class FakeAdapter:
        async def upsert(self, records, namespace):
            captured["upsert_namespace"] = namespace
            captured["upsert_count"] = len(records)
            captured["upsert_texts"] = [record.text for record in records]
            return len(records)

    monkeypatch.setattr("app.rag.pipeline.operator_executor.WebCrawlerExecutor._build_provider", lambda self: FakeCrawler())
    monkeypatch.setattr("app.rag.pipeline.operator_executor.ModelResolver", FakeModelResolver, raising=False)
    monkeypatch.setattr("app.services.model_resolver.ModelResolver", FakeModelResolver)
    monkeypatch.setattr("app.rag.adapters.create_adapter", lambda backend, config: FakeAdapter())

    await PipelineExecutor(db_session).execute_job(job.id)
    await db_session.refresh(job)
    await db_session.refresh(store)

    steps = (
        await db_session.execute(
            select(PipelineStepExecution)
            .where(PipelineStepExecution.job_id == job.id)
            .order_by(PipelineStepExecution.execution_order.asc())
        )
    ).scalars().all()

    assert job.status == PipelineJobStatus.COMPLETED
    assert [step.step_id for step in steps] == ["crawl", "pii", "meta", "chunk", "embed", "sink"]
    assert all(step.status == PipelineStepStatus.COMPLETED for step in steps)
    assert captured["crawl_request"].start_urls == ["https://example.com/doc"]
    assert captured["model_id"] == "fake-embedding-model"
    assert captured["upsert_namespace"] == "campaign"
    assert captured["upsert_count"] >= 1
    assert any("[MASKED]" in text for text in captured["upsert_texts"])
    assert store.chunk_count == captured["upsert_count"]
