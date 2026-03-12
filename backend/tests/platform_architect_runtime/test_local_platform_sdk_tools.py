from __future__ import annotations

import pytest

from app.services import platform_sdk_local_tools
from app.agent.execution.emitter import active_emitter


@pytest.mark.asyncio
async def test_local_platform_sdk_dispatch_forwards_tool_slug(monkeypatch):
    captured = {}

    def fake_execute(state, config, context):
        captured["state"] = state
        captured["config"] = config
        captured["context"] = context
        return {"result": {"status": "ok"}}

    monkeypatch.setattr(platform_sdk_local_tools.platform_sdk_handler, "execute", fake_execute)

    result = await platform_sdk_local_tools.platform_sdk_local_platform_agents(
        {
            "action": "agents.list",
            "payload": {"limit": 5},
            "context": {"tenant_id": "tenant-1", "grant_id": "45a51cee-f484-4a9b-96c7-94433fae0f3c"},
        }
    )

    assert result["result"]["status"] == "ok"
    assert captured["state"] == {}
    assert captured["config"]["tool_slug"] == "platform-agents"
    assert captured["context"]["tool_slug"] == "platform-agents"
    assert captured["context"]["inputs"]["tool_slug"] == "platform-agents"
    assert captured["context"]["inputs"]["action"] == "agents.list"
    assert callable(captured["context"]["auth"]["mint_token"])


@pytest.mark.asyncio
async def test_local_platform_sdk_dispatch_emits_internal_trace_events(monkeypatch):
    emitted: list[tuple[str, dict]] = []

    class _Emitter:
        def emit_internal_event(self, event_name, data, *, node_id=None, category=None, visibility=None):
            del node_id, visibility
            emitted.append((event_name, {"category": category, **data}))

    monkeypatch.setattr(
        platform_sdk_local_tools.platform_sdk_handler,
        "execute",
        lambda state, config, context: {"context": {"action": "agents.list", "errors": [], "result": {"items": []}}},
    )

    token = active_emitter.set(_Emitter())
    try:
        await platform_sdk_local_tools.platform_sdk_local_platform_agents(
            {
                "action": "agents.list",
                "payload": {"limit": 5},
                "context": {"tenant_id": "tenant-1", "grant_id": "45a51cee-f484-4a9b-96c7-94433fae0f3c"},
            }
        )
    finally:
        active_emitter.reset(token)

    event_names = [name for name, _data in emitted]
    assert "platform_sdk_local.dispatch_prepared" in event_names
    assert "platform_sdk_local.dispatch_completed" in event_names
    prepared = next(data for name, data in emitted if name == "platform_sdk_local.dispatch_prepared")
    auth_preview = prepared["runtime_context_preview"]["auth"]
    assert auth_preview["mint_token"] == "<callable:mint_token>"
