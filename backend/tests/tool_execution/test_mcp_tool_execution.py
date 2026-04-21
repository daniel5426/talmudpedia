import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.agent.executors.tool import ToolNodeExecutor
from app.services import mcp_client


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

    async def fake_resolve_hostname(_hostname):
        return [mcp_client.ipaddress.ip_address("93.184.216.34")]

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
    monkeypatch.setattr(
        mcp_client,
        "_resolve_hostname_addresses",
        fake_resolve_hostname,
    )

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

    executor = ToolNodeExecutor(organization_id=None, db=db)
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


@pytest.mark.asyncio
async def test_mcp_tool_execution_rejects_private_host_by_default(monkeypatch):
    monkeypatch.delenv("MCP_ALLOW_PRIVATE_HOSTS", raising=False)

    tool_id = uuid4()
    tool = make_tool(
        tool_id,
        {
            "implementation": {
                "type": "mcp",
                "server_url": "http://127.0.0.1:8080/tools",
                "tool_name": "do_thing",
            }
        },
    )
    db = FakeDB(tool)
    executor = ToolNodeExecutor(organization_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    with pytest.raises(ValueError, match="private or loopback hosts"):
        await executor.execute(
            {"context": {"foo": "bar"}},
            {"tool_id": str(tool_id)},
            {"node_id": "tool-node"},
        )


@pytest.mark.asyncio
async def test_mcp_tool_execution_rejects_non_allowlisted_host(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "trusted.example")

    with pytest.raises(ValueError, match="not in MCP_ALLOWED_HOSTS"):
        await mcp_client.call_mcp_tool(
            server_url="https://mcp.test/tools",
            tool_name="do_thing",
            arguments={"foo": "bar"},
        )


@pytest.mark.asyncio
async def test_mcp_tool_execution_normalizes_http_errors(monkeypatch):
    async def fake_resolve_hostname(_hostname):
        return [mcp_client.ipaddress.ip_address("93.184.216.34")]

    def handler(_request):
        return httpx.Response(502, json={"error": "upstream bad gateway"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(
        mcp_client,
        "_resolve_hostname_addresses",
        fake_resolve_hostname,
    )

    with pytest.raises(RuntimeError, match="MCP transport error: HTTP 502"):
        await mcp_client.call_mcp_tool(
            server_url="https://mcp.test/tools",
            tool_name="do_thing",
            arguments={"foo": "bar"},
        )


@pytest.mark.asyncio
async def test_mcp_tool_execution_rejects_invalid_json_response(monkeypatch):
    async def fake_resolve_hostname(_hostname):
        return [mcp_client.ipaddress.ip_address("93.184.216.34")]

    def handler(_request):
        return httpx.Response(200, text="not-json")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(
        mcp_client,
        "_resolve_hostname_addresses",
        fake_resolve_hostname,
    )

    with pytest.raises(RuntimeError, match="non-JSON response"):
        await mcp_client.call_mcp_tool(
            server_url="https://mcp.test/tools",
            tool_name="do_thing",
            arguments={"foo": "bar"},
        )


def test_mcp_oauth_metadata_candidates_support_path_issuers():
    candidates = mcp_client._authorization_server_metadata_candidates("https://github.com/login/oauth")

    assert "https://github.com/.well-known/oauth-authorization-server/login/oauth" in candidates
    assert "https://github.com/login/oauth/.well-known/oauth-authorization-server" in candidates


def test_mcp_oauth_metadata_candidates_support_root_issuers():
    candidates = mcp_client._authorization_server_metadata_candidates("https://mcp.linear.app")

    assert candidates[0] == "https://mcp.linear.app/.well-known/oauth-authorization-server"
    assert "https://mcp.linear.app/.well-known/openid-configuration" in candidates


def test_mcp_protected_resource_metadata_candidates_support_path_resources():
    candidates = mcp_client._protected_resource_metadata_candidates("https://gitlab.com/api/v4/mcp")

    assert candidates[0] == "https://gitlab.com/.well-known/oauth-protected-resource/api/v4/mcp"
    assert "https://gitlab.com/.well-known/oauth-protected-resource" in candidates
