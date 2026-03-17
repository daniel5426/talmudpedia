from __future__ import annotations

import pytest

from app.services import platform_native_tools


@pytest.mark.asyncio
async def test_native_platform_dispatch_passes_runtime_context(monkeypatch):
    captured = {}

    async def fake_handler(runtime):
        captured["tool_slug"] = runtime.tool_slug
        captured["action"] = runtime.action
        captured["tenant_id"] = runtime.runtime_context.get("tenant_id")
        captured["token"] = runtime.runtime_context.get("token")
        return {"status": "ok"}

    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def commit(self):
            return None

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setitem(platform_native_tools._ACTION_HANDLERS, "agents.list", fake_handler)

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "agents.list",
            "payload": {"limit": 5},
            "__tool_runtime_context__": {
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "token": "bearer-123",
            },
        }
    )

    assert result["result"]["status"] == "ok"
    assert captured["tool_slug"] == "platform-agents"
    assert captured["action"] == "agents.list"
    assert captured["tenant_id"] == "tenant-1"
    assert captured["token"] == "bearer-123"


@pytest.mark.asyncio
async def test_native_platform_dispatch_rejects_tool_action_mismatch(monkeypatch):
    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def commit(self):
            return None

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "artifacts.list",
            "payload": {},
            "__tool_runtime_context__": {"tenant_id": "tenant-1", "requested_scopes": ["*"]},
        }
    )

    assert result["errors"][0]["code"] == "SCOPE_DENIED"
