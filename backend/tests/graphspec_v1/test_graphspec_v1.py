import pytest

from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph


@pytest.mark.asyncio
async def test_graphspec_v1_normalizes_legacy_fields():
    graph = AgentGraph(
        spec_version="1.0",
        nodes=[
            {
                "id": "n1",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {
                    "config": {"label": "Start"},
                    "inputMappings": {"documents": "{{ state.docs }}"},
                },
            }
        ],
        edges=[
            {
                "id": "e1",
                "source": "n1",
                "target": "n2",
                "sourceHandle": "approve",
                "targetHandle": "reject",
            }
        ],
    )

    node = graph.nodes[0]
    edge = graph.edges[0]

    assert node.config.get("label") == "Start"
    assert node.input_mappings == {"documents": "{{ state.docs }}"}
    assert edge.source_handle == "approve"
    assert edge.target_handle == "reject"


@pytest.mark.asyncio
async def test_graphspec_version_validation_rejects_unknown_version():
    compiler = AgentCompiler()
    graph = AgentGraph(spec_version="3.0", nodes=[], edges=[])
    errors = await compiler.validate(graph)
    messages = [e.message for e in errors]
    assert any("Unsupported graph spec version" in m for m in messages)


@pytest.mark.asyncio
async def test_graphspec_routing_normalizes_whitespace_handles():
    compiler = AgentCompiler()
    graph = AgentGraph(
        spec_version="1.0",
        nodes=[
            {
                "id": "start-1",
                "type": "start",
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "classify-1",
                "type": "classify",
                "position": {"x": 120, "y": 0},
                "config": {
                    "model_id": "model-1",
                    "categories": [{"name": "money "}, {"name": "other"}],
                },
            },
            {
                "id": "end-1",
                "type": "end",
                "position": {"x": 240, "y": 0},
            },
        ],
        edges=[
            {"id": "e1", "source": "start-1", "target": "classify-1"},
            {"id": "e2", "source": "classify-1", "target": "end-1", "source_handle": "money"},
            {"id": "e3", "source": "classify-1", "target": "end-1", "source_handle": "other"},
        ],
    )

    errors = await compiler.validate(graph)
    messages = [e.message for e in errors]
    assert not any("Invalid branch handle" in m for m in messages)
    assert not any("Missing branch edges for handles" in m for m in messages)
