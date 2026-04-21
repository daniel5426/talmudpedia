from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routers import agent_graph_mutations as router
from app.services.agent_service import AgentGraphValidationError


class _ExplodingAgentService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def apply_patch(self, *args, **kwargs):
        exc = RuntimeError("post-write response build failed")
        setattr(exc, "graph_mutation_phase", "post_write_validation")
        raise exc


class _ValidationAgentService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def validate_patch(self, *args, **kwargs):
        exc = AgentGraphValidationError([{"code": "BAD_GRAPH", "message": "Graph is invalid"}])
        setattr(exc, "graph_mutation_phase", "preview_validation")
        raise exc


@pytest.mark.asyncio
async def test_apply_agent_graph_patch_returns_structured_internal_error(monkeypatch):
    monkeypatch.setattr(router, "AgentGraphMutationService", _ExplodingAgentService)

    with pytest.raises(HTTPException) as exc_info:
        await router.apply_agent_graph_patch(
            SimpleNamespace(headers={"X-Request-ID": "req-agent-500"}),
            uuid4(),
            router.GraphPatchRequest(operations=[]),
            {},
            {"organization_id": uuid4(), "user": SimpleNamespace(id=uuid4())},
            None,
        )

    detail = exc_info.value.detail
    assert exc_info.value.status_code == 500
    assert detail["code"] == "GRAPH_MUTATION_INTERNAL_ERROR"
    assert detail["request_id"] == "req-agent-500"
    assert detail["operation"] == "agents.graph.apply_patch"
    assert detail["phase"] == "post_write_validation"
    assert detail["error_class"] == "RuntimeError"
    assert "response build failed" in detail["error_message"]


@pytest.mark.asyncio
async def test_validate_agent_graph_patch_returns_structured_validation_error(monkeypatch):
    monkeypatch.setattr(router, "AgentGraphMutationService", _ValidationAgentService)

    with pytest.raises(HTTPException) as exc_info:
        await router.validate_agent_graph_patch(
            SimpleNamespace(headers={"X-Request-ID": "req-agent-422"}),
            uuid4(),
            router.GraphPatchRequest(operations=[{"op": "set_node_config_value"}]),
            {},
            {"organization_id": uuid4(), "user": None},
            None,
        )

    detail = exc_info.value.detail
    assert exc_info.value.status_code == 422
    assert detail["code"] == "VALIDATION_ERROR"
    assert detail["request_id"] == "req-agent-422"
    assert detail["operation"] == "agents.graph.validate_patch"
    assert detail["phase"] == "preview_validation"
    assert detail["errors"][0]["code"] == "BAD_GRAPH"
