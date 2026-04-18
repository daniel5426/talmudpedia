import json

import httpx
import pytest

from app.services.published_app_sandbox_backend import PublishedAppSandboxBackendConfig
from app.services.published_app_sandbox_backend_sprite import SpriteSandboxBackend
from app.services.opencode_server_client import (
    OpenCodeServerClient,
    OpenCodeServerClientConfig,
    OpenCodeServerClientError,
)
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError
from app.services.published_app_templates import OPENCODE_BOOTSTRAP_CONTEXT_PATH


def _client(*, sandbox_controller_mode_override: bool | None = False) -> OpenCodeServerClient:
    return OpenCodeServerClient(
        OpenCodeServerClientConfig(
            enabled=True,
            base_url="http://opencode.local",
            api_key=None,
            request_timeout_seconds=10.0,
            connect_timeout_seconds=2.0,
            health_cache_seconds=5,
            sandbox_controller_mode_override=sandbox_controller_mode_override,
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
    external_directory_rules = [item for item in rules if item.get("permission") == "external_directory"]
    assert external_directory_rules
    assert any(item.get("permission") == "question" and item.get("pattern") == "*" for item in rules)
    patterns = {str(item.get("pattern") or "") for item in external_directory_rules}
    assert "/tmp/workspace-a" in patterns
    assert "/tmp/workspace-a/*" in patterns


def test_extract_session_id_from_global_event_properties_recurses_nested_payloads():
    properties = {
        "message": {
            "info": {
                "sessionID": "ses_nested_session_1",
            }
        }
    }

    assert (
        OpenCodeServerClient._extract_session_id_from_global_event_properties(properties)
        == "ses_nested_session_1"
    )


def test_merge_official_extra_headers_adds_encoded_directory_header():
    headers = OpenCodeServerClient._merge_official_extra_headers(
        {"X-Test": "1"},
        workspace_path="/home/sprite/app",
    )

    assert headers == {
        "X-Test": "1",
        "x-opencode-directory": "%2Fhome%2Fsprite%2Fapp",
    }


def test_normalize_message_and_part_ids_use_official_prefixes():
    message_id = OpenCodeServerClient.normalize_message_id("msg-custom")
    parts = OpenCodeServerClient.normalize_request_parts([{"type": "text", "text": "hello"}])

    assert message_id.startswith("msg_")
    assert len(message_id) > len("msg_")
    assert parts[0]["id"].startswith("prt_")


@pytest.mark.asyncio
async def test_official_mode_seeds_custom_tools_before_start(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_SEED_BOOTSTRAP_ON_RUN_START", "1")
    workspace_path = str(tmp_path / "workspace")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-seed"}})
        if request.url.path == "/session/sess-seed/message":
            payload = json.loads(request.content.decode("utf-8"))
            text = str((payload.get("parts") or [{}])[0].get("text") or "")
            assert "run_id: run-mcp" in text
            assert "app_id: app-mcp" in text
            assert "read_agent_context" in text
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
        / "read_agent_context.ts"
    ).exists()
    context_file = tmp_path / "workspace" / OPENCODE_BOOTSTRAP_CONTEXT_PATH
    assert context_file.exists()
    context_payload = json.loads(context_file.read_text(encoding="utf-8"))
    assert context_payload["context_version"] == "1"
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
async def test_host_mode_can_skip_workspace_bootstrap(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": "sess-skip-bootstrap"}})
        if request.url.path == "/session/sess-skip-bootstrap/message":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "info": {"id": "msg-skip-bootstrap"},
                        "parts": [{"type": "text", "text": "OK"}],
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = OpenCodeServerClient(
        OpenCodeServerClientConfig(
            enabled=True,
            base_url="http://opencode.local",
            api_key=None,
            request_timeout_seconds=10.0,
            connect_timeout_seconds=2.0,
            health_cache_seconds=5,
            sandbox_controller_mode_override=False,
            skip_workspace_bootstrap=True,
        )
    )

    run_ref = await client.start_run(
        run_id="run-skip-bootstrap",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/workspace/.talmudpedia/stage/shared/workspace",
        model_id="",
        prompt="reply",
        messages=[{"role": "user", "content": "reply"}],
    )

    assert run_ref == "sess-skip-bootstrap"


@pytest.mark.asyncio
async def test_sprite_inner_opencode_client_skips_host_workspace_bootstrap(monkeypatch: pytest.MonkeyPatch):
    backend = SpriteSandboxBackend(
        PublishedAppSandboxBackendConfig(
            backend="sprite",
            controller_url=None,
            controller_token=None,
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
            preview_proxy_base_path="/public/apps-builder/draft-dev/sessions",
            e2b_template=None,
            e2b_template_tag=None,
            e2b_timeout_seconds=1800,
            e2b_workspace_path="/workspace",
            e2b_preview_port=4173,
            e2b_opencode_port=4141,
            e2b_secure=True,
            e2b_allow_internet_access=True,
            e2b_auto_pause=False,
            sprite_api_base_url="https://api.sprites.dev",
            sprite_api_token="sprite-token",
            sprite_name_prefix="app-builder",
            sprite_workspace_path="/home/sprite/app",
            sprite_stage_workspace_path="/home/sprite/.talmudpedia/stage/current/workspace",
            sprite_publish_workspace_path="/home/sprite/.talmudpedia/publish/current/workspace",
            sprite_preview_port=8080,
            sprite_opencode_port=4141,
            sprite_preview_service_name="builder-preview",
            sprite_opencode_service_name="opencode",
            sprite_opencode_command=None,
            sprite_command_timeout_seconds=900,
            sprite_retention_seconds=21600,
            sprite_network_policy=None,
        )
    )

    class _TunnelManagerStub:
        async def ensure_tunnel(self, *, api_base_url: str, api_token: str, sprite_name: str, remote_host: str, remote_port: int) -> str:
            assert api_base_url == "https://api.sprites.dev"
            assert api_token == "sprite-token"
            assert sprite_name == "sprite-app-1"
            assert remote_host == "127.0.0.1"
            assert remote_port == 4141
            return "http://127.0.0.1:40141"

    from app.services import published_app_sandbox_backend_sprite as sprite_backend_module

    async def fake_ensure_opencode_service(*, sprite_name: str) -> None:
        assert sprite_name == "sprite-app-1"

    monkeypatch.setattr(backend, "_ensure_opencode_service", fake_ensure_opencode_service)
    monkeypatch.setattr(sprite_backend_module, "get_sprite_proxy_tunnel_manager", lambda: _TunnelManagerStub())

    client = await backend._build_opencode_client(sandbox_id="sprite-app-1")

    assert client._config.base_url == "http://127.0.0.1:40141"
    assert client._config.skip_workspace_bootstrap is True


@pytest.mark.asyncio
async def test_sprite_write_file_streams_content_over_stdin(monkeypatch: pytest.MonkeyPatch):
    backend = SpriteSandboxBackend(
        PublishedAppSandboxBackendConfig(
            backend="sprite",
            controller_url=None,
            controller_token=None,
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
            preview_proxy_base_path="/public/apps-builder/draft-dev/sessions",
            e2b_template=None,
            e2b_template_tag=None,
            e2b_timeout_seconds=1800,
            e2b_workspace_path="/workspace",
            e2b_preview_port=4173,
            e2b_opencode_port=4141,
            e2b_secure=True,
            e2b_allow_internet_access=True,
            e2b_auto_pause=False,
            sprite_api_base_url="https://api.sprites.dev",
            sprite_api_token="sprite-token",
            sprite_name_prefix="app-builder",
            sprite_workspace_path="/home/sprite/app",
            sprite_stage_workspace_path="/home/sprite/.talmudpedia/stage/current/workspace",
            sprite_publish_workspace_path="/home/sprite/.talmudpedia/publish/current/workspace",
            sprite_preview_port=8080,
            sprite_opencode_port=4141,
            sprite_preview_service_name="builder-preview",
            sprite_opencode_service_name="opencode",
            sprite_opencode_command=None,
            sprite_command_timeout_seconds=900,
            sprite_retention_seconds=21600,
            sprite_network_policy=None,
        )
    )

    captured: dict[str, object] = {}

    async def fake_exec_with_stdin(*, sprite_name: str, command: list[str], stdin_text: str, **kwargs):
        captured["sprite_name"] = sprite_name
        captured["command"] = command
        captured["stdin_text"] = stdin_text
        captured["kwargs"] = kwargs
        return ("", 0)

    async def fake_bump_revision_token(*, sprite_name: str, workspace_path: str) -> str:
        assert sprite_name == "sprite-app-1"
        assert workspace_path == "/home/sprite/app"
        return "rev-1"

    monkeypatch.setattr(backend, "_exec_with_stdin", fake_exec_with_stdin)
    monkeypatch.setattr(backend, "_bump_revision_token", fake_bump_revision_token)

    result = await backend.write_file(
        sandbox_id="sprite-app-1",
        path="src/App.tsx",
        content="x" * 250_000,
    )

    assert captured["sprite_name"] == "sprite-app-1"
    assert captured["stdin_text"] == "x" * 250_000
    assert captured["command"][:2] == ["python3", "-c"]
    assert "destination.write_text(sys.stdin.read(), encoding='utf-8')" in str(captured["command"][2])
    assert result["revision_token"] == "rev-1"


@pytest.mark.asyncio
async def test_sprite_build_opencode_client_reuses_cached_service_and_tunnel(monkeypatch: pytest.MonkeyPatch):
    backend = SpriteSandboxBackend(
        PublishedAppSandboxBackendConfig(
            backend="sprite",
            controller_url=None,
            controller_token=None,
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
            preview_proxy_base_path="/public/apps-builder/draft-dev/sessions",
            e2b_template=None,
            e2b_template_tag=None,
            e2b_timeout_seconds=1800,
            e2b_workspace_path="/workspace",
            e2b_preview_port=4173,
            e2b_opencode_port=4141,
            e2b_secure=True,
            e2b_allow_internet_access=True,
            e2b_auto_pause=False,
            sprite_api_base_url="https://api.sprites.dev",
            sprite_api_token="sprite-token",
            sprite_name_prefix="app-builder",
            sprite_workspace_path="/home/sprite/app",
            sprite_stage_workspace_path="/home/sprite/.talmudpedia/stage/current/workspace",
            sprite_publish_workspace_path="/home/sprite/.talmudpedia/publish/current/workspace",
            sprite_preview_port=8080,
            sprite_opencode_port=4141,
            sprite_preview_service_name="builder-preview",
            sprite_opencode_service_name="opencode",
            sprite_opencode_command=None,
            sprite_command_timeout_seconds=900,
            sprite_retention_seconds=21600,
            sprite_network_policy=None,
        )
    )

    ensure_service_calls: list[str] = []
    tunnel_calls: list[str] = []

    async def fake_ensure_opencode_service(*, sprite_name: str) -> None:
        ensure_service_calls.append(sprite_name)

    class _TunnelManagerStub:
        async def ensure_tunnel(self, *, api_base_url: str, api_token: str, sprite_name: str, remote_host: str, remote_port: int) -> str:
            tunnel_calls.append(sprite_name)
            return "http://127.0.0.1:40141"

    from app.services import published_app_sandbox_backend_sprite as sprite_backend_module

    monkeypatch.setattr(backend, "_ensure_opencode_service", fake_ensure_opencode_service)
    monkeypatch.setattr(sprite_backend_module, "get_sprite_proxy_tunnel_manager", lambda: _TunnelManagerStub())

    first = await backend._build_opencode_client(sandbox_id="sprite-app-1")
    second = await backend._build_opencode_client(sandbox_id="sprite-app-1")
    third = await backend._build_opencode_client(sandbox_id="sprite-app-1", force_refresh=True)

    assert first is second
    assert third is not first
    assert ensure_service_calls == ["sprite-app-1", "sprite-app-1", "sprite-app-1", "sprite-app-1"]
    assert tunnel_calls == ["sprite-app-1", "sprite-app-1"]


@pytest.mark.asyncio
async def test_sandbox_mode_seeds_custom_tools_before_start(monkeypatch: pytest.MonkeyPatch):
    class SandboxClientStub:
        is_remote_enabled = True

        def __init__(self) -> None:
            self.writes: list[tuple[str, str]] = []

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            self.writes.append((path, content))
            return {"sandbox_id": sandbox_id, "path": path, "status": "written"}

    class NestedSandboxClientStub:
        def __init__(self) -> None:
            self.start_calls = 0

        async def create_session(self, **kwargs):
            return "sandbox-session-1"

        async def submit_turn(self, **kwargs):
            self.start_calls += 1
            return "sandbox-run-1"

    nested = NestedSandboxClientStub()

    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_SEED_BOOTSTRAP_ON_RUN_START", "1")
    stub = SandboxClientStub()
    client = _client(sandbox_controller_mode_override=True)
    client._sandbox_runtime_client = stub
    monkeypatch.setattr(
        client,
        "_get_sandbox_official_client",
        lambda **kwargs: pytest.fail("_get_sandbox_official_client must be async"),
    )

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        _ = sandbox_id
        return nested, workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

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
    assert nested.start_calls == 1
    seeded_paths = {path for path, _ in stub.writes}
    assert ".opencode/package.json" in seeded_paths
    assert ".opencode/tools/read_agent_context.ts" in seeded_paths
    assert OPENCODE_BOOTSTRAP_CONTEXT_PATH in seeded_paths

    second_run_ref = await client.start_run(
        run_id="run-sandbox-seed-2",
        app_id="app-1",
        sandbox_id="sandbox-seed",
        workspace_path="/workspace",
        model_id="",
        prompt="seed again",
        messages=[{"role": "user", "content": "seed again"}],
        selected_agent_contract={"agent": {"id": "agent-1"}},
    )
    assert second_run_ref == "sandbox-run-1"
    assert nested.start_calls == 2
    assert len(stub.writes) == len(seeded_paths)


@pytest.mark.asyncio
async def test_e2b_backend_auto_selects_sandbox_mode_without_controller_url(monkeypatch: pytest.MonkeyPatch):
    class SandboxClientStub:
        backend_name = "e2b"
        is_remote_enabled = False

        def __init__(self) -> None:
            self.writes: list[tuple[str, str]] = []

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            self.writes.append((path, content))
            return {"sandbox_id": sandbox_id, "path": path, "status": "written"}

    class NestedSandboxClientStub:
        def __init__(self) -> None:
            self.start_calls = 0

        async def create_session(self, **kwargs):
            return "sandbox-session-e2b"

        async def submit_turn(self, **kwargs):
            self.start_calls += 1
            return "sandbox-run-e2b"

    nested = NestedSandboxClientStub()

    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", raising=False)
    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_URL", raising=False)
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_SEED_BOOTSTRAP_ON_RUN_START", "1")
    stub = SandboxClientStub()
    client = _client(sandbox_controller_mode_override=None)
    client._sandbox_runtime_client = stub

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        _ = sandbox_id
        return nested, workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

    run_ref = await client.start_run(
        run_id="run-e2b-auto",
        app_id="app-1",
        sandbox_id="sandbox-e2b",
        workspace_path="/workspace/.talmudpedia/stage/shared/workspace",
        model_id="",
        prompt="seed",
        messages=[{"role": "user", "content": "seed"}],
        selected_agent_contract={"agent": {"id": "agent-1"}},
    )

    assert run_ref == "sandbox-run-e2b"
    assert nested.start_calls == 1
    seeded_paths = {path for path, _ in stub.writes}
    assert ".opencode/package.json" in seeded_paths
    assert OPENCODE_BOOTSTRAP_CONTEXT_PATH in seeded_paths


@pytest.mark.asyncio
async def test_sandbox_mode_refreshes_context_when_contract_changes(monkeypatch: pytest.MonkeyPatch):
    class SandboxClientStub:
        is_remote_enabled = True

        def __init__(self) -> None:
            self.writes: list[tuple[str, str]] = []

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            self.writes.append((path, content))
            return {"sandbox_id": sandbox_id, "path": path, "status": "written"}

    class NestedSandboxClientStub:
        async def create_session(self, **kwargs):
            return "sandbox-session-1"

        async def submit_turn(self, **kwargs):
            return "sandbox-run-1"

    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_SEED_BOOTSTRAP_ON_RUN_START", "1")
    stub = SandboxClientStub()
    client = _client(sandbox_controller_mode_override=True)
    client._sandbox_runtime_client = stub
    nested = NestedSandboxClientStub()

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        _ = sandbox_id
        return nested, workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

    await client.start_run(
        run_id="run-contract-1",
        app_id="app-1",
        sandbox_id="sandbox-seed",
        workspace_path="/workspace",
        model_id="",
        prompt="seed",
        messages=[{"role": "user", "content": "seed"}],
        selected_agent_contract={"agent": {"id": "agent-1"}},
    )
    writes_after_first = len(stub.writes)
    await client.start_run(
        run_id="run-contract-2",
        app_id="app-1",
        sandbox_id="sandbox-seed",
        workspace_path="/workspace",
        model_id="",
        prompt="seed",
        messages=[{"role": "user", "content": "seed"}],
        selected_agent_contract={"agent": {"id": "agent-2"}},
    )
    assert len(stub.writes) == writes_after_first + 1
    assert stub.writes[-1][0] == OPENCODE_BOOTSTRAP_CONTEXT_PATH


@pytest.mark.asyncio
async def test_sandbox_mode_ignores_generated_at_for_context_hash(monkeypatch: pytest.MonkeyPatch):
    class SandboxClientStub:
        is_remote_enabled = True

        def __init__(self) -> None:
            self.writes: list[tuple[str, str]] = []

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            self.writes.append((path, content))
            return {"sandbox_id": sandbox_id, "path": path, "status": "written"}

    class NestedSandboxClientStub:
        async def create_session(self, **kwargs):
            return "sandbox-session-1"

        async def submit_turn(self, **kwargs):
            return "sandbox-run-1"

    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    stub = SandboxClientStub()
    client = _client(sandbox_controller_mode_override=True)
    client._sandbox_runtime_client = stub
    nested = NestedSandboxClientStub()

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        _ = sandbox_id
        return nested, workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

    await client.start_run(
        run_id="run-generated-at-1",
        app_id="app-1",
        sandbox_id="sandbox-seed",
        workspace_path="/workspace",
        model_id="",
        prompt="seed",
        messages=[{"role": "user", "content": "seed"}],
        selected_agent_contract={"agent": {"id": "agent-1"}, "generated_at": "2026-02-22T00:00:00Z"},
    )
    writes_after_first = len(stub.writes)

    await client.start_run(
        run_id="run-generated-at-2",
        app_id="app-1",
        sandbox_id="sandbox-seed",
        workspace_path="/workspace",
        model_id="",
        prompt="seed",
        messages=[{"role": "user", "content": "seed"}],
        selected_agent_contract={"agent": {"id": "agent-1"}, "generated_at": "2026-02-22T01:00:00Z"},
    )

    assert len(stub.writes) == writes_after_first


@pytest.mark.asyncio
async def test_sandbox_mode_fails_closed_when_seed_write_fails(monkeypatch: pytest.MonkeyPatch):
    class FailingSandboxClientStub:
        is_remote_enabled = True

        async def write_file(self, *, sandbox_id: str, path: str, content: str):
            raise PublishedAppDraftDevRuntimeClientError("write failed")

    class NestedSandboxClientStub:
        async def create_session(self, **kwargs):
            return "sandbox-session-fail"

        async def submit_turn(self, **kwargs):
            raise AssertionError("submit_turn should not be called when seeding fails")

    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "1")
    client = _client(sandbox_controller_mode_override=True)
    client._sandbox_runtime_client = FailingSandboxClientStub()
    nested = NestedSandboxClientStub()

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        _ = sandbox_id
        return nested, workspace_path

    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

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
        ("run.completed", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
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


def test_extract_incremental_tool_events_refreshes_started_after_pending_with_real_input():
    state: dict[str, object] = {}
    pending_message = {
        "parts": [
            {
                "type": "tool",
                "tool": "apply_patch",
                "callID": "call-1",
                "state": {"status": "pending", "input": {}},
            }
        ]
    }
    running_message = {
        "parts": [
            {
                "type": "tool",
                "tool": "apply_patch",
                "callID": "call-1",
                "state": {
                    "status": "running",
                    "input": {"patchText": "*** Begin Patch\n*** Update File: src/App.tsx\n*** End Patch"},
                },
            }
        ]
    }

    pending_events = OpenCodeServerClient._extract_incremental_tool_events(message=pending_message, state=state)
    running_events = OpenCodeServerClient._extract_incremental_tool_events(message=running_message, state=state)

    assert [event.get("event") for event in pending_events] == ["tool.started"]
    assert [event.get("event") for event in running_events] == ["tool.started"]
    assert running_events[0].get("payload", {}).get("input", {}).get("patchText")


def test_extract_incremental_tool_events_completed_payload_includes_input():
    state: dict[str, object] = {}
    completed_message = {
        "parts": [
            {
                "type": "tool",
                "tool": "apply_patch",
                "callID": "call-1",
                "state": {
                    "status": "completed",
                    "input": {"patchText": "*** Begin Patch\n*** Update File: src/App.tsx\n*** End Patch"},
                    "output": {"ok": True},
                },
            }
        ]
    }

    events = OpenCodeServerClient._extract_incremental_tool_events(message=completed_message, state=state)
    assert [event.get("event") for event in events] == ["tool.started", "tool.completed"]
    completed_payload = events[1].get("payload", {})
    assert completed_payload.get("input", {}).get("patchText")
    assert completed_payload.get("output", {}).get("ok") is True


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
        ("run.completed", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
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
async def test_official_mode_global_event_stream_emits_deltas_from_message_updated_payload(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-global-updated-deltas"
    assistant_message_id = "msg-assistant-updated"
    user_message_id = "msg-user-updated"
    text_part_id = "part-text-updated"

    global_events = [
        ("message.updated", {"info": {"id": user_message_id, "sessionID": session_id, "role": "user"}}),
        (
            "message.updated",
            {
                "info": {
                    "id": assistant_message_id,
                    "sessionID": session_id,
                    "role": "assistant",
                    "parentID": user_message_id,
                },
                "parts": [{"id": text_part_id, "type": "text", "text": "Hel"}],
            },
        ),
        (
            "message.updated",
            {
                "info": {
                    "id": assistant_message_id,
                    "sessionID": session_id,
                    "role": "assistant",
                    "parentID": user_message_id,
                },
                "parts": [{"id": text_part_id, "type": "text", "text": "Hello there"}],
            },
        ),
        ("session.idle", {"sessionID": session_id}),
        ("run.completed", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
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
                        "parts": [{"id": text_part_id, "type": "text", "text": "Hello there"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-global-updated-deltas",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with Hello there",
        messages=[{"role": "user", "content": "Reply with Hello there"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assistant_chunks = [str(item.get("payload", {}).get("content") or "") for item in events if item.get("event") == "assistant.delta"]
    assert assistant_chunks
    assert "".join(assistant_chunks) == "Hello there"
    assert events[-1].get("event") == "run.completed"


@pytest.mark.asyncio
async def test_official_mode_global_event_stream_keeps_running_after_session_idle_text_before_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    session_id = "sess-global-idle-before-tool"
    assistant_message_id = "msg-assistant-idle-before-tool"
    user_message_id = "msg-user-idle-before-tool"
    text_part_id = "part-text-idle-before-tool"
    tool_part_id = "part-tool-idle-before-tool"

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
                    "id": text_part_id,
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "text",
                    "text": "Working on it...",
                }
            },
        ),
        ("session.idle", {"sessionID": session_id}),
        (
            "message.part.updated",
            {
                "part": {
                    "id": tool_part_id,
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "tool",
                    "tool": "read",
                    "callID": "call-idle-before-tool",
                    "state": {"status": "running", "input": {"filePath": "/tmp/a.txt"}},
                }
            },
        ),
        (
            "message.part.updated",
            {
                "part": {
                    "id": tool_part_id,
                    "sessionID": session_id,
                    "messageID": assistant_message_id,
                    "type": "tool",
                    "tool": "read",
                    "callID": "call-idle-before-tool",
                    "state": {"status": "completed", "input": {"filePath": "/tmp/a.txt"}, "output": {"text": "ok"}},
                }
            },
        ),
        ("run.completed", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
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
                            "finish": "tool-calls",
                            "time": {"created": 1, "completed": 2},
                        },
                        "parts": [{"id": text_part_id, "type": "text", "text": "Working on it..."}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-global-idle-before-tool",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Continue with tool",
        messages=[{"role": "user", "content": "Continue with tool"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    event_names = [str(item.get("event") or "") for item in events]
    assert "tool.started" in event_names
    assert "tool.completed" in event_names
    assert "run.completed" in event_names
    assert event_names.index("tool.started") < event_names.index("run.completed")
    assert event_names.index("tool.completed") < event_names.index("run.completed")


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_official_mode_global_event_stream_completes_from_session_status_idle(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-global-status-idle"
    assistant_message_id = "msg-assistant-status-idle"
    user_message_id = "msg-user-status-idle"
    text_part_id = "part-text-status-idle"

    global_events = [
        ("message.updated", {"info": {"id": user_message_id, "sessionID": session_id, "role": "user"}}),
        (
            "message.updated",
            {
                "info": {
                    "id": assistant_message_id,
                    "sessionID": session_id,
                    "role": "assistant",
                    "parentID": user_message_id,
                },
                "parts": [{"id": text_part_id, "type": "text", "text": "Done"}],
            },
        ),
        ("session.status", {"sessionID": session_id, "status": {"type": "idle"}}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
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
                            "finish": "stop",
                            "time": {"created": 1, "completed": 2},
                        },
                        "parts": [{"id": text_part_id, "type": "text", "text": "Done"}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    run_ref = await client.start_run(
        run_id="run-global-status-idle",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="Reply with Done",
        messages=[{"role": "user", "content": "Reply with Done"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert any(item.get("event") == "assistant.delta" for item in events)
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
        if request.url.path == "/global/event":
            sse_text = f"data: {_sse_payload('session.idle', {'sessionID': 'sess-candidates'})}\n\n"
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
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


@pytest.mark.asyncio
async def test_official_mode_persistent_session_followup_turn_uses_message_append_path(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-persistent-followup"
    assistant_messages: list[dict[str, object]] = []
    latest_assistant_id = ""

    def _assistant(parent_id: str, text: str, order: int) -> dict[str, object]:
        return {
            "info": {
                "id": f"assistant-{order}",
                "sessionID": session_id,
                "role": "assistant",
                "parentID": parent_id,
                "time": {"created": order, "completed": order},
            },
            "parts": [{"type": "text", "text": text}],
        }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal assistant_messages, latest_assistant_id
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == "/global/event":
            sse_text = "".join(
                [
                    f"data: {_sse_payload('session.idle', {'sessionID': session_id})}\n\n",
                    f"data: {_sse_payload('run.completed', {'sessionID': session_id})}\n\n",
                ]
            )
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            message_id = str(payload.get("messageID") or "").strip()
            prompt_text = str((payload.get("parts") or [{}])[0].get("text") or "")
            assert "parentID" not in payload
            reply_text = (
                "Your first message was hi."
                if "what was my first message?" in prompt_text.lower()
                else "First reply"
            )
            order = len(assistant_messages) + 1
            assistant_messages.append(_assistant(message_id, reply_text, order))
            latest_assistant_id = f"assistant-{order}"
            return httpx.Response(200, content=b"")
        if request.url.path == f"/session/{session_id}/message" and request.method == "GET":
            return httpx.Response(200, json=assistant_messages)
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    created_session_id = await client.create_session(
        run_id="run-persistent-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
    )
    assert created_session_id == session_id

    first_turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-persistent-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="hi",
    )
    first_events = [
        item
        async for item in client.stream_turn_events(session_id=session_id, turn_ref=first_turn_ref)
    ]
    first_text = "".join(
        str(item.get("payload", {}).get("content") or "")
        for item in first_events
        if item.get("event") == "assistant.delta"
    )
    assert "First reply" in first_text

    second_turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-persistent-2",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="what was my first message?",
    )
    second_events = [
        item
        async for item in client.stream_turn_events(session_id=session_id, turn_ref=second_turn_ref)
    ]
    second_text = "".join(
        str(item.get("payload", {}).get("content") or "")
        for item in second_events
        if item.get("event") == "assistant.delta"
    )
    assert "Your first message was hi." in second_text


@pytest.mark.asyncio
async def test_official_mode_followup_turn_does_not_complete_from_stale_idle_history(
    monkeypatch: pytest.MonkeyPatch,
):
    session_id = "sess-followup-stale-idle"
    first_assistant_id = "assistant-1"
    second_assistant_id = "assistant-2"
    post_count = 0
    stream_count = 0
    second_turn_get_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count, stream_count, second_turn_get_count
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            post_count += 1
            assert "parentID" not in payload
            return httpx.Response(200, content=b"")
        if request.url.path == "/global/event":
            stream_count += 1
            if stream_count == 1:
                sse_text = "".join(
                    [
                        f"data: {_sse_payload('session.idle', {'sessionID': session_id})}\n\n",
                        f"data: {_sse_payload('run.completed', {'sessionID': session_id})}\n\n",
                    ]
                )
                return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
            sse_text = "".join(
                [
                    f"data: {_sse_payload('session.status', {'sessionID': session_id, 'status': {'type': 'idle'}})}\n\n",
                    "data: "
                    + _sse_payload(
                        "message.updated",
                        {
                            "info": {
                                "id": second_assistant_id,
                                "sessionID": session_id,
                                "role": "assistant",
                            },
                            "parts": [{"type": "text", "text": "Your first message was hi."}],
                        },
                    )
                    + "\n\n",
                    f"data: {_sse_payload('run.completed', {'sessionID': session_id})}\n\n",
                ]
            )
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/message" and request.method == "GET":
            if post_count == 1:
                return httpx.Response(
                    200,
                    json=[
                        {
                            "info": {
                                "id": first_assistant_id,
                                "sessionID": session_id,
                                "role": "assistant",
                            },
                            "parts": [{"type": "text", "text": "Hi! How can I help you today?"}],
                        }
                    ],
                )
            second_turn_get_count += 1
            if second_turn_get_count == 1:
                return httpx.Response(
                    200,
                    json=[
                        {
                            "info": {
                                "id": first_assistant_id,
                                "sessionID": session_id,
                                "role": "assistant",
                            },
                            "parts": [{"type": "text", "text": "Hi! How can I help you today?"}],
                        }
                    ],
                )
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {
                            "id": first_assistant_id,
                            "sessionID": session_id,
                            "role": "assistant",
                        },
                        "parts": [{"type": "text", "text": "Hi! How can I help you today?"}],
                    },
                    {
                        "info": {
                            "id": second_assistant_id,
                            "sessionID": session_id,
                            "role": "assistant",
                        },
                        "parts": [{"type": "text", "text": "Your first message was hi."}],
                    },
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    created_session_id = await client.create_session(
        run_id="run-followup-stale-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
    )
    assert created_session_id == session_id

    first_turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-followup-stale-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="hi",
    )
    first_events = [
        item
        async for item in client.stream_turn_events(session_id=session_id, turn_ref=first_turn_ref)
    ]
    first_text = "".join(
        str(item.get("payload", {}).get("content") or "")
        for item in first_events
        if item.get("event") == "assistant.delta"
    )
    assert "Hi! How can I help you today?" in first_text

    second_turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-followup-stale-2",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="what is my first message",
        defer_until_stream=True,
    )
    second_events = [
        item
        async for item in client.stream_turn_events(session_id=session_id, turn_ref=second_turn_ref)
    ]
    second_text = "".join(
        str(item.get("payload", {}).get("content") or "")
        for item in second_events
        if item.get("event") == "assistant.delta"
    )
    assert second_text == "Your first message was hi."
    assert any(item.get("event") == "run.completed" for item in second_events)


@pytest.mark.asyncio
async def test_official_mode_persistent_session_followup_turn_recovers_parent_from_session_messages(
    monkeypatch: pytest.MonkeyPatch,
):
    session_id = "sess-persistent-parent-recovery"
    assistant_messages: list[dict[str, object]] = []
    latest_assistant_id = ""

    def _assistant(parent_id: str, text: str, order: int) -> dict[str, object]:
        return {
            "info": {
                "id": f"assistant-{order}",
                "sessionID": session_id,
                "role": "assistant",
                "parentID": parent_id,
                "time": {"created": order, "completed": order},
            },
            "parts": [{"type": "text", "text": text}],
        }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal assistant_messages, latest_assistant_id
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == "/global/event":
            sse_text = "".join(
                [
                    f"data: {_sse_payload('session.idle', {'sessionID': session_id})}\n\n",
                    f"data: {_sse_payload('run.completed', {'sessionID': session_id})}\n\n",
                ]
            )
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            message_id = str(payload.get("messageID") or "").strip()
            prompt_text = str((payload.get("parts") or [{}])[0].get("text") or "")
            assert "parentID" not in payload
            if "what was my first message?" in prompt_text.lower():
                reply_text = "Your first message was hi."
            else:
                reply_text = "First reply"
            order = len(assistant_messages) + 1
            assistant_messages.append(_assistant(message_id, reply_text, order))
            latest_assistant_id = f"assistant-{order}"
            return httpx.Response(200, content=b"")
        if request.url.path == f"/session/{session_id}/message" and request.method == "GET":
            return httpx.Response(200, json=assistant_messages)
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)

    first_client = _client()
    created_session_id = await first_client.create_session(
        run_id="run-parent-recovery-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
    )
    assert created_session_id == session_id

    first_turn_ref = await first_client.submit_turn(
        session_id=session_id,
        run_id="run-parent-recovery-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="hi",
    )
    _ = [
        item
        async for item in first_client.stream_turn_events(session_id=session_id, turn_ref=first_turn_ref)
    ]

    second_client = _client()
    second_turn_ref = await second_client.submit_turn(
        session_id=session_id,
        run_id="run-parent-recovery-2",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="what was my first message?",
    )
    second_events = [
        item
        async for item in second_client.stream_turn_events(session_id=session_id, turn_ref=second_turn_ref)
    ]
    second_text = "".join(
        str(item.get("payload", {}).get("content") or "")
        for item in second_events
        if item.get("event") == "assistant.delta"
    )
    assert "Your first message was hi." in second_text


@pytest.mark.asyncio
async def test_official_mode_deferred_turn_attaches_global_stream_before_posting_followup(
    monkeypatch: pytest.MonkeyPatch,
):
    session_id = "sess-deferred-followup"
    latest_assistant_id = ""
    stream_count = 0
    post_seen_stream_counts: list[int] = []
    second_post_parent_id = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal latest_assistant_id, stream_count, second_post_parent_id
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == "/global/event":
            stream_count += 1
            live_assistant_id = f"assistant-live-{stream_count}"
            latest_assistant_id = live_assistant_id
            sse_text = "".join(
                [
                    "data: "
                    + _sse_payload(
                        "message.updated",
                        {
                            "info": {
                                "id": live_assistant_id,
                                "sessionID": session_id,
                                "role": "assistant",
                                "time": {"created": stream_count, "completed": stream_count},
                            },
                            "parts": [{"type": "text", "text": "Live reply"}],
                        },
                    )
                    + "\n\n",
                    f"data: {_sse_payload('run.completed', {'sessionID': session_id})}\n\n",
                ]
            )
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            post_seen_stream_counts.append(stream_count)
            payload = json.loads(request.content.decode("utf-8"))
            if len(post_seen_stream_counts) > 1:
                second_post_parent_id = str(payload.get("parentID") or "").strip()
            assert "parentID" not in payload
            return httpx.Response(200, content=b"")
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    client = _client()

    created_session_id = await client.create_session(
        run_id="run-deferred-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
    )
    assert created_session_id == session_id

    first_turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-deferred-1",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="hi",
        defer_until_stream=True,
    )
    first_events = [
        item
        async for item in client.stream_turn_events(session_id=session_id, turn_ref=first_turn_ref)
    ]
    assert any(item.get("event") == "run.completed" for item in first_events)

    second_turn_ref = await client.submit_turn(
        session_id=session_id,
        run_id="run-deferred-2",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/sandbox-1",
        model_id="",
        prompt="what was my first message?",
        defer_until_stream=True,
    )
    second_events = [
        item
        async for item in client.stream_turn_events(session_id=session_id, turn_ref=second_turn_ref)
    ]
    assert any(item.get("event") == "run.completed" for item in second_events)
    assert post_seen_stream_counts == [1, 2]
    assert second_post_parent_id == ""


@pytest.mark.asyncio
async def test_official_mode_auto_approves_permission_asked_in_stage_workspace(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-permission-auto"
    permission_request_id = "perm-1"
    approval_calls: list[str] = []
    global_events = [
        (
            "permission.asked",
            {
                "sessionID": session_id,
                "id": permission_request_id,
                "permission": "filesystem",
                "path": "/tmp/.talmudpedia/stage/shared/workspace/src/App.tsx",
                "question": "Allow write?",
            },
        ),
        ("session.idle", {"sessionID": session_id}),
        ("run.completed", {"sessionID": session_id}),
    ]
    sse_text = "".join([f"data: {_sse_payload(event_type, properties)}\n\n" for event_type, properties in global_events])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})
        if request.url.path == "/session":
            return httpx.Response(200, json={"success": True, "data": {"id": session_id}})
        if request.url.path == f"/session/{session_id}/message" and request.method == "POST":
            return httpx.Response(200, content=b"")
        if request.url.path == "/global/event":
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        if request.url.path == f"/session/{session_id}/permissions/{permission_request_id}" and request.method == "POST":
            approval_calls.append(request.url.path)
            return httpx.Response(200, json={"ok": True})
        if request.url.path == f"/session/{session_id}/message" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "info": {"id": "msg-assistant", "sessionID": session_id, "role": "assistant"},
                        "parts": [{"id": "part-text", "type": "text", "text": "Permission approved."}],
                    }
                ],
            )
        raise AssertionError(f"Unexpected request path: {request.url.path} ({request.method})")

    _patch_async_client(monkeypatch, handler)
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_POLL_INTERVAL_SECONDS", "0.1")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_OFFICIAL_STREAM_SETTLE_SECONDS", "0.2")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_AUTO_APPROVE_PERMISSION_ASK", "1")
    client = _client()

    run_ref = await client.start_run(
        run_id="run-permission-auto",
        app_id="app-1",
        sandbox_id="sandbox-1",
        workspace_path="/tmp/.talmudpedia/stage/shared/workspace",
        model_id="",
        prompt="Continue",
        messages=[{"role": "user", "content": "Continue"}],
    )
    events = [item async for item in client.stream_run_events(run_ref=run_ref)]
    assert approval_calls == [f"/session/{session_id}/permissions/{permission_request_id}"]
    assert any(item.get("event") == "tool.question.answered" for item in events)
    assert events[-1].get("event") == "run.completed"


@pytest.mark.asyncio
async def test_host_mode_answer_question_ignores_sandbox_id_and_uses_api(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []

    class _SandboxClientStub:
        is_remote_enabled = True

    async def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path))
        if path == "/question/question-1/reply":
            return {}
        raise AssertionError(f"Unexpected request path: {path}")

    client = _client(sandbox_controller_mode_override=False)
    client._sandbox_runtime_client = _SandboxClientStub()
    client._api_mode = "official"
    client._request = fake_request  # type: ignore[method-assign]

    ok = await client.answer_question(
        run_ref="run-1",
        question_id="question-1",
        answers=[["A"]],
        sandbox_id="sandbox-1",
    )

    assert ok is True
    assert calls == [("POST", "/question/question-1/reply")]


@pytest.mark.asyncio
async def test_stream_session_events_maps_question_events_to_session_chat_contract(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-question-1"
    sse_text = "".join(
        [
            f"data: {_sse_payload('question.asked', {'sessionID': session_id, 'id': 'question-1', 'questions': [{'header': 'Need input', 'question': 'Pick one', 'options': [{'label': 'A'}]}]})}\n\n",
            f"data: {_sse_payload('question.replied', {'sessionID': session_id, 'id': 'question-1', 'answers': [['A']]})}\n\n",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/global/event":
            return httpx.Response(200, text=sse_text, headers={"content-type": "text/event-stream"})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    _patch_async_client(monkeypatch, handler)
    client = _client()
    client._api_mode = "official"

    stream = client.stream_session_events(session_id=session_id)
    events = [await anext(stream), await anext(stream)]
    await stream.aclose()

    assert events == [
        {
            "event": "permission.updated",
            "session_id": session_id,
                "payload": {
                    "request_id": "question-1",
                    "questions": [{
                        "header": "Need input",
                        "question": "Pick one",
                        "multiple": False,
                        "options": [{"label": "A", "description": ""}],
                    }],
                    "request_kind": "question",
                },
            },
        {
            "event": "permission.replied",
            "session_id": session_id,
            "payload": {
                "request_id": "question-1",
                "request_kind": None,
                "answers": [["A"]],
            },
        },
    ]


@pytest.mark.asyncio
async def test_reply_request_routes_question_answers_to_question_endpoint(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path))
        if path == "/question/question-1/reply":
            return {}
        raise AssertionError(f"Unexpected request path: {path}")

    client = _client(sandbox_controller_mode_override=False)
    client._api_mode = "official"
    client._request = fake_request  # type: ignore[method-assign]
    client._remember_request_kind(session_id="sess-1", request_id="question-1", kind="question")

    ok = await client.reply_request(
        session_id="sess-1",
        request_id="question-1",
        answers=[["A"]],
    )

    assert ok is True
    assert calls == [("POST", "/question/question-1/reply")]


@pytest.mark.asyncio
async def test_reply_request_infers_question_endpoint_from_official_question_id(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path))
        if path == "/question/que_da2862c7e001Z3dPoANSu9N2U1/reply":
            return {}
        raise AssertionError(f"Unexpected request path: {path}")

    client = _client(sandbox_controller_mode_override=False)
    client._api_mode = "official"
    client._request = fake_request  # type: ignore[method-assign]

    ok = await client.reply_request(
        session_id="sess-1",
        request_id="que_da2862c7e001Z3dPoANSu9N2U1",
        answers=[["A"]],
    )

    assert ok is True
    assert calls == [("POST", "/question/que_da2862c7e001Z3dPoANSu9N2U1/reply")]


@pytest.mark.asyncio
async def test_sandbox_mode_stream_can_use_explicit_sandbox_id_without_in_memory_mapping():
    class _NestedSandboxClientStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def stream_turn_events(self, *, session_id: str, turn_ref: str):
            self.calls.append((session_id, turn_ref))
            yield {"event": "assistant.delta", "payload": {"content": "hello"}}
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    client = _client(sandbox_controller_mode_override=True)
    stub = _NestedSandboxClientStub()

    async def _fake_get_sandbox_official_client(*, sandbox_id: str, workspace_path: str):
        _ = sandbox_id, workspace_path
        return stub, workspace_path

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(client, "_get_sandbox_official_client", _fake_get_sandbox_official_client)

    events = [
        item
        async for item in client.stream_run_events(
            run_ref="sandbox-run-ref-1",
            sandbox_id="sandbox-1",
        )
    ]

    monkeypatch.undo()
    assert stub.calls == [("sandbox-run-ref-1", "sandbox-run-ref-1")]
    assert [item.get("event") for item in events] == ["assistant.delta", "run.completed"]


@pytest.mark.asyncio
async def test_host_mode_cancel_ignores_sandbox_id_and_uses_api(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []

    class _SandboxClientStub:
        is_remote_enabled = True

    async def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path))
        if path == "/session/run-1/abort":
            return {"aborted": True}
        raise AssertionError(f"Unexpected request path: {path}")

    client = _client(sandbox_controller_mode_override=False)
    client._sandbox_runtime_client = _SandboxClientStub()
    client._api_mode = "official"
    client._request = fake_request  # type: ignore[method-assign]

    ok = await client.cancel_run(
        run_ref="run-1",
        sandbox_id="sandbox-1",
    )

    assert ok is True
    assert calls == [("POST", "/session/run-1/abort")]


@pytest.mark.asyncio
async def test_abort_session_accepts_empty_success_body():
    calls: list[tuple[str, str, bool]] = []

    async def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, bool(kwargs.get("expect_json", True))))
        if path == "/session/sess-1/abort":
            return None
        raise AssertionError(f"Unexpected request path: {path}")

    client = _client(sandbox_controller_mode_override=False)
    client._api_mode = "official"
    client._request = fake_request  # type: ignore[method-assign]

    ok = await client.abort_session(session_id="sess-1")

    assert ok is True
    assert calls == [("POST", "/session/sess-1/abort", False)]
