from __future__ import annotations

import uuid

import pytest

from app.db.postgres.models.rag import PipelineType, VisualPipeline
from app.rag.pipeline.compiler import PipelineCompiler


def _pipeline(*, pipeline_type: PipelineType, nodes: list[dict], edges: list[dict]) -> VisualPipeline:
    return VisualPipeline(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Invalid Topology",
        description=None,
        pipeline_type=pipeline_type,
        version=1,
        is_published=False,
        nodes=nodes,
        edges=edges,
    )


def _node(node_id: str, category: str, operator: str, config: dict | None = None) -> dict:
    return {
        "id": node_id,
        "category": category,
        "operator": operator,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def _edge(edge_id: str, source: str, target: str) -> dict:
    return {"id": edge_id, "source": source, "target": target}


def _codes(result) -> set[str]:
    return {error.code for error in result.errors}


def test_retrieval_pipeline_requires_query_input():
    result = PipelineCompiler().compile(
        _pipeline(
            pipeline_type=PipelineType.RETRIEVAL,
            nodes=[
                _node("embed", "embedding", "model_embedder", {"model_id": "m-1"}),
                _node("search", "retrieval", "vector_search", {"knowledge_store_id": str(uuid.uuid4())}),
                _node("output", "output", "retrieval_result"),
            ],
            edges=[_edge("e1", "embed", "search"), _edge("e2", "search", "output")],
        )
    )

    assert result.success is False
    assert "NO_QUERY_INPUT" in _codes(result)


def test_retrieval_pipeline_rejects_multiple_query_inputs():
    result = PipelineCompiler().compile(
        _pipeline(
            pipeline_type=PipelineType.RETRIEVAL,
            nodes=[
                _node("input_a", "input", "query_input"),
                _node("input_b", "input", "query_input"),
                _node("output", "output", "retrieval_result"),
            ],
            edges=[_edge("e1", "input_a", "output")],
        )
    )

    assert result.success is False
    assert "MULTIPLE_QUERY_INPUTS" in _codes(result)


def test_retrieval_pipeline_rejects_direct_query_to_result_type_mismatch():
    result = PipelineCompiler().compile(
        _pipeline(
            pipeline_type=PipelineType.RETRIEVAL,
            nodes=[
                _node("input", "input", "query_input"),
                _node("output", "output", "retrieval_result"),
            ],
            edges=[_edge("e1", "input", "output")],
        )
    )

    assert result.success is False
    assert "TYPE_MISMATCH" in _codes(result)


def test_retrieval_pipeline_rejects_output_node_with_outgoing_edges():
    result = PipelineCompiler().compile(
        _pipeline(
            pipeline_type=PipelineType.RETRIEVAL,
            nodes=[
                _node("input", "input", "query_input"),
                _node("output", "output", "retrieval_result"),
                _node("search", "retrieval", "vector_search", {"knowledge_store_id": str(uuid.uuid4())}),
            ],
            edges=[_edge("e1", "input", "output"), _edge("e2", "output", "search")],
        )
    )

    assert result.success is False
    assert "EXIT_NODE_HAS_OUTPUTS" in _codes(result)


def test_ingestion_pipeline_rejects_unreachable_orphan_node():
    result = PipelineCompiler().compile(
        _pipeline(
            pipeline_type=PipelineType.INGESTION,
            nodes=[
                _node("source", "source", "web_crawler", {"start_urls": "https://example.com"}),
                _node("chunk", "chunking", "chunker", {"strategy": "recursive"}),
                _node("embed", "embedding", "model_embedder", {"model_id": "m-1"}),
                _node("sink", "storage", "knowledge_store_sink", {"knowledge_store_id": str(uuid.uuid4())}),
                _node("orphan", "normalization", "format_normalizer"),
            ],
            edges=[
                _edge("e1", "source", "chunk"),
                _edge("e2", "chunk", "embed"),
                _edge("e3", "embed", "sink"),
            ],
        )
    )

    assert result.success is False
    assert "UNREACHABLE_NODE" in _codes(result)
