from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.postgres.models.rag import KnowledgeStore, RetrievalPolicy, StorageBackend
from app.rag.adapters import SearchResult
from app.rag.pipeline.operator_executor import (
    ExecutionContext,
    KnowledgeStoreSinkExecutor,
    OperatorInput,
    VectorSearchExecutor,
)
from app.rag.pipeline.registry import OperatorRegistry


def _spec(operator_id: str):
    spec = OperatorRegistry.get_instance().get(operator_id)
    assert spec is not None
    return spec


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_knowledge_store_sink_uses_store_namespace_when_runtime_namespace_missing(
    db_session, test_tenant_id, test_user_id, run_prefix, monkeypatch
):
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-namespace-store",
        description="namespace fallback",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_fallback", "namespace": "store-default"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    captured = {}

    class FakeAdapter:
        async def upsert(self, records, namespace):
            captured["namespace"] = namespace
            captured["count"] = len(records)
            return len(records)

    monkeypatch.setattr("app.rag.adapters.create_adapter", lambda backend, config: FakeAdapter())
    executor = KnowledgeStoreSinkExecutor(_spec("knowledge_store_sink"))
    result = await executor.execute(
        OperatorInput(
            data=[
                {"id": str(uuid4()), "text": "alpha", "values": [1.0, 0.0], "metadata": {"kind": "a"}},
                {"id": str(uuid4()), "text": "beta", "values": [0.0, 1.0], "metadata": {"kind": "b"}},
            ]
        ),
        ExecutionContext(
            step_id="sink",
            config={"knowledge_store_id": str(store.id)},
            db=db_session,
        ),
    )

    await db_session.refresh(store)
    assert result.success is True
    assert result.data["debug"]["namespace"] == "store-default"
    assert captured["namespace"] == "store-default"
    assert store.chunk_count == 2


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_knowledge_store_sink_runtime_namespace_overrides_store_namespace(
    db_session, test_tenant_id, test_user_id, run_prefix, monkeypatch
):
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-namespace-override-store",
        description="namespace override",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_override", "namespace": "store-default"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    captured = {}

    class FakeAdapter:
        async def upsert(self, records, namespace):
            captured["namespace"] = namespace
            return len(records)

    monkeypatch.setattr("app.rag.adapters.create_adapter", lambda backend, config: FakeAdapter())
    executor = KnowledgeStoreSinkExecutor(_spec("knowledge_store_sink"))
    result = await executor.execute(
        OperatorInput(data={"id": str(uuid4()), "text": "alpha", "values": [1.0, 0.0], "metadata": {}}),
        ExecutionContext(
            step_id="sink",
            config={"knowledge_store_id": str(store.id), "namespace": "runtime-ns"},
            db=db_session,
        ),
    )

    assert result.success is True
    assert result.data["debug"]["namespace"] == "runtime-ns"
    assert captured["namespace"] == "runtime-ns"


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_vector_search_prefers_runtime_top_k_and_namespace_override(
    db_session, test_tenant_id, test_user_id, run_prefix, monkeypatch
):
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-search-store",
        description="search override",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_search", "namespace": "store-default"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    captured = {}

    class FakeAdapter:
        async def query(self, vector, top_k, filters, namespace):
            captured["vector"] = vector
            captured["top_k"] = top_k
            captured["filters"] = filters
            captured["namespace"] = namespace
            return [SearchResult(id="doc-1", score=0.9, text="hello", metadata={"kind": "campaign"})]

    monkeypatch.setattr("app.rag.adapters.create_adapter", lambda backend, config: FakeAdapter())
    executor = VectorSearchExecutor(_spec("vector_search"))
    result = await executor.execute(
        OperatorInput(
            data={
                "values": [0.1, 0.2],
                "top_k": 3,
                "filters": {"kind": "campaign"},
                "text": "hello",
            }
        ),
        ExecutionContext(
            step_id="search",
            config={"knowledge_store_id": str(store.id), "top_k": 10, "namespace": "runtime-ns"},
            db=db_session,
        ),
    )

    assert result.success is True
    assert captured == {
        "vector": [0.1, 0.2],
        "top_k": 3,
        "filters": {"kind": "campaign"},
        "namespace": "runtime-ns",
    }
    assert result.data[0]["id"] == "doc-1"
