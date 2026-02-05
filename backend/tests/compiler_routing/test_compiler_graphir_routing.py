from uuid import uuid4

import pytest

from app.agent.executors.standard import register_standard_operators
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph, NodeType, EdgeType


@pytest.mark.asyncio
async def test_compiler_builds_routing_maps_and_interrupts():
    register_standard_operators()
    compiler = AgentCompiler()

    graph = AgentGraph(
        spec_version="1.0",
        nodes=[
            {"id": "start", "type": NodeType.START, "position": {"x": 0, "y": 0}},
            {"id": "approval", "type": "user_approval", "position": {"x": 100, "y": 0}},
            {"id": "end_yes", "type": NodeType.END, "position": {"x": 200, "y": -50}},
            {"id": "end_no", "type": NodeType.END, "position": {"x": 200, "y": 50}},
        ],
        edges=[
            {"id": "e1", "source": "start", "target": "approval", "type": EdgeType.CONTROL},
            {"id": "e2", "source": "approval", "target": "end_yes", "source_handle": "approve"},
            {"id": "e3", "source": "approval", "target": "end_no", "source_handle": "reject"},
        ],
    )

    graph_ir = await compiler.compile(
        agent_id=uuid4(),
        version=1,
        graph=graph,
        memory_config={},
        execution_constraints={},
    )

    routing = graph_ir.routing_maps.get("approval")
    assert routing is not None
    assert set(routing.handles) == {"approve", "reject"}
    assert routing.edges["approve"] == "end_yes"
    assert routing.edges["reject"] == "end_no"

    assert graph_ir.entry_point == "start"
    assert set(graph_ir.exit_nodes) == {"end_yes", "end_no"}
    assert "approval" in graph_ir.interrupt_before


@pytest.mark.asyncio
async def test_compiler_routing_validation_errors():
    register_standard_operators()
    compiler = AgentCompiler()

    graph = AgentGraph(
        nodes=[
            {"id": "start", "type": NodeType.START, "position": {"x": 0, "y": 0}},
            {"id": "approval", "type": "user_approval", "position": {"x": 100, "y": 0}},
            {"id": "end", "type": NodeType.END, "position": {"x": 200, "y": 0}},
        ],
        edges=[
            {"id": "e1", "source": "start", "target": "approval"},
            {"id": "e2", "source": "approval", "target": "end"},
            {"id": "e3", "source": "approval", "target": "end", "source_handle": "approve"},
            {"id": "e4", "source": "approval", "target": "end", "source_handle": "approve"},
            {"id": "e5", "source": "approval", "target": "end", "source_handle": "maybe"},
        ],
    )

    errors = await compiler.validate(graph)
    messages = [e.message for e in errors]

    assert any("Conditional edge missing source_handle" in m for m in messages)
    assert any("Duplicate branch handle" in m for m in messages)
    assert any("Invalid branch handle" in m for m in messages)
    assert any("Missing branch edges for handles" in m for m in messages)
