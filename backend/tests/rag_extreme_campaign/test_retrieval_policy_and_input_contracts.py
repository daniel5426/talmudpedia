from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.routers.rag_pipelines import PipelineInputSchemaBuilder, PipelineInputValidator
from app.rag.adapters import SearchResult
from app.rag.pipeline.registry import OperatorRegistry
from app.rag.pipeline.input_storage import PipelineInputStorage
from app.services.retrieval_service import RetrievalResult, RetrievalService


def _retrieval_dag() -> list[dict]:
    return [
        {
            "step_id": "input",
            "operator": "query_input",
            "config": {},
            "depends_on": [],
        },
        {
            "step_id": "embed",
            "operator": "model_embedder",
            "config": {"model_id": "model-1"},
            "depends_on": ["input"],
        },
        {
            "step_id": "search",
            "operator": "vector_search",
            "config": {"knowledge_store_id": "ks-1", "top_k": 3},
            "depends_on": ["embed"],
        },
    ]


@pytest.mark.asyncio
async def test_pipeline_input_schema_builder_exposes_only_source_step_fields():
    schema = PipelineInputSchemaBuilder(
        _retrieval_dag(),
        OperatorRegistry.get_instance(),
        organization_id=None,
    ).build()

    assert [step.step_id for step in schema.steps] == ["input"]
    assert schema.steps[0].operator_id == "query_input"
    field_names = {field.name for field in schema.steps[0].fields}
    assert "text" in field_names
    assert "top_k" in field_names


@pytest.mark.asyncio
async def test_pipeline_input_validator_accepts_query_top_k_runtime_field():
    validator = PipelineInputValidator(
        _retrieval_dag(),
        OperatorRegistry.get_instance(),
        organization_id=None,
        storage=PipelineInputStorage(),
    )

    normalized, errors = validator.validate({"text": "hello retrieval", "top_k": 5})
    assert normalized == {"input": {"text": "hello retrieval", "top_k": 5}}
    assert errors == []


@pytest.mark.asyncio
async def test_retrieval_service_hybrid_search_boosts_keyword_hits(monkeypatch):
    service = RetrievalService.__new__(RetrievalService)
    adapter = SimpleNamespace()

    async def fake_query(query_vector, top_k, filters, namespace):
        del query_vector, top_k, filters, namespace
        return [
            SearchResult(id="semantic-best", score=0.88, text="totally unrelated", metadata={}),
            SearchResult(id="keyword-hit", score=0.80, text="hello keyword world", metadata={}),
        ]

    monkeypatch.setattr(adapter, "query", fake_query, raising=False)

    results = await RetrievalService._hybrid_search(
        service,
        adapter,
        query="hello keyword",
        query_vector=[1.0, 0.0],
        top_k=2,
        filters=None,
        namespace=None,
    )

    assert results[0].id == "keyword-hit"


@pytest.mark.asyncio
async def test_retrieval_service_keyword_only_returns_empty_placeholder():
    service = RetrievalService.__new__(RetrievalService)
    results = await RetrievalService._keyword_search(
        service,
        adapter=object(),
        query="hello",
        top_k=3,
        filters=None,
        namespace=None,
    )
    assert results == []


@pytest.mark.asyncio
async def test_retrieval_service_recency_boosted_reorders_newer_records(monkeypatch):
    service = RetrievalService.__new__(RetrievalService)
    adapter = SimpleNamespace()

    async def fake_query(query_vector, top_k, filters, namespace):
        del query_vector, top_k, filters, namespace
        return [
            SearchResult(id="old", score=0.80, text="older", metadata={"timestamp": 1}),
            SearchResult(id="new", score=0.79, text="newer", metadata={"timestamp": 4102444800}),
        ]

    monkeypatch.setattr(adapter, "query", fake_query, raising=False)

    results = await RetrievalService._recency_boosted_search(
        service,
        adapter,
        query_vector=[1.0],
        top_k=2,
        filters=None,
        namespace=None,
    )

    assert results[0].id == "new"


@pytest.mark.asyncio
async def test_query_multiple_stores_continues_when_one_store_fails(monkeypatch):
    service = RetrievalService.__new__(RetrievalService)
    bad_store_id = uuid.uuid4()
    good_store_id = uuid.uuid4()

    async def fake_query(store_id, query, top_k=10, filters=None, policy_override=None, namespace=None, policy_snapshot=None):
        del query, top_k, filters, policy_override, namespace, policy_snapshot
        if store_id == bad_store_id:
            raise RuntimeError("boom")
        return [
            RetrievalResult(
                id="ok-1",
                score=0.7,
                text="ok",
                metadata={"store": str(store_id)},
                knowledge_store_id=store_id,
            )
        ]

    monkeypatch.setattr(service, "query", fake_query)
    results = await RetrievalService.query_multiple_stores(service, [bad_store_id, good_store_id], "hello", top_k=2)
    assert len(results) == 1
    assert results[0].id == "ok-1"
