import pytest
from uuid import uuid4
from app.agent.graph.schema import AgentGraph, NodeType, EdgeType
from app.agent.graph.compiler import AgentCompiler

@pytest.mark.asyncio
async def test_compiler_validation_empty_graph():
    compiler = AgentCompiler()
    graph = AgentGraph(nodes=[], edges=[])
    errors = await compiler.validate(graph)
    
    messages = [e.message for e in errors]
    assert "Graph must have at least one input node" in messages
    assert "Graph must have at least one output node" in messages

@pytest.mark.asyncio
async def test_compiler_validation_valid_minimal_graph():
    compiler = AgentCompiler()
    graph = AgentGraph(
        nodes=[
            {"id": "n1", "type": NodeType.INPUT, "position": {"x": 0, "y": 0}},
            {"id": "n2", "type": NodeType.OUTPUT, "position": {"x": 100, "y": 0}}
        ],
        edges=[
            {"id": "e1", "source": "n1", "target": "n2", "type": EdgeType.CONTROL}
        ]
    )
    errors = await compiler.validate(graph)
    assert len(errors) == 0

@pytest.mark.asyncio
async def test_compiler_validation_missing_config():
    compiler = AgentCompiler()
    graph = AgentGraph(
        nodes=[
            {"id": "n1", "type": NodeType.INPUT, "position": {"x": 0, "y": 0}},
            {"id": "n2", "type": NodeType.LLM_CALL, "position": {"x": 100, "y": 0}, "config": {}},
            {"id": "n3", "type": NodeType.OUTPUT, "position": {"x": 200, "y": 0}}
        ],
        edges=[
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"}
        ]
    )
    errors = await compiler.validate(graph)
    assert any("model_id" in e.message for e in errors)
