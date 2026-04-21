from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.postgres.models.rag import KnowledgeStore, RetrievalPolicy, StorageBackend
from app.rag.pipeline.operator_executor import ExecutionContext, ExecutorRegistry, KnowledgeStoreSinkExecutor, OperatorInput, VectorSearchExecutor
from app.rag.pipeline.registry import OperatorRegistry


def _spec(operator_id: str):
    spec = OperatorRegistry.get_instance().get(operator_id)
    assert spec is not None
    return spec


@pytest.mark.asyncio
async def test_catalog_operator_format_normalizer_now_has_executor_implementation():
    spec = _spec("format_normalizer")
    executor = ExecutorRegistry.create_executor(spec)
    assert executor.operator_id == "format_normalizer"


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_vector_search_fails_when_query_has_neither_values_nor_text(
    db_session, test_tenant_id, test_user_id, run_prefix
):
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-missing-query-store",
        description="missing vector failure",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_missing_query"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    executor = VectorSearchExecutor(_spec("vector_search"))
    with pytest.raises(ValueError, match="No query vector found for search"):
        await executor.execute(
            OperatorInput(data={"filters": {"kind": "campaign"}}),
            ExecutionContext(
                step_id="search",
                config={"knowledge_store_id": str(store.id)},
                db=db_session,
            ),
        )


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_knowledge_store_sink_raises_when_backend_reports_zero_upserts(
    db_session, test_tenant_id, test_user_id, run_prefix, monkeypatch
):
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-zero-upsert-store",
        description="zero upsert failure",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_zero_upsert"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    class FakeAdapter:
        async def upsert(self, records, namespace):
            del records, namespace
            return 0

    monkeypatch.setattr("app.rag.adapters.create_adapter", lambda backend, config: FakeAdapter())
    executor = KnowledgeStoreSinkExecutor(_spec("knowledge_store_sink"))

    with pytest.raises(RuntimeError, match="Vector upsert completed with 0 records"):
        await executor.execute(
            OperatorInput(data={"id": str(uuid4()), "text": "alpha", "values": [1.0, 0.0], "metadata": {}}),
            ExecutionContext(
                step_id="sink",
                config={"knowledge_store_id": str(store.id)},
                db=db_session,
            ),
        )


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_vector_search_applies_similarity_threshold_after_backend_results(
    db_session, test_tenant_id, test_user_id, run_prefix, monkeypatch
):
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-threshold-store",
        description="threshold filtering",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_threshold"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    class FakeAdapter:
        async def query(self, vector, top_k, filters, namespace):
            del vector, top_k, filters, namespace
            return [
                SimpleNamespace(model_dump=lambda: {"id": "drop-me", "score": 0.2, "text": "low", "metadata": {}} , score=0.2),
                SimpleNamespace(model_dump=lambda: {"id": "keep-me", "score": 0.9, "text": "high", "metadata": {}} , score=0.9),
            ]

    monkeypatch.setattr("app.rag.adapters.create_adapter", lambda backend, config: FakeAdapter())
    executor = VectorSearchExecutor(_spec("vector_search"))
    result = await executor.execute(
        OperatorInput(data={"values": [0.1, 0.2], "text": "hello"}),
        ExecutionContext(
            step_id="search",
            config={"knowledge_store_id": str(store.id), "similarity_threshold": 0.5},
            db=db_session,
        ),
    )

    assert result.success is True
    assert [row["id"] for row in result.data] == ["keep-me"]
