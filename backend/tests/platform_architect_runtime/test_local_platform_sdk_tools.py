from __future__ import annotations

import pytest

from app.services import platform_sdk_local_tools


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
