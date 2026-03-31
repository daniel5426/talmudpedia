from __future__ import annotations

import uuid
from uuid import uuid4

import pytest

from app.db.postgres.models.rag import KnowledgeStore, RetrievalPolicy, StorageBackend
from app.rag.pipeline.operator_executor import (
    ExecutionContext,
    KnowledgeStoreSinkExecutor,
    OperatorInput,
    VectorSearchExecutor,
)
from app.rag.pipeline.registry import OperatorRegistry, OperatorSpec
from app.services.retrieval_service import RetrievalService


def _sink_spec() -> OperatorSpec:
    spec = OperatorRegistry.get_instance().get("knowledge_store_sink")
    assert spec is not None
    return spec


def _vector_search_spec() -> OperatorSpec:
    spec = OperatorRegistry.get_instance().get("vector_search")
    assert spec is not None
    return spec


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_local_knowledge_store_sink_and_vector_search_roundtrip(db_session, test_tenant_id, test_user_id, run_prefix):
    collection_name = f"{run_prefix}_ingest_roundtrip"
    store = KnowledgeStore(
        tenant_id=test_tenant_id,
        name=f"{run_prefix}-ingest-store",
        description="local ingestion/storage campaign test",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": collection_name},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    vectors = [
        {
            "id": f"{run_prefix}-v1",
            "text": "alpha chunk",
            "values": [0.91, 0.02, 0.03, 0.04],
            "metadata": {"kind": "alpha", "rank": 1},
        },
        {
            "id": f"{run_prefix}-v2",
            "text": "beta chunk",
            "values": [0.05, 0.93, 0.02, 0.01],
            "metadata": {"kind": "beta", "rank": 2},
        },
    ]

    try:
        sink = KnowledgeStoreSinkExecutor(_sink_spec())
        sink_result = await sink.execute(
            OperatorInput(data=vectors),
            ExecutionContext(
                tenant_id=str(test_tenant_id),
                pipeline_id=str(uuid4()),
                job_id=str(uuid4()),
                step_id="sink",
                config={"knowledge_store_id": str(store.id), "namespace": "campaign"},
                db=db_session,
            ),
        )

        assert sink_result.success is True
        assert sink_result.data["upsert_count"] == 2
        await db_session.refresh(store)
        assert store.chunk_count == 2

        search = VectorSearchExecutor(_vector_search_spec())
        search_result = await search.execute(
            OperatorInput(data={"values": [0.91, 0.02, 0.03, 0.04], "filters": {"kind": "alpha"}}),
            ExecutionContext(
                tenant_id=str(test_tenant_id),
                pipeline_id=str(uuid4()),
                job_id=str(uuid4()),
                step_id="search",
                config={"knowledge_store_id": str(store.id), "top_k": 2, "namespace": "campaign"},
                db=db_session,
            ),
        )

        assert search_result.success is True
        assert search_result.data
        assert search_result.data[0]["id"] == f"{run_prefix}-v1"
        assert search_result.data[0]["text"] == "alpha chunk"
    finally:
        from app.rag.providers.vector_store.pgvector import PgvectorVectorStore

        await db_session.delete(store)
        await db_session.commit()
        await PgvectorVectorStore().delete_index(collection_name)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_local_retrieval_service_query_multiple_stores_merges_results(db_session, test_tenant_id, test_user_id, run_prefix, monkeypatch):
    store_a = KnowledgeStore(
        tenant_id=test_tenant_id,
        name=f"{run_prefix}-ks-a",
        description="store a",
        embedding_model_id="manual-a",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_a"},
        created_by=test_user_id,
    )
    store_b = KnowledgeStore(
        tenant_id=test_tenant_id,
        name=f"{run_prefix}-ks-b",
        description="store b",
        embedding_model_id="manual-b",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_b"},
        created_by=test_user_id,
    )
    db_session.add_all([store_a, store_b])
    await db_session.commit()
    await db_session.refresh(store_a)
    await db_session.refresh(store_b)

    service = RetrievalService(db_session)

    from app.services.retrieval_service import RetrievalResult

    async def fake_query_impl(store_id, query, top_k=10, filters=None, policy_override=None, namespace=None, policy_snapshot=None):
        del query, top_k, filters, policy_override, namespace, policy_snapshot
        if store_id == store_a.id:
            return [
                RetrievalResult(
                    id="a-1",
                    score=0.61,
                    text="alpha",
                    metadata={"store": "a"},
                    knowledge_store_id=store_a.id,
                )
            ]
        return [
            RetrievalResult(
                id="b-1",
                score=0.82,
                text="beta",
                metadata={"store": "b"},
                knowledge_store_id=store_b.id,
            )
        ]

    monkeypatch.setattr(service, "query", fake_query_impl)
    merged = await service.query_multiple_stores([store_a.id, store_b.id], "hello", top_k=2)
    assert [item.id for item in merged] == ["b-1", "a-1"]

    await db_session.delete(store_a)
    await db_session.delete(store_b)
    await db_session.commit()
