import importlib

import pytest


@pytest.mark.asyncio
async def test_legacy_chat_agent_initializes_lazily(monkeypatch):
    import app.agent as agent_pkg
    import app.api.routers.agent as legacy_router

    calls: list[str] = []
    dummy_agent = object()

    def fake_create_agent(_config):
        calls.append("called")
        return dummy_agent

    monkeypatch.setattr(agent_pkg.AgentFactory, "create_agent", staticmethod(fake_create_agent))

    # Reload module to validate import-time behavior.
    reloaded_router = importlib.reload(legacy_router)

    # No eager construction at import.
    assert calls == []

    first = await reloaded_router.get_chat_agent()
    second = await reloaded_router.get_chat_agent()

    assert first is dummy_agent
    assert second is dummy_agent
    assert len(calls) == 1
