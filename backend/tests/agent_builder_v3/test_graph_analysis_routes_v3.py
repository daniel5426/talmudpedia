from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routers import agent_graph_mutations as router
from app.services.agent_service import AgentGraphValidationError


class _AnalyzeAgentService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def analyze_graph(self, agent_id, *, graph_definition):
        return {
            "agent_id": str(agent_id),
            "graph_definition": graph_definition,
            "analysis": {
                "spec_version": "3.0",
                "inventory": {
                    "workflow_input": [{"key": "input_as_text", "type": "string"}],
                    "state": [],
                    "node_outputs": [],
                    "template_suggestions": {"global": [], "by_node": {}},
                },
                "operator_contracts": {},
                "errors": [],
                "warnings": [],
            },
        }


class _AnalyzeValidationAgentService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def analyze_graph(self, *args, **kwargs):
        exc = AgentGraphValidationError([{"code": "BAD_GRAPH", "message": "Graph analysis failed"}])
        setattr(exc, "graph_mutation_phase", "analyze_graph")
        raise exc


@pytest.mark.asyncio
async def test_analyze_agent_graph_returns_analysis_payload(monkeypatch):
    monkeypatch.setattr(router, "AgentGraphMutationService", _AnalyzeAgentService)
    agent_id = uuid4()
    payload = router.GraphAnalysisRequest(graph_definition={"spec_version": "3.0", "nodes": [], "edges": []})

    response = await router.analyze_agent_graph(
        SimpleNamespace(headers={"X-Request-ID": "req-agent-analyze"}),
        agent_id,
        payload,
        {},
        {"tenant_id": uuid4(), "user": None},
        None,
    )

    assert response["agent_id"] == str(agent_id)
    assert response["graph_definition"]["spec_version"] == "3.0"
    assert response["analysis"]["spec_version"] == "3.0"
    assert response["analysis"]["inventory"]["workflow_input"][0]["key"] == "input_as_text"


@pytest.mark.asyncio
async def test_analyze_agent_graph_returns_structured_validation_error(monkeypatch):
    monkeypatch.setattr(router, "AgentGraphMutationService", _AnalyzeValidationAgentService)

    with pytest.raises(HTTPException) as exc_info:
        await router.analyze_agent_graph(
            SimpleNamespace(headers={"X-Request-ID": "req-agent-analyze-422"}),
            uuid4(),
            router.GraphAnalysisRequest(graph_definition={"spec_version": "3.0", "nodes": [], "edges": []}),
            {},
            {"tenant_id": uuid4(), "user": None},
            None,
        )

    detail = exc_info.value.detail
    assert exc_info.value.status_code == 422
    assert detail["code"] == "VALIDATION_ERROR"
    assert detail["request_id"] == "req-agent-analyze-422"
    assert detail["operation"] == "agents.graph.analyze"
    assert detail["phase"] == "analyze_graph"
    assert detail["errors"][0]["code"] == "BAD_GRAPH"
