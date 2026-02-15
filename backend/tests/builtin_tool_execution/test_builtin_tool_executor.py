from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.agent.executors.retrieval_runtime import RetrievalPipelineRuntime
from app.agent.executors.tool import ToolNodeExecutor
from app.db.postgres.models.registry import ToolStatus


class DummyDB:
    pass


def _make_tool(
    *,
    implementation_type: str,
    config_schema: dict,
    builtin_key: str | None = None,
    status: ToolStatus | str = ToolStatus.PUBLISHED,
    is_active: bool = True,
):
    return SimpleNamespace(
        id=uuid4(),
        name="tool-under-test",
        slug="tool-under-test",
        description="",
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema=config_schema,
        is_active=is_active,
        is_system=False,
        artifact_id=None,
        artifact_version=None,
        implementation_type=implementation_type,
        builtin_key=builtin_key,
        is_builtin_template=False,
        status=status,
    )


@pytest.mark.asyncio
async def test_builtin_retrieval_pipeline_executes_runtime(monkeypatch):
    pipeline_id = str(uuid4())
    tool = _make_tool(
        implementation_type="RAG_RETRIEVAL",
        builtin_key="retrieval_pipeline",
        config_schema={"implementation": {"type": "rag_retrieval", "pipeline_id": pipeline_id}},
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    async def fake_run_query(self, *, pipeline_id, query, top_k=10, filters=None):
        return ([{"doc_id": "d1", "score": 0.91, "query": query, "top_k": top_k, "filters": filters or {}}], None)

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr(RetrievalPipelineRuntime, "run_query", fake_run_query)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())
    result = await executor.execute(
        state={"context": {"query": "where is this text", "top_k": 3, "filters": {"tractate": "Berakhot"}}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node"},
    )

    assert result["context"]["pipeline_id"] == pipeline_id
    assert result["context"]["count"] == 1
    assert result["context"]["results"][0]["query"] == "where is this text"


@pytest.mark.asyncio
async def test_unknown_implementation_type_returns_explicit_error(monkeypatch):
    tool = _make_tool(
        implementation_type="INTERNAL",
        config_schema={"implementation": {"type": "internal"}},
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())
    with pytest.raises(NotImplementedError, match="Unsupported tool implementation type"):
        await executor.execute(
            state={"context": {"x": 1}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node"},
        )


@pytest.mark.asyncio
async def test_production_blocks_draft_but_debug_allows(monkeypatch):
    tool = _make_tool(
        implementation_type="HTTP",
        config_schema={"implementation": {"type": "http", "url": "https://example.com", "method": "GET"}},
        status=ToolStatus.DRAFT,
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    async def fake_http(_self, _tool, input_data, _impl, _ctx):
        return {"ok": True, "echo": input_data}

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr(ToolNodeExecutor, "_execute_http_tool", fake_http)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())

    with pytest.raises(PermissionError, match="published"):
        await executor.execute(
            state={"context": {"x": 1}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "production"},
        )

    allowed = await executor.execute(
        state={"context": {"x": 1}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node", "mode": "debug"},
    )
    assert allowed["context"]["ok"] is True


@pytest.mark.asyncio
async def test_web_fetch_happy_path_and_invalid_scheme(monkeypatch):
    tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="web_fetch",
        config_schema={"implementation": {"type": "builtin", "builtin": "web_fetch", "timeout_s": 5}},
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello world", headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())

    ok = await executor.execute(
        state={"context": {"url": "https://example.com"}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node"},
    )
    assert ok["context"]["status_code"] == 200
    assert "hello" in ok["context"]["text"]

    with pytest.raises(ValueError, match="http/https"):
        await executor.execute(
            state={"context": {"url": "file:///tmp/test.txt"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node"},
        )


@pytest.mark.asyncio
async def test_web_search_uses_provider_dispatch(monkeypatch):
    tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="web_search",
        config_schema={
            "implementation": {
                "type": "builtin",
                "builtin": "web_search",
                "provider": "serper",
                "api_key": "test-key",
            }
        },
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    class FakeProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {
                "query": query,
                "provider": "serper",
                "results": [{"title": "Result", "url": "https://example.com", "top_k": top_k}],
            }

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "test-key"
        return FakeProvider()

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())
    result = await executor.execute(
        state={"context": {"query": "latest halacha", "top_k": 3}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node"},
    )

    assert result["context"]["provider"] == "serper"
    assert result["context"]["query"] == "latest halacha"
    assert len(result["context"]["results"]) == 1


@pytest.mark.asyncio
async def test_web_search_accepts_q_alias(monkeypatch):
    tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="web_search",
        config_schema={
            "implementation": {
                "type": "builtin",
                "builtin": "web_search",
                "provider": "serper",
                "api_key": "test-key",
            }
        },
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    class FakeProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {"query": query, "provider": "serper", "results": [{"query": query, "top_k": top_k}]}

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "test-key"
        return FakeProvider()

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())
    result = await executor.execute(
        state={"context": {"q": "shabbat candle lighting", "top_k": 2}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node"},
    )

    assert result["context"]["provider"] == "serper"
    assert result["context"]["query"] == "shabbat candle lighting"


@pytest.mark.asyncio
async def test_web_search_uses_tenant_settings_credentials_when_tool_has_no_key(monkeypatch):
    tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="web_search",
        config_schema={
            "implementation": {
                "type": "builtin",
                "builtin": "web_search",
                "provider": "serper",
            }
        },
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    class FakeProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {"query": query, "provider": "serper", "results": [{"query": query, "top_k": top_k}]}

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "tenant-settings-key"
        return FakeProvider()

    async def fake_get_by_provider(self, *, category, provider_key: str, provider_variant=None):
        _ = category  # enum check is covered implicitly by runtime behavior
        if provider_key == "web_search" and provider_variant == "serper":
            return SimpleNamespace(
                is_enabled=True,
                credentials={"api_key": "tenant-settings-key"},
            )
        return None

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)
    monkeypatch.setattr("app.agent.executors.tool.CredentialsService.get_by_provider", fake_get_by_provider)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())
    result = await executor.execute(
        state={"context": {"query": "amud yomi", "top_k": 1}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node"},
    )

    assert result["context"]["provider"] == "serper"
    assert result["context"]["query"] == "amud yomi"


@pytest.mark.asyncio
async def test_web_search_falls_back_to_env_key_when_no_tenant_credential(monkeypatch):
    tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="web_search",
        config_schema={
            "implementation": {
                "type": "builtin",
                "builtin": "web_search",
                "provider": "serper",
            }
        },
    )

    async def fake_load_tool(_self, _tool_id):
        return tool

    class FakeProvider:
        async def search(self, *, query: str, top_k: int = 5):
            return {"query": query, "provider": "serper", "results": [{"query": query, "top_k": top_k}]}

    def fake_provider_factory(_provider, *, api_key: str, endpoint=None, timeout_s: int = 15):
        assert api_key == "env-default-key"
        return FakeProvider()

    async def fake_get_by_provider(self, *, category, provider_key: str, provider_variant=None):
        _ = (category, provider_key, provider_variant)
        return None

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr("app.agent.executors.tool.create_web_search_provider", fake_provider_factory)
    monkeypatch.setattr("app.agent.executors.tool.CredentialsService.get_by_provider", fake_get_by_provider)
    monkeypatch.setenv("SERPER_API_KEY", "env-default-key")

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())
    result = await executor.execute(
        state={"context": {"query": "daf yomi news", "top_k": 2}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node"},
    )

    assert result["context"]["provider"] == "serper"
    assert result["context"]["query"] == "daf yomi news"


@pytest.mark.asyncio
async def test_json_transform_and_datetime_utils(monkeypatch):
    json_tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="json_transform",
        config_schema={"implementation": {"type": "builtin", "builtin": "json_transform"}},
    )
    datetime_tool = _make_tool(
        implementation_type="CUSTOM",
        builtin_key="datetime_utils",
        config_schema={"implementation": {"type": "builtin", "builtin": "datetime_utils", "operation": "diff"}},
    )

    async def fake_load_tool(_self, tool_id):
        return json_tool if str(tool_id) == str(json_tool.id) else datetime_tool

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)

    executor = ToolNodeExecutor(tenant_id=uuid4(), db=DummyDB())

    transformed = await executor.execute(
        state={
            "context": {
                "data": {"a": {"b": 7}, "c": "x"},
                "mapping": {"value": "a.b", "label": "c"},
            }
        },
        config={"tool_id": str(json_tool.id)},
        context={"node_id": "tool-node"},
    )
    assert transformed["context"]["result"] == {"value": 7, "label": "x"}

    diffed = await executor.execute(
        state={
            "context": {
                "operation": "diff",
                "value": "2026-02-10T10:00:00+00:00",
                "other": "2026-02-10T09:30:00+00:00",
                "unit": "minutes",
            }
        },
        config={"tool_id": str(datetime_tool.id)},
        context={"node_id": "tool-node"},
    )
    assert diffed["context"]["operation"] == "diff"
    assert diffed["context"]["result"] == 30
