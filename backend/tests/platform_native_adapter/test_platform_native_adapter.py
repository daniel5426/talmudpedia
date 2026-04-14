from __future__ import annotations

import pytest

from app.services import platform_native_tools


@pytest.mark.asyncio
async def test_native_adapter_passes_runtime_context_and_hides_debug_meta(monkeypatch):
    captured = {}

    async def fake_handler(runtime):
        captured["tool_slug"] = runtime.tool_slug
        captured["action"] = runtime.action
        captured["tenant_id"] = runtime.runtime_context.get("tenant_id")
        return {"status": "ok"}

    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setitem(platform_native_tools._ACTION_HANDLERS, "agents.list", fake_handler)

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "agents.list",
            "payload": {"limit": 5},
            "__tool_runtime_context__": {"tenant_id": "tenant-1", "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"]["status"] == "ok"
    assert captured == {"tool_slug": "platform-agents", "action": "agents.list", "tenant_id": "tenant-1"}
    assert "trace_version" not in result["meta"]


@pytest.mark.asyncio
async def test_native_adapter_rejects_removed_alias_actions(monkeypatch):
    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "create_agent",
            "payload": {},
            "__tool_runtime_context__": {"tenant_id": "tenant-1", "scopes": ["*"]},
        }
    )

    assert result["errors"][0]["code"] == "SCOPE_DENIED"
    assert result["action"] == "create_agent"
