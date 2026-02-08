import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.agent.executors.tool import ToolNodeExecutor


class FakeResult:
    def __init__(self, tool):
        self._tool = tool

    def scalar_one_or_none(self):
        return self._tool


class FakeDB:
    def __init__(self, tool):
        self._tool = tool

    async def execute(self, _stmt):
        return FakeResult(self._tool)


def make_tool(tool_id, config_schema, implementation_type="MCP"):
    return SimpleNamespace(
        id=tool_id,
        name="mcp_tool",
        slug="mcp_tool",
        description="",
        schema={"input": {"type": "object"}},
        config_schema=config_schema,
        is_active=True,
        is_system=False,
        artifact_id=None,
        artifact_version=None,
        implementation_type=implementation_type,
    )


@pytest.mark.asyncio
async def test_mcp_tool_execution_jsonrpc_payload(monkeypatch):
    captured = {}

    def handler(request):
        body = json.loads(request.content.decode())
        captured["body"] = body
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True}})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    tool_id = uuid4()
    config_schema = {
        "implementation": {
            "type": "mcp",
            "server_url": "https://mcp.test/tools",
            "tool_name": "do_thing",
            "headers": {"X-Test": "yes"},
        },
        "execution": {"timeout_s": 5},
    }
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)
    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {"context": {"foo": "bar"}},
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert result["context"]["ok"] is True
    body = captured["body"]
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "do_thing"
    assert body["params"]["arguments"] == {"foo": "bar"}
