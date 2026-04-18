from __future__ import annotations

import pytest

from app.services.opencode_server_client import OpenCodeServerClient


@pytest.mark.asyncio
async def test_create_session_and_submit_turn_route_via_sandbox_controller(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_URL", "http://sandbox-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    captured: dict[str, object] = {}

    class _FakeSandboxClient:
        async def create_session(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, selected_agent_contract=None):
            _ = selected_agent_contract
            captured["sandbox_id"] = sandbox_id
            captured["run_id"] = run_id
            captured["app_id"] = app_id
            captured["workspace_path"] = workspace_path
            captured["model_id"] = model_id
            return "sandbox-session-1"

        async def submit_turn(
            self,
            *,
            session_id,
            run_id,
            app_id,
            sandbox_id,
            workspace_path,
            model_id,
            prompt,
            recovery_messages=None,
            selected_agent_contract=None,
        ):
            _ = run_id, app_id, sandbox_id, workspace_path, model_id, selected_agent_contract
            captured["submit_session_id"] = session_id
            captured["prompt"] = prompt
            captured["messages"] = recovery_messages
            return "sandbox-turn-ref-1"

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        captured["endpoint_sandbox_id"] = sandbox_id
        captured["endpoint_workspace_path"] = workspace_path
        return _FakeSandboxClient(), workspace_path

    async def _fake_seed_custom_tools_and_context(**kwargs):
        _ = kwargs
        return None

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)
    monkeypatch.setattr(client, "_seed_custom_tools_and_context", _fake_seed_custom_tools_and_context)

    session_id = await client.create_session(
        run_id="run-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/workspace",
        model_id="openai/gpt-5",
    )
    turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/workspace",
        model_id="openai/gpt-5",
        prompt="hello",
        recovery_messages=[{"role": "user", "content": "hello"}],
    )

    assert session_id == "sandbox-session-1"
    assert turn_ref == "sandbox-turn-ref-1"
    assert captured["sandbox_id"] == "sandbox-1"
    assert captured["endpoint_workspace_path"] == "/workspace"
    assert captured["workspace_path"] == "/workspace"
    assert captured["model_id"] == "openai/gpt-5"
    assert captured["submit_session_id"] == "sandbox-session-1"


@pytest.mark.asyncio
async def test_stream_and_cancel_route_via_sandbox_controller(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_URL", "http://sandbox-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    client._sandbox_turn_ref_to_sandbox_id["sandbox-turn-ref-2"] = "sandbox-2"
    captured: dict[str, object] = {}

    class _FakeSandboxClient:
        async def stream_turn_events(self, *, session_id, turn_ref, workspace_path=None, sandbox_id=None):
            _ = workspace_path, sandbox_id
            assert session_id == "sandbox-session-2"
            assert turn_ref == "sandbox-turn-ref-2"
            yield {"event": "assistant.delta", "payload": {"content": "hello"}}
            yield {"event": "run.completed", "payload": {"status": "completed"}}

        async def cancel_turn(self, *, session_id, turn_ref, workspace_path=None, sandbox_id=None):
            _ = workspace_path, sandbox_id
            captured["cancel_session_id"] = session_id
            captured["cancel_turn_ref"] = turn_ref
            return True

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        captured["sandbox_id"] = sandbox_id
        captured["workspace_path"] = workspace_path
        return _FakeSandboxClient(), workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

    events = []
    async for event in client.stream_turn_events(session_id="sandbox-session-2", turn_ref="sandbox-turn-ref-2"):
        events.append(event)
    assert [event.get("event") for event in events] == ["assistant.delta", "run.completed"]

    client._sandbox_turn_ref_to_sandbox_id["sandbox-turn-ref-2"] = "sandbox-2"
    cancelled = await client.cancel_turn(session_id="sandbox-session-2", turn_ref="sandbox-turn-ref-2")
    assert cancelled is True
    assert captured["cancel_session_id"] == "sandbox-session-2"
    assert captured["cancel_turn_ref"] == "sandbox-turn-ref-2"


@pytest.mark.asyncio
async def test_cancel_routes_via_sandbox_controller_with_explicit_sandbox_id(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_URL", "http://sandbox-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    captured: dict[str, object] = {}

    class _FakeSandboxClient:
        async def cancel_turn(self, *, session_id, turn_ref, workspace_path=None, sandbox_id=None):
            _ = workspace_path, sandbox_id
            captured["session_id"] = session_id
            captured["turn_ref"] = turn_ref
            return True

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        captured["sandbox_id"] = sandbox_id
        return _FakeSandboxClient(), workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

    cancelled = await client.cancel_turn(
        session_id="sandbox-session-explicit",
        turn_ref="sandbox-turn-ref-explicit",
        sandbox_id="sandbox-explicit",
    )
    assert cancelled is True
    assert captured["sandbox_id"] == "sandbox-explicit"
    assert captured["session_id"] == "sandbox-session-explicit"
    assert captured["turn_ref"] == "sandbox-turn-ref-explicit"


@pytest.mark.asyncio
async def test_sandbox_controller_mode_detected_from_draft_dev_controller_url(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", raising=False)
    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_URL", raising=False)
    monkeypatch.setenv("APPS_DRAFT_DEV_CONTROLLER_URL", "http://draft-dev-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    assert client.is_enabled is True

    await client.ensure_healthy()


@pytest.mark.asyncio
async def test_sandbox_controller_mode_is_enabled_even_when_opencode_flag_off(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "0")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", raising=False)
    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_URL", raising=False)
    monkeypatch.setenv("APPS_DRAFT_DEV_CONTROLLER_URL", "http://draft-dev-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    assert client.is_enabled is True

    await client.ensure_healthy()


@pytest.mark.asyncio
async def test_sprite_backend_forces_sandbox_mode_even_when_legacy_controller_flag_is_off(monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "sprite")
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-test-token")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "0")
    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("APPS_DRAFT_DEV_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    assert client.is_enabled is True
    assert client._sandbox_runtime_mode_enabled() is True

    await client.ensure_healthy()
