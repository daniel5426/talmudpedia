from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.postgres.models.rag import KnowledgeStore, RetrievalPolicy, StorageBackend
from app.rag.pipeline.operator_executor import (
    ClassifierExecutor,
    ExecutionContext,
    KnowledgeStoreSinkExecutor,
    LLMTransformExecutor,
    OperatorInput,
    QueryInputExecutor,
    RerankerExecutor,
    TransformExecutor,
    WebCrawlerExecutor,
    FormatNormalizerExecutor,
)
from app.rag.pipeline.registry import OperatorRegistry


def _spec(operator_id: str):
    spec = OperatorRegistry.get_instance().get(operator_id)
    assert spec is not None
    return spec


@pytest.mark.asyncio
async def test_web_crawler_spec_type_checks_present_config_values_but_not_runtime_required_fields():
    spec = _spec("web_crawler")

    assert spec.validate_config({}) == []
    assert "Field 'max_depth' must be an integer" in spec.validate_config(
        {"start_urls": "https://example.com", "max_depth": "deep"}
    )
    assert "Field 'respect_robots_txt' must be a boolean" in spec.validate_config(
        {"start_urls": "https://example.com", "respect_robots_txt": "yes"}
    )


@pytest.mark.asyncio
async def test_query_input_executor_normalizes_query_alias_and_nested_runtime_fields():
    executor = QueryInputExecutor(_spec("query_input"))

    result = await executor.execute(
        OperatorInput(
            data={
                "query": "hello retrieval",
                "input": {"top_k": 7, "filters": {"kind": "campaign"}},
            }
        ),
        ExecutionContext(step_id="input", config={}),
    )

    assert result.success is True
    assert result.data["text"] == "hello retrieval"
    assert result.data["top_k"] == 7
    assert result.data["filters"] == {"kind": "campaign"}
    assert result.metadata["query_text"] == "hello retrieval"


@pytest.mark.asyncio
async def test_format_normalizer_executor_normalizes_whitespace_unicode_and_lowercase():
    executor = FormatNormalizerExecutor(_spec("format_normalizer"))

    result = await executor.execute(
        OperatorInput(data=[{"id": "doc-1", "text": "A\u0301   B\n\nC"}]),
        ExecutionContext(
            step_id="normalize",
            config={"normalize_whitespace": True, "normalize_unicode": True, "lowercase": True},
        ),
    )

    assert result.success is True
    assert result.data[0]["text"] == "á b c"


@pytest.mark.asyncio
async def test_transform_executor_can_filter_rename_and_dedupe_records():
    executor = TransformExecutor(_spec("transform"))

    result = await executor.execute(
        OperatorInput(
            data=[
                {"id": "1", "kind": "keep", "title": "One"},
                {"id": "1", "kind": "keep", "title": "One duplicate"},
                {"id": "2", "kind": "drop", "title": "Two"},
            ]
        ),
        ExecutionContext(
            step_id="transform",
            config={
                "dedupe_by": "id",
                "filter_field": "kind",
                "filter_equals": "keep",
                "rename_fields": {"title": "text"},
                "drop_fields": "kind",
            },
        ),
    )

    assert result.success is True
    assert result.data == [{"id": "1", "text": "One"}]


@pytest.mark.asyncio
async def test_classifier_executor_writes_classification_metadata():
    executor = ClassifierExecutor(_spec("classifier"))

    result = await executor.execute(
        OperatorInput(data=[{"id": "doc-1", "text": "finance report for the quarterly budget"}]),
        ExecutionContext(step_id="classify", config={"categories": "finance,legal,marketing"}),
    )

    assert result.success is True
    assert result.data[0]["metadata"]["classification"] == "finance"


@pytest.mark.asyncio
async def test_llm_executor_requires_db_context():
    executor = LLMTransformExecutor(_spec("llm"))

    with pytest.raises(ValueError, match="Database session is required"):
        await executor.execute(
            OperatorInput(data=[{"id": "doc-1", "text": "hello"}]),
            ExecutionContext(
                step_id="llm",
                config={"model_id": "model-1", "prompt_template": "Rewrite: {text}"},
            ),
        )


@pytest.mark.asyncio
async def test_reranker_executor_uses_query_metadata_to_reorder_results():
    executor = RerankerExecutor(_spec("reranker"))

    result = await executor.execute(
        OperatorInput(
            data=[
                {"id": "a", "score": 0.8, "text": "totally unrelated"},
                {"id": "b", "score": 0.7, "text": "hello keyword world"},
            ],
            metadata={"query_text": "hello keyword"},
        ),
        ExecutionContext(step_id="rerank", config={"top_k": 2}),
    )

    assert result.success is True
    assert [item["id"] for item in result.data] == ["b", "a"]


@pytest.mark.asyncio
async def test_web_crawler_executor_rejects_invalid_start_urls_before_provider_call():
    executor = WebCrawlerExecutor(_spec("web_crawler"))

    with pytest.raises(ValueError, match="Invalid start_urls"):
        await executor.execute(
            OperatorInput(data=None),
            ExecutionContext(
                step_id="source",
                config={"start_urls": "notaurl, https://example.com"},
            ),
        )


@pytest.mark.asyncio
async def test_web_crawler_executor_accepts_list_start_urls(monkeypatch):
    executor = WebCrawlerExecutor(_spec("web_crawler"))
    captured = {}

    class FakeProvider:
        async def crawl(self, request):
            captured["request"] = request
            return [SimpleNamespace(model_dump=lambda: {"id": "doc-1", "content": "ok"})]

    monkeypatch.setattr(executor, "_build_provider", lambda: FakeProvider())
    result = await executor.execute(
        OperatorInput(data=None),
        ExecutionContext(
            step_id="source",
            config={
                "start_urls": ["https://example.com/a", "https://example.com/b"],
                "content_preference": "html",
                "page_timeout_ms": 1234,
            },
        ),
    )

    assert result.success is True
    assert captured["request"].start_urls == ["https://example.com/a", "https://example.com/b"]
    assert captured["request"].content_preference == "html"
    assert result.data == [{"id": "doc-1", "content": "ok"}]


@pytest.mark.asyncio
async def test_knowledge_store_sink_rejects_documents_without_vectors(db_session, test_tenant_id, test_user_id, run_prefix):
    executor = KnowledgeStoreSinkExecutor(_spec("knowledge_store_sink"))
    store = KnowledgeStore(
        organization_id=test_tenant_id,
        name=f"{run_prefix}-empty-vector-store",
        description="empty vector validation",
        embedding_model_id="manual-vector-test",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"{run_prefix}_empty_vectors"},
        created_by=test_user_id,
    )
    db_session.add(store)
    await db_session.commit()

    with pytest.raises(ValueError, match="No valid vectors to upsert"):
        await executor.execute(
            OperatorInput(
                data=[
                    {"id": str(uuid4()), "text": "no vector", "metadata": {"kind": "empty"}},
                    {"id": str(uuid4()), "text": "also no vector", "values": []},
                ]
            ),
            ExecutionContext(
                step_id="sink",
                config={"knowledge_store_id": str(store.id)},
                db=db_session,
            ),
        )
