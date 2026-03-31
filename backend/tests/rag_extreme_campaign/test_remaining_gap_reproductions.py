from __future__ import annotations

import uuid

import pytest

from app.api.routers.rag_pipelines import PipelineInputValidator
from app.rag.pipeline.compiler import PipelineCompiler
from app.rag.pipeline.input_storage import PipelineInputStorage
from app.rag.pipeline.operator_executor import ExecutionContext, ExecutorRegistry, OperatorInput
from app.rag.pipeline.registry import OperatorRegistry
from app.services.platform_native_tools import _pipeline_shell_graph
from app.system_artifacts.platform_sdk.actions.rag import _retrieval_pipeline_shell_graph


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
            "config": {"knowledge_store_id": str(uuid.uuid4()), "top_k": 3},
            "depends_on": ["embed"],
        },
        {
            "step_id": "output",
            "operator": "retrieval_result",
            "config": {},
            "depends_on": ["search"],
        },
    ]


def _compile_retrieval_shell(graph: dict):
    from app.db.postgres.models.rag import PipelineType, VisualPipeline

    return PipelineCompiler().compile(
        VisualPipeline(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Seeded Retrieval Shell",
            description=None,
            nodes=graph["nodes"],
            edges=graph["edges"],
            pipeline_type=PipelineType.RETRIEVAL,
            version=1,
            is_published=False,
        )
    )


@pytest.mark.asyncio
async def test_model_embedder_safe_execute_accepts_structured_query_payload():
    spec = OperatorRegistry.get_instance().get("model_embedder")
    assert spec is not None
    executor = OperatorRegistry.get_instance()
    del executor

    from app.rag.pipeline.operator_executor import ExecutorRegistry

    result = await ExecutorRegistry.create_executor(spec).safe_execute(
        OperatorInput(data={"text": "hello retrieval", "top_k": 3}),
        ExecutionContext(step_id="embed", config={"model_id": "model-1"}),
    )

    assert result.success is False
    assert "Database session is required in execution context" in (result.error_message or "")


@pytest.mark.asyncio
async def test_pipeline_input_validator_accepts_runtime_top_k_for_query_input():
    validator = PipelineInputValidator(
        _retrieval_dag(),
        OperatorRegistry.get_instance(),
        tenant_id=None,
        storage=PipelineInputStorage(),
    )

    normalized, errors = validator.validate({"text": "hello retrieval", "top_k": 5})
    assert normalized == {"input": {"text": "hello retrieval", "top_k": 5}}
    assert errors == []


@pytest.mark.parametrize("graph_factory", [_pipeline_shell_graph, _retrieval_pipeline_shell_graph])
def test_seeded_retrieval_shell_graphs_compile_as_valid(graph_factory):
    result = _compile_retrieval_shell(graph_factory())

    assert result.success is True
    assert result.errors == []


def test_registry_matches_final_rag_catalog_and_retires_replaced_node_ids():
    registry = OperatorRegistry.get_instance()
    actual_ids = {spec.operator_id for spec in registry.list_all()}
    expected_ids = {
        "local_loader",
        "s3_loader",
        "web_crawler",
        "api_loader",
        "format_normalizer",
        "pii_redactor",
        "metadata_extractor",
        "entity_recognizer",
        "classifier",
        "llm",
        "chunker",
        "model_embedder",
        "knowledge_store_sink",
        "query_input",
        "vector_search",
        "hybrid_search",
        "reranker",
        "retrieval_result",
        "transform",
    }

    assert actual_ids == expected_ids

    for retired_id in (
        "language_detector",
        "summarizer",
        "token_based_chunker",
        "recursive_chunker",
        "semantic_chunker",
        "hierarchical_chunker",
        "model_reranker",
        "cross_encoder_reranker",
    ):
        assert registry.get(retired_id) is None
        assert ExecutorRegistry.get(retired_id) is None
