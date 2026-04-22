from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.agent_service import AgentService
from app.services.prompt_reference_resolver import PromptReferenceResolver


@pytest.mark.asyncio
async def test_agent_write_normalizes_schema_defaults_and_contract_nodes(monkeypatch):
    service = AgentService(db=SimpleNamespace(), organization_id=uuid4(), project_id=uuid4())

    async def _noop_prompt_validation(self, graph_definition):
        return None

    async def _no_runtime_issues(_graph_definition):
        return []

    monkeypatch.setattr(PromptReferenceResolver, "validate_graph_definition", _noop_prompt_validation)
    monkeypatch.setattr(service, "_collect_runtime_reference_issues", _no_runtime_issues)

    normalized = await service._validate_graph_for_write(
        {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "position": {"x": 0, "y": 0},
                    "config": {
                        "state_variables": [{"key": "customer_id", "type": "string", "default": "abc"}],
                    },
                },
                {
                    "id": "assistant",
                    "type": "agent",
                    "position": {"x": 200, "y": 0},
                    "config": {"model_id": str(uuid4())},
                },
                {
                    "id": "router",
                    "type": "router",
                    "position": {"x": 400, "y": 0},
                    "config": {"route_table": [{"name": "success"}, {"name": "success"}]},
                },
                {
                    "id": "end",
                    "type": "end",
                    "position": {"x": 600, "y": 0},
                    "config": {},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assistant"},
                {"id": "e2", "source": "assistant", "target": "router"},
                {"id": "e3", "source": "router", "target": "end"},
            ],
        }
    )

    assistant = next(node for node in normalized["nodes"] if node["id"] == "assistant")
    router = next(node for node in normalized["nodes"] if node["id"] == "router")
    end = next(node for node in normalized["nodes"] if node["id"] == "end")

    assert normalized["spec_version"] == "4.0"
    assert normalized["state_contract"]["variables"][0]["key"] == "customer_id"
    assert normalized["state_contract"]["variables"][0]["type"] == "string"
    assert normalized["state_contract"]["variables"][0]["default_value"] == "abc"
    assert assistant["config"]["include_chat_history"] is True
    assert assistant["config"]["reasoning_effort"] == "medium"
    assert assistant["config"]["output_format"] == "text"
    assert assistant["config"]["tool_execution_mode"] == "sequential"
    assert assistant["config"]["max_parallel_tools"] == 4
    assert router["config"]["route_table"] == [
        {"name": "success", "match": "success"},
        {"name": "success_1", "match": "success_1"},
    ]
    assert router["config"]["routes"] == [
        {"name": "success", "match": "success"},
        {"name": "success_1", "match": "success_1"},
    ]
    assert end["config"]["output_schema"]["name"] == "workflow_result"
    assert end["config"]["output_bindings"][0]["json_pointer"] == "/response"


@pytest.mark.asyncio
async def test_agent_validation_surfaces_authoring_issues_with_paths(monkeypatch):
    service = AgentService(db=SimpleNamespace(), organization_id=uuid4(), project_id=uuid4())

    async def _no_runtime_issues(_graph_definition):
        return []

    async def _no_compiler_errors(self, graph, agent_id=None):
        return []

    monkeypatch.setattr(service, "_collect_runtime_reference_issues", _no_runtime_issues)
    monkeypatch.setattr("app.services.agent_service.AgentCompiler.validate", _no_compiler_errors)

    result = await service._build_validation_result_for_graph(
        {
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {
                    "id": "assistant",
                    "type": "agent",
                    "position": {"x": 200, "y": 0},
                    "config": {"bogus_field": 0.3},
                },
                {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assistant"},
                {"id": "e2", "source": "assistant", "target": "end"},
            ],
        }
    )

    assert result.valid is False
    codes_by_path = {(item.get("code"), item.get("path")) for item in result.errors}
    assert ("UNKNOWN_CONFIG_FIELD", "/nodes/1/config/bogus_field") in codes_by_path
    assert ("MISSING_REQUIRED_CONFIG", "/nodes/1/config/model_id") in codes_by_path
