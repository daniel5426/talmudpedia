from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent.registry import AgentOperatorRegistry
from app.services.agent_graph_mutation_service import AgentGraphMutationService
from app.services.graph_mutation_service import GraphMutationError, apply_graph_operations


def _agent_graph() -> dict:
    return {
        "spec_version": "2.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "assistant",
                "type": "agent",
                "position": {"x": 200, "y": 0},
                "config": {"instructions": "Initial", "tools": ["tool-a"], "model_id": "model-a"},
            },
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {"output_variable": "context"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "assistant", "type": "control"},
            {"id": "e2", "source": "assistant", "target": "end", "type": "control"},
        ],
    }


def _service() -> AgentGraphMutationService:
    return AgentGraphMutationService.__new__(AgentGraphMutationService)


def test_agent_graph_mutation_operations_preserve_edges_and_patch_config(monkeypatch):
    monkeypatch.setattr(
        AgentOperatorRegistry,
        "get",
        lambda _node_type: SimpleNamespace(
            config_schema={"properties": {"instructions": {}, "tools": {}, "model_id": {}}}
        ),
    )
    service = _service()

    mutation = apply_graph_operations(
        _agent_graph(),
        [
            {"op": "append_unique_node_config_list_item", "node_id": "assistant", "path": "tools", "value": "tool-b"},
            {"op": "set_node_config_value", "node_id": "assistant", "path": "instructions", "value": "Use web search"},
        ],
        validate_node_config_path=service._validate_node_config_path,
    )

    assistant = next(node for node in mutation.graph["nodes"] if node["id"] == "assistant")
    assert assistant["config"]["tools"] == ["tool-a", "tool-b"]
    assert assistant["config"]["instructions"] == "Use web search"
    assert mutation.graph["edges"] == _agent_graph()["edges"]
    assert mutation.changed_node_ids == ["assistant"]


def test_agent_graph_mutation_rejects_unknown_config_field(monkeypatch):
    monkeypatch.setattr(
        AgentOperatorRegistry,
        "get",
        lambda _node_type: SimpleNamespace(config_schema={"properties": {"instructions": {}, "tools": {}}}),
    )
    service = _service()

    with pytest.raises(GraphMutationError) as exc_info:
        apply_graph_operations(
            _agent_graph(),
            [{"op": "set_node_config_value", "node_id": "assistant", "path": "temperature", "value": 0.3}],
            validate_node_config_path=service._validate_node_config_path,
        )

    assert exc_info.value.errors[0]["code"] == "GRAPH_MUTATION_UNKNOWN_CONFIG_FIELD"


@pytest.mark.asyncio
async def test_agent_apply_patch_persists_incomplete_graph_and_returns_advisory_diagnostics(monkeypatch):
    agent_id = uuid4()
    service = _service()
    calls = {"updated": False}

    class _StubAgentService:
        async def get_agent(self, _agent_id):
            return SimpleNamespace(id=agent_id, slug="draft-agent", graph_definition=_agent_graph())

        async def _validate_graph_for_write(self, *_args, **_kwargs):
            return _agent_graph()

        async def validate_agent(self, _agent_id):
            return SimpleNamespace(valid=False, errors=[{"code": "VALIDATION_ERROR", "message": "invalid"}], warnings=[])

        async def _build_validation_result_for_graph(self, *_args, **_kwargs):
            return SimpleNamespace(valid=False, errors=[{"code": "VALIDATION_ERROR", "message": "invalid"}], warnings=[])

        async def update_agent(self, *_args, **_kwargs):
            calls["updated"] = True
            return SimpleNamespace(id=agent_id, graph_definition=_agent_graph())

    service.agent_service = _StubAgentService()
    monkeypatch.setattr(
        AgentOperatorRegistry,
        "get",
        lambda _node_type: SimpleNamespace(config_schema={"properties": {"instructions": {}, "tools": {}, "model_id": {}}}),
    )

    result = await service.apply_patch(
        agent_id,
        [{"op": "set_node_config_value", "node_id": "assistant", "path": "instructions", "value": "Retry"}],
    )

    assert calls["updated"] is True
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"][0]["code"] == "VALIDATION_ERROR"
