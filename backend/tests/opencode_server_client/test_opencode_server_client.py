import json

import httpx
import pytest

from app.services.opencode_server_client import (
    OpenCodeServerClient,
    OpenCodeServerClientConfig,
    OpenCodeServerClientError,
)
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError
from app.services.published_app_templates import OPENCODE_BOOTSTRAP_CONTEXT_PATH


def _client() -> OpenCodeServerClient:
    return OpenCodeServerClient(
        OpenCodeServerClientConfig(
            enabled=True,
            base_url="http://opencode.local",
            api_key=None,
            request_timeout_seconds=10.0,
            connect_timeout_seconds=2.0,
            health_cache_seconds=5,
        )
    )


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, handler):
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


def _sse_payload(event_type: str, properties: dict[str, object]) -> str:
    return json.dumps({"directory": "/tmp/workspace", "payload": {"type": event_type, "properties": properties}})


def test_build_official_session_permission_rules_includes_workspace_patterns():
    rules = OpenCodeServerClient._build_official_session_permission_rules("/tmp/workspace-a")
    assert rules
    assert all(item.get("permission") == "external_directory" for item in rules)
    patterns = {str(item.get("pattern") or "") for item in rules}
    assert "/tmp/workspace-a" in patterns
    assert "/tmp/workspace-a/*" in patterns


@pytest.mark.asyncio
async def test_official_mode_seeds_custom_tools_before_start(monkeypatch: pytest.MonkeyPatch, tmp_path):
    workspace_path = str(tmp_path / "workspace")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-seed"}})
        if request.url.path == "/session/sess-seed/prompt_async":
            return httpx.Response(404, json={"error": "unsupported"})
        if request.url.path == "/session/sess-seed/message":
            payload = json.loads(request.content.decode("utf-8"))
            text = str((payload.get("parts") or [{}])[0].get("text") or "")
            assert "run_id: run-mcp" in text
            assert "app_id: app-mcp" in text
            assert "coding_agent_get_agent_integration_contract" in text
            return httpx.Response(200, json={"success": True, "data": {"parts": [{"type": "text", "text": "OK"}]}})
        if request.url.path == "/mcp":
            raise AssertionError("OpenCode MCP should not be called after custom-tool cutover.")
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-mcp",
        app_id="app-mcp",
        sandbox_id="sandbox-1",
        workspace_path=workspace_path,
        model_id="",
        prompt="use tools",
        messages=[{"role": "user", "content": "use tools"}],
        selected_agent_contract={"agent": {"id": "agent-1"}},
    )
    assert run_ref == "sess-seed"
    assert (tmp_path / "workspace" / ".opencode" / "package.json").exists()
    assert (
        tmp_path
        / "workspace"
        / ".opencode"
        / "tools"
        / "coding_agent_get_agent_integration_contract.ts"
    ).exists()
    context_file = tmp_path / "workspace" / OPENCODE_BOOTSTRAP_CONTEXT_PATH
    assert context_file.exists()
    context_payload = json.loads(context_file.read_text(encoding="utf-8"))
    assert context_payload["run_id"] == "run-mcp"
    assert context_payload["app_id"] == "app-mcp"
    assert context_payload["selected_agent_contract"]["agent"]["id"] == "agent-1"


@pytest.mark.asyncio
async def test_official_mode_start_run_buffers_assistant_events(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-1"}})
        if request.url.path == "/session/sess-1/message":
            payload = json.loads(request.content.decode("utf-8"))
            assert str(payload.get("messageID") or "").startswith("msg-")
            assert payload.get("model") == {"providerID": "openai", "modelID": "gpt-5"}
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "info": {"id": "msg-1"},
                        "parts": [
                            {"type": "text", "text": "Applied the requested change."},
                            {"type": "meta", "payload": {"part": {"content": "Build is clean."}}},
                        ],
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="openai/gpt-5",
        prompt="Fix the TS issue",
        messages=[{"role": "user", "content": "Fix the TS issue"}],
    )
    assert run_ref == "sess-1"

    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    delta_text = "\n".join(str(item.get("payload", {}).get("content") or "") for item in events if item.get("event") == "assistant.delta")
    assert "Applied the requested change." in delta_text
    assert "Build is clean." in delta_text
    assert any(item.get("event") == "run.completed" for item in events)


@pytest.mark.asyncio
async def test_sandbox_mode_seeds_custom_tools_before_start(monkeypatch: pytest.MonkeyPatch):
    class SandboxClientStub:
        is_remote_enabled = True

        def __init__(self) -> None:
            self.writes: list[tuple[str, str]] = []
            self.start_calls = 0

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            self.writes.append((path, content))
            return {"sandbox_id": sandbox_id, "path": path, "status": "written"}

        async def start_opencode_run(self, **kwargs):
            self.start_calls += 1
            return {"run_ref": "sandbox-run-1"}

    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    stub = SandboxClientStub()
    client = _client()
    client._sandbox_runtime_client = stub

    run_ref = await client.start_run(
        run_id="run-sandbox-seed",
        app_id="app-1",
        sandbox_id="sandbox-seed",
        workspace_path="/workspace",
        model_id="",
        prompt="seed",
        messages=[{"role": "user", "content": "seed"}],
        selected_agent_contract={"agent": {"id": "agent-1"}},
    )
    assert run_ref == "sandbox-run-1"
    assert stub.start_calls == 1
    seeded_paths = {path for path, _ in stub.writes}
    assert ".opencode/package.json" in seeded_paths
    assert ".opencode/tools/coding_agent_get_agent_integration_contract.ts" in seeded_paths
    assert ".opencode/tools/coding_agent_describe_selected_agent_contract.ts" in seeded_paths
    assert OPENCODE_BOOTSTRAP_CONTEXT_PATH in seeded_paths


@pytest.mark.asyncio
async def test_sandbox_mode_fails_closed_when_seed_write_fails(monkeypatch: pytest.MonkeyPatch):
    class FailingSandboxClientStub:
        is_remote_enabled = True

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            raise PublishedAppDraftDevRuntimeClientError("write failed")

        async def start_opencode_run(self, **kwargs):
            raise AssertionError("start_opencode_run should not be called when seeding fails")

    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    client = _client()
    client._sandbox_runtime_client = FailingSandboxClientStub()

    with pytest.raises(OpenCodeServerClientError) as exc:
        await client.start_run(
            run_id="run-seed-fail",
            app_id="app-1",
            sandbox_id="sandbox-fail",
            workspace_path="/workspace",
            model_id="",
            prompt="seed",
            messages=[{"role": "user", "content": "seed"}],
        )
    assert "Failed to seed OpenCode custom tools in sandbox" in str(exc.value)


@pytest.mark.asyncio
async def test_official_mode_fails_closed_when_workspace_path_is_invalid():
    client = _client()
    with pytest.raises(OpenCodeServerClientError) as exc:
        await client.start_run(
            run_id="run-invalid-workspace",
            app_id="app-1",
            sandbox_id="sandbox-1",
            workspace_path="relative/path",
            model_id="",
            prompt="reply",
            messages=[{"role": "user", "content": "reply"}],
        )
    assert "workspace_path must be absolute" in str(exc.value)


@pytest.mark.asyncio
async def test_official_mode_emits_tool_events_from_assistant_parts(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-tools"}})
        if request.url.path == "/session/sess-tools/message":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "info": {"id": "msg-tools"},
                        "parts": [
                            {
                                "type": "tool",
                                "tool": "read",
                                "callID": "call-1",
                                "state": {
                                    "status": "completed",
                                    "input": {"filePath": "/tmp/a.txt"},
                                    "output": {"text": "ok"},
                                },
                            },
                            {"type": "text", "text": "Done."},
                        ],
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-tools",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Do it",
        messages=[{"role": "user", "content": "Do it"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert [item.get("event") for item in events] == [
        "tool.started",
        "tool.completed",
        "assistant.delta",
        "run.completed",
    ]


@pytest.mark.asyncio
async def test_official_mode_global_event_stream_emits_tool_events_and_incremental_text(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-global-events"
    assistant_message_id = "msg-assistant-1"
    user_message_id = "msg-user-1"
    text_part_id = "part-text-1"

    global_events = [
        ("message.updated", {"info": {"id": user_message_id, "sessionID": session_id, "role": "user"}}),
        (
            "message.part.updated",
            {
                "part": {
                    "id": "part-tool-1",
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "tool",
                    "tool": "read",
                    "callID": "call-1",
                    "state": {"status": "pending", "input": {}},
                }
            },
        ),
        (
            "message.updated",
            {"info": {"id": assistant_message_id, "sessionID": session_id, "role": "assistant", "parentID": user_message_id}},
        ),
        (
            "message.part.updated",
            {
                "part": {
                    "id": "part-tool-1",
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "tool",
                    "tool": "read",
                    "callID": "call-1",
                    "state": {"status": "running", "input": {"filePath": "/tmp/a.txt"}},
                }
            },
        ),
        (
            "message.part.updated",
            {
                "part": {
                    "id": "part-tool-1",
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "tool",
                    "tool": "read",
                    "callID": "call-1",
                    "state": {"status": "completed", "input": {"filePath": "/tmp/a.txt"}, "output": {"text": "ok"}},
                }
            },
        ),
        (
            "message.part.updated",
            {
                "part": {
                    "id": text_part_id,
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "text",
                    "text": "He",
                }
            },
        ),
        (
            "message.part.delta",
            {
                "sessionID": session_id,
                "messageID": assistant_message_id,
                "partID": text_part_id,
                "field": "text",
                "delta": "llo",
            },
        ),
        ("session.idle", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/prompt_async":
            return httpx.Response(204, text="")
        if request.url.path == "/global/event":
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/message" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {
                            "id": assistant_message_id,
                            "sessionID": session_id,
                            "role": "assistant",
                            "parentID": user_message_id,
                            "time": {"created": 1, "completed": 2},
                        },
                        "parts": [{"id": text_part_id, "type": "text", "text": "Hello"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-global-stream",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with hello",
        messages=[{"role": "user", "content": "Reply with hello"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(item.get("event") == "tool.started" and item.get("payload", {}).get("tool") == "read" for item in events)
    assert any(item.get("event") == "tool.completed" and item.get("payload", {}).get("tool") == "read" for item in events)
    assistant_text = "".join(str(item.get("payload", {}).get("content") or "") for item in events if item.get("event") == "assistant.delta")
    assert assistant_text == "Hello"
    assert events[-1].get("event") == "run.completed"


@pytest.mark.asyncio
async def test_official_mode_global_event_stream_skips_reasoning_deltas(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-global-reasoning"
    assistant_message_id = "msg-assistant-r"
    user_message_id = "msg-user-r"
    text_part_id = "part-text-r"
    reasoning_part_id = "part-reasoning-r"

    global_events = [
        ("message.updated", {"info": {"id": user_message_id, "sessionID": session_id, "role": "user"}}),
        (
            "message.updated",
            {"info": {"id": assistant_message_id, "sessionID": session_id, "role": "assistant", "parentID": user_message_id}},
        ),
        (
            "message.part.updated",
            {
                "part": {
                    "id": reasoning_part_id,
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "reasoning",
                    "text": "",
                }
            },
        ),
        (
            "message.part.delta",
            {
                "sessionID": session_id,
                "messageID": assistant_message_id,
                "partID": reasoning_part_id,
                "field": "text",
                "delta": "secret-thought",
            },
        ),
        (
            "message.part.updated",
            {
                "part": {
                    "id": text_part_id,
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "text",
                    "text": "done",
                }
            },
        ),
        ("session.idle", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/prompt_async":
            return httpx.Response(204, text="")
        if request.url.path == "/global/event":
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/message" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {
                            "id": assistant_message_id,
                            "sessionID": session_id,
                            "role": "assistant",
                            "parentID": user_message_id,
                            "time": {"created": 1, "completed": 2},
                        },
                        "parts": [{"id": text_part_id, "type": "text", "text": "done"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-global-reasoning",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with done",
        messages=[{"role": "user", "content": "Reply with done"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assistant_chunks = [str(item.get("payload", {}).get("content") or "") for item in events if item.get("event") == "assistant.delta"]
    assert "".join(assistant_chunks) == "done"
    assert "secret-thought" not in "".join(assistant_chunks)
    assert events[-1].get("event") == "run.completed"


@pytest.mark.asyncio
async def test_official_mode_session_create_includes_workspace_permission_rules(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            payload = json.loads(request.content.decode("utf-8"))
            permission = payload.get("permission")
            assert isinstance(permission, list) and permission
            patterns = {str(item.get("pattern") or "") for item in permission if isinstance(item, dict)}
            assert "/private/tmp/talmudpedia-draft-dev/sandbox-123" in patterns
            assert "/private/tmp/talmudpedia-draft-dev/sandbox-123/*" in patterns
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-perm"}})
        if request.url.path == "/session/sess-perm/message":
            return httpx.Response(200, json={"success": True, "data": {"parts": [{"type": "text", "text": "OK"}]}})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-permission-rules",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/private/tmp/talmudpedia-draft-dev/sandbox-123",
        model_id="",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(item.get("event") == "assistant.delta" for item in events)


@pytest.mark.asyncio
async def test_official_mode_unwraps_success_false_error_payload(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-2"}})
        if request.url.path == "/session/sess-2/message":
            return httpx.Response(
                200,
                json={
                    "success": False,
                    "error": [{"message": "No default model configured for this OpenCode server."}],
                    "data": {"messageID": "msg-2"},
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    with pytest.raises(OpenCodeServerClientError, match="No default model configured"):
        await client.start_run(
            run_id="run-2",
            app_id="app-1",
            sandbox_id="sandbox-1",
            workspace_path="/tmp/sandbox-1",
            model_id="",
            prompt="Fix the TS issue",
            messages=[{"role": "user", "content": "Fix the TS issue"}],
        )


@pytest.mark.asyncio
async def test_legacy_mode_fallback_when_official_health_unavailable(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(404, text="not found")
        if request.url.path == "/health":
            return httpx.Response(200, text="ok")
        if request.url.path == "/v1/runs":
            return httpx.Response(200, json={"run_ref": "legacy-run-1"})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-legacy",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Fix the TS issue",
        messages=[{"role": "user", "content": "Fix the TS issue"}],
    )
    assert run_ref == "legacy-run-1"


@pytest.mark.asyncio
async def test_official_mode_missing_text_emits_failed_buffer_event(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-3"}})
        if request.url.path == "/session/sess-3/message":
            return httpx.Response(200, json={"success": True, "data": {"info": {"id": "msg-3"}}})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-3",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Fix the TS issue",
        messages=[{"role": "user", "content": "Fix the TS issue"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert len(events) == 1
    assert events[0]["event"] == "run.failed"
    assert "did not include assistant text" in str(events[0]["payload"].get("error") or "")


@pytest.mark.asyncio
async def test_official_mode_model_object_shape_prevents_invalid_type_error(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-model"}})
        if request.url.path == "/session/sess-model/message":
            payload = json.loads(request.content.decode("utf-8"))
            model = payload.get("model")
            assert isinstance(model, dict)
            assert model.get("providerID") == "openai"
            assert model.get("modelID") == "gpt-5.2-2025-12-11"
            return httpx.Response(200, json={"success": True, "data": {"parts": [{"type": "text", "text": "OK"}]}})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()
    run_ref = await client.start_run(
        run_id="run-model-shape",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="openai/gpt-5.2-2025-12-11",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(item.get("event") == "assistant.delta" for item in events)


@pytest.mark.asyncio
async def test_official_mode_embedded_assistant_error_is_raised(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-4"}})
        if request.url.path == "/session/sess-4/message":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "info": {
                            "role": "assistant",
                            "error": {
                                "name": "UnknownError",
                                "data": {
                                    "message": "Error: Missing or invalid provider credentials.",
                                },
                            },
                        }
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    with pytest.raises(OpenCodeServerClientError, match="Missing or invalid provider credentials"):
        await client.start_run(
            run_id="run-4",
            app_id="app-1",
            sandbox_id="sandbox-1",
            workspace_path="/tmp/sandbox-1",
            model_id="",
            prompt="Fix the TS issue",
            messages=[{"role": "user", "content": "Fix the TS issue"}],
        )


@pytest.mark.asyncio
async def test_official_mode_embedded_error_redacts_private_key(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-5"}})
        if request.url.path == "/session/sess-5/message":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "info": {
                            "error": {
                                "data": {
                                    "message": 'Error opening credentials: {"private_key":"-----BEGIN PRIVATE KEY-----ABC-----END PRIVATE KEY-----"}'
                                }
                            }
                        }
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    with pytest.raises(OpenCodeServerClientError) as exc:
        await client.start_run(
            run_id="run-5",
            app_id="app-1",
            sandbox_id="sandbox-1",
            workspace_path="/tmp/sandbox-1",
            model_id="",
            prompt="Fix the TS issue",
            messages=[{"role": "user", "content": "Fix the TS issue"}],
        )
    text = str(exc.value)
    assert "[REDACTED_PRIVATE_KEY]" in text or '"private_key":"[REDACTED]"' in text
    assert "BEGIN PRIVATE KEY" not in text


@pytest.mark.asyncio
async def test_official_mode_preflight_invalid_model_raises_clear_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_MODEL_PREFLIGHT_ENABLED", "1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-preflight"}})
        if request.url.path == "/session/sess-preflight/init":
            return httpx.Response(
                400,
                json={
                    "name": "ProviderModelNotFoundError",
                    "data": {
                        "providerID": "openai",
                        "modelID": "gpt-5.2-2025-12-11",
                        "suggestions": [],
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    with pytest.raises(OpenCodeServerClientError, match="model is unavailable"):
        await client.start_run(
            run_id="run-preflight",
            app_id="app-1",
            sandbox_id="sandbox-1",
            workspace_path="/tmp/sandbox-1",
            model_id="openai/gpt-5.2-2025-12-11",
            prompt="Reply with OK",
            messages=[{"role": "user", "content": "Reply with OK"}],
        )


@pytest.mark.asyncio
async def test_official_mode_empty_message_response_polls_session_messages(monkeypatch: pytest.MonkeyPatch):
    state: dict[str, str | int] = {"message_id": "", "poll_count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-poll"}})
        if request.url.path == "/session/sess-poll/init":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/session/sess-poll/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            state["message_id"] = str(payload.get("messageID") or "")
            return httpx.Response(200, content=b"")
        if request.url.path == "/session/sess-poll/message" and request.method == "GET":
            state["poll_count"] = int(state["poll_count"]) + 1
            if int(state["poll_count"]) < 2:
                return httpx.Response(
                    200,
                    json=[
                        {
                            "info": {"role": "user", "id": state["message_id"]},
                            "parts": [{"type": "text", "text": "request"}],
                        }
                    ],
                )
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {"role": "assistant", "parentID": state["message_id"], "id": "assistant-1"},
                        "parts": [{"type": "text", "text": "Polled OK"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-poll",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="openai/gpt-5",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(item.get("event") == "assistant.delta" and "Polled OK" in str(item.get("payload", {}).get("content")) for item in events)


@pytest.mark.asyncio
async def test_official_mode_empty_message_response_polls_wrapped_messages_payload(monkeypatch: pytest.MonkeyPatch):
    state: dict[str, str] = {"message_id": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-wrapped-poll"}})
        if request.url.path == "/session/sess-wrapped-poll/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            state["message_id"] = str(payload.get("messageID") or "")
            return httpx.Response(200, content=b"")
        if request.url.path == "/session/sess-wrapped-poll/message" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "info": {"role": "assistant", "parentID": state["message_id"], "id": "assistant-wrapped"},
                            "parts": [{"type": "text", "text": "Wrapped payload OK"}],
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-wrapped-poll",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(
        item.get("event") == "assistant.delta" and "Wrapped payload OK" in str(item.get("payload", {}).get("content"))
        for item in events
    )


@pytest.mark.asyncio
async def test_official_mode_poll_accepts_assistant_message_without_parent_id(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-no-parent"}})
        if request.url.path == "/session/sess-no-parent/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
        if request.url.path == "/session/sess-no-parent/message" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {"role": "assistant", "id": "assistant-no-parent"},
                        "parts": [{"type": "text", "text": "No parent id but valid assistant response"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-no-parent",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(
        item.get("event") == "assistant.delta"
        and "No parent id but valid assistant response" in str(item.get("payload", {}).get("content"))
        for item in events
    )


@pytest.mark.asyncio
async def test_request_error_without_message_includes_exception_class(monkeypatch: pytest.MonkeyPatch):
    class _Boom(RuntimeError):
        def __str__(self) -> str:
            return ""

    async def _raise(*args, **kwargs):
        raise _Boom()

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        request = _raise

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    client = _client()

    with pytest.raises(OpenCodeServerClientError, match="OpenCode request failed: _Boom"):
        await client._request("GET", "/global/health", json_payload={}, retries=0)


@pytest.mark.asyncio
async def test_official_mode_post_message_read_timeout_falls_back_to_polling(monkeypatch: pytest.MonkeyPatch):
    state: dict[str, str] = {"message_id": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-timeout"}})
        if request.url.path == "/session/sess-timeout/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            state["message_id"] = str(payload.get("messageID") or "")
            raise httpx.ReadTimeout("timed out")
        if request.url.path == "/session/sess-timeout/message" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {"role": "assistant", "parentID": state["message_id"], "id": "assistant-timeout"},
                        "parts": [{"type": "text", "text": "Recovered after timeout"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-timeout",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(
        item.get("event") == "assistant.delta" and "Recovered after timeout" in str(item.get("payload", {}).get("content"))
        for item in events
    )


@pytest.mark.asyncio
async def test_official_mode_prefers_assistant_candidate_with_text(monkeypatch: pytest.MonkeyPatch):
    state: dict[str, str] = {"message_id": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-candidates"}})
        if request.url.path == "/session/sess-candidates/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            state["message_id"] = str(payload.get("messageID") or "")
            return httpx.Response(200, content=b"")
        if request.url.path == "/session/sess-candidates/message" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {"role": "assistant", "parentID": state["message_id"], "id": "assistant-done"},
                        "parts": [{"type": "text", "text": "Earlier completed text"}],
                    },
                    {
                        "info": {"role": "assistant", "parentID": state["message_id"], "id": "assistant-latest"},
                        "parts": [{"type": "step-start"}],
                    },
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-candidates",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with OK",
        messages=[{"role": "user", "content": "Reply with OK"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(
        item.get("event") == "assistant.delta" and "Earlier completed text" in str(item.get("payload", {}).get("content"))
        for item in events
    )
