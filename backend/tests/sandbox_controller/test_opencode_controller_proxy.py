from __future__ import annotations

import pytest

from app.services.opencode_server_client import OpenCodeServerClient


@pytest.mark.asyncio
async def test_start_run_routes_via_sandbox_controller(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_URL", "http://sandbox-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    captured: dict[str, object] = {}

    async def _fake_start_opencode_run(
        *,
        sandbox_id: str,
        run_id: str,
        app_id: str,
        workspace_path: str,
        model_id: str,
        prompt: str,
        messages: list[dict[str, str]],
    ):
        captured["sandbox_id"] = sandbox_id
        captured["run_id"] = run_id
        captured["app_id"] = app_id
        captured["workspace_path"] = workspace_path
        captured["model_id"] = model_id
        captured["prompt"] = prompt
        captured["messages"] = messages
        return {"run_ref": "sandbox-run-ref-1"}

    monkeypatch.setattr(client._sandbox_runtime_client, "start_opencode_run", _fake_start_opencode_run)

    run_ref = await client.start_run(
        run_id="run-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/workspace",
        model_id="openai/gpt-5",
        prompt="hello",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert run_ref == "sandbox-run-ref-1"
    assert captured["sandbox_id"] == "sandbox-1"
    assert captured["workspace_path"] == "/workspace"
    assert captured["model_id"] == "openai/gpt-5"


@pytest.mark.asyncio
async def test_stream_and_cancel_route_via_sandbox_controller(monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_URL", "http://sandbox-controller.local")
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)

    client = OpenCodeServerClient.from_env()
    client._sandbox_run_ref_to_sandbox_id["sandbox-run-ref-2"] = "sandbox-2"

    async def _fake_stream_opencode_events(*, sandbox_id: str, run_ref: str):
        assert sandbox_id == "sandbox-2"
        assert run_ref == "sandbox-run-ref-2"
        yield {"event": "assistant.delta", "payload": {"content": "hello"}}
        yield {"event": "run.completed", "payload": {"status": "completed"}}

    async def _fake_cancel_opencode_run(*, sandbox_id: str, run_ref: str):
        assert sandbox_id == "sandbox-2"
        assert run_ref == "sandbox-run-ref-2"
        return {"cancelled": True}

    monkeypatch.setattr(client._sandbox_runtime_client, "stream_opencode_events", _fake_stream_opencode_events)
    monkeypatch.setattr(client._sandbox_runtime_client, "cancel_opencode_run", _fake_cancel_opencode_run)

    events = []
    async for event in client.stream_run_events(run_ref="sandbox-run-ref-2"):
        events.append(event)
    assert [event.get("event") for event in events] == ["assistant.delta", "run.completed"]

    client._sandbox_run_ref_to_sandbox_id["sandbox-run-ref-2"] = "sandbox-2"
    cancelled = await client.cancel_run(run_ref="sandbox-run-ref-2")
    assert cancelled is True


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
