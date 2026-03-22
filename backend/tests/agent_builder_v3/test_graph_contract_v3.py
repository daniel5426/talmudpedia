from uuid import uuid4

import pytest

from app.agent.executors.data import SetStateNodeExecutor
from app.agent.executors.standard import register_standard_operators
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.contracts import materialize_end_output
from app.agent.graph.schema import AgentGraph


def _base_v3_graph() -> AgentGraph:
    return AgentGraph(
        spec_version="3.0",
        nodes=[
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "config": {
                    "state_variables": [
                        {"key": "customer_name", "type": "string", "default_value": "Ada"},
                    ]
                },
            },
            {
                "id": "agent_1",
                "type": "agent",
                "position": {"x": 120, "y": 0},
                "config": {"model_id": "model-1", "output_format": "text"},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 240, "y": 0},
                "config": {
                    "output_schema": {
                        "name": "result",
                        "mode": "simple",
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "reply": {"type": "string"},
                                "name": {"type": "string"},
                            },
                            "required": ["reply", "name"],
                        },
                    },
                    "output_bindings": [
                        {"json_pointer": "/reply", "value_ref": {"namespace": "node_output", "node_id": "agent_1", "key": "output_text"}},
                        {"json_pointer": "/name", "value_ref": {"namespace": "state", "key": "customer_name"}},
                    ],
                },
            },
        ],
        edges=[
            {"id": "e1", "source": "start", "target": "agent_1"},
            {"id": "e2", "source": "agent_1", "target": "end"},
        ],
    )


@pytest.mark.asyncio
async def test_graph_v3_analysis_exposes_inventory_and_metadata():
    register_standard_operators()
    compiler = AgentCompiler()
    graph = _base_v3_graph()

    graph_ir = await compiler.compile(agent_id=uuid4(), version=1, graph=graph)
    analysis = graph_ir.metadata.get("analysis") or {}

    assert analysis["spec_version"] == "3.0"
    assert analysis["inventory"]["workflow_input"][0]["key"] == "input_as_text"
    assert any(item["key"] == "customer_name" for item in analysis["inventory"]["state"])
    agent_outputs = next(item for item in analysis["inventory"]["node_outputs"] if item["node_id"] == "agent_1")
    assert any(field["key"] == "output_text" for field in agent_outputs["fields"])


@pytest.mark.asyncio
async def test_graph_v3_requires_type_when_set_state_creates_new_key():
    register_standard_operators()
    compiler = AgentCompiler()
    base = _base_v3_graph()
    graph = AgentGraph(
        spec_version=base.spec_version,
        nodes=[
            *[node.model_dump() for node in base.nodes[:2]],
            {
                "id": "set_state_1",
                "type": "set_state",
                "position": {"x": 180, "y": 0},
                "config": {"assignments": [{"key": "new_value", "value": "state.customer_name"}]},
            },
            *[node.model_dump() for node in base.nodes[2:]],
        ],
        edges=[
            {"id": "e1", "source": "start", "target": "agent_1"},
            {"id": "e2", "source": "agent_1", "target": "set_state_1"},
            {"id": "e3", "source": "set_state_1", "target": "end"},
        ],
    )

    errors = await compiler.validate(graph)
    assert any("must declare a type" in error.message for error in errors)


def test_materialize_end_output_uses_schema_bindings():
    payload = materialize_end_output(
        config=_base_v3_graph().nodes[-1].config,
        state={
            "workflow_input": {"input_as_text": "hello"},
            "state": {"customer_name": "Ada"},
            "node_outputs": {"agent_1": {"output_text": "Shalom"}},
        },
    )

    assert payload == {"reply": "Shalom", "name": "Ada"}


@pytest.mark.asyncio
async def test_set_state_executor_writes_typed_value_ref_assignment():
    executor = SetStateNodeExecutor(tenant_id=uuid4(), db=None)

    payload = await executor.execute(
        state={
            "workflow_input": {"input_as_text": "hello"},
            "state": {"customer_name": "Ada"},
            "state_types": {"customer_name": "string"},
        },
        config={
            "assignments": [
                {
                    "key": "selected_name",
                    "type": "string",
                    "value_ref": {"namespace": "state", "key": "customer_name"},
                }
            ]
        },
        context={"node_id": "set_state_1", "node_name": "Set State"},
    )

    assert payload["state"]["selected_name"] == "Ada"
    assert payload["state_types"]["selected_name"] == "string"


@pytest.mark.asyncio
async def test_graph_v3_rejects_set_state_value_ref_type_mismatch():
    register_standard_operators()
    compiler = AgentCompiler()
    base = _base_v3_graph()
    graph = AgentGraph(
        spec_version=base.spec_version,
        nodes=[
            *[node.model_dump() for node in base.nodes[:2]],
            {
                "id": "set_state_1",
                "type": "set_state",
                "position": {"x": 180, "y": 0},
                "config": {
                    "assignments": [
                        {
                            "key": "score",
                            "type": "number",
                            "value_ref": {"namespace": "workflow_input", "key": "input_as_text"},
                        }
                    ]
                },
            },
            *[node.model_dump() for node in base.nodes[2:]],
        ],
        edges=[
            {"id": "e1", "source": "start", "target": "agent_1"},
            {"id": "e2", "source": "agent_1", "target": "set_state_1"},
            {"id": "e3", "source": "set_state_1", "target": "end"},
        ],
    )

    errors = await compiler.validate(graph)
    assert any("type mismatch" in error.message for error in errors)
