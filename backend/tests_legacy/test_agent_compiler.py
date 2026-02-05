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
    assert any("Graph must have exactly one Start node" in m for m in messages)
    assert any("Graph must have at least one End node" in m for m in messages)

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
@pytest.mark.asyncio
async def test_compile_simple_graph():
    compiler = AgentCompiler()
    graph = AgentGraph(
        nodes=[
            {"id": "n1", "type": NodeType.INPUT, "position": {"x": 0, "y": 0}},
            {"id": "n2", "type": NodeType.LLM_CALL, "position": {"x": 100, "y": 0}, "config": {"model_id": "mock-model"}},
            {"id": "n3", "type": NodeType.OUTPUT, "position": {"x": 200, "y": 0}}
        ],
        edges=[
            {"id": "e1", "source": "n1", "target": "n2", "type": EdgeType.CONTROL},
            {"id": "e2", "source": "n2", "target": "n3", "type": EdgeType.CONTROL}
        ]
    )
    
    agent_id = uuid4()
    graph_ir = await compiler.compile(
        agent_id=agent_id,
        version=1,
        graph=graph,
        memory_config={},
        execution_constraints={}
    )
    
    assert graph_ir is not None
    assert graph_ir.entry_point == "n1"

@pytest.mark.asyncio
async def test_compile_frontend_graph():
    """Verify that the compiler handles frontend-specific node types and extra fields."""
    compiler = AgentCompiler()
    
    # Graph data mimicking the frontend payload that caused the error
    frontend_graph_data = {
        "nodes": [
            {
                "id": "start-node",
                "type": "start", # Alias for INPUT
                "position": {"x": 0, "y": 0},
                "data": {"some_extra": "value"}, # Extra field
                "measured": {"width": 100, "height": 100}, # Extra field
                "dragging": False # Extra field
            },
            {
                "id": "end-node",
                "type": "end", # Alias for OUTPUT
                "position": {"x": 200, "y": 0},
                "data": {} 
            }
        ],
        "edges": [
            {
                "id": "e1",
                "source": "start-node",
                "target": "end-node",
                "type": "control",
                "animated": True # Extra field
            }
        ]
    }
    
    # Validate manually first
    graph = AgentGraph(**frontend_graph_data)
    assert graph.nodes[0].type == NodeType.START
    
    # Compile
    agent_id = uuid4()
    graph_ir = await compiler.compile(
        agent_id=agent_id,
        version=1,
        graph=graph,
        memory_config={},
        execution_constraints={}
    )
    
    assert graph_ir is not None
    assert graph_ir.entry_point == "start-node"
