from __future__ import annotations

import pytest

from app.api.routers import sandbox_controller_dev_shim as shim_router


@pytest.mark.asyncio
async def test_dev_shim_session_lifecycle_and_file_routes(client, monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")

    class _FakeManager:
        async def start_session(self, *, session_id, files, dependency_hash, draft_dev_token):
            return {
                "sandbox_id": session_id,
                "preview_url": "http://127.0.0.1:5173/sandbox/test",
                "status": "running",
                "workspace_path": f"/tmp/talmudpedia-draft-dev/{session_id}",
            }

        async def sync_session(self, *, sandbox_id, files, dependency_hash, install_dependencies):
            return {"sandbox_id": sandbox_id, "status": "running"}

        async def heartbeat_session(self, *, sandbox_id):
            return {"sandbox_id": sandbox_id, "status": "running"}

        async def stop_session(self, *, sandbox_id):
            return {"sandbox_id": sandbox_id, "status": "stopped"}

        async def list_files(self, *, sandbox_id, limit=500):
            return {"sandbox_id": sandbox_id, "count": 1, "paths": ["src/main.tsx"][:limit]}

        async def snapshot_files(self, *, sandbox_id):
            return {"sandbox_id": sandbox_id, "files": {"src/main.tsx": "export {}"}, "file_count": 1}

        async def run_command(self, *, sandbox_id, command, timeout_seconds=180, max_output_bytes=12000):
            return {"sandbox_id": sandbox_id, "code": 0, "stdout": "ok", "stderr": "", "command": command}

        async def resolve_project_dir(self, *, sandbox_id):
            return f"/tmp/talmudpedia-draft-dev/{sandbox_id}"

    fake_manager = _FakeManager()
    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: fake_manager)
    stopped_sandboxes: list[str] = []

    async def _fake_stop_sandbox_opencode_server(*, sandbox_id: str):
        stopped_sandboxes.append(sandbox_id)

    monkeypatch.setattr(shim_router, "_stop_sandbox_opencode_server", _fake_stop_sandbox_opencode_server)

    headers = {"Authorization": "Bearer dev-token"}
    start_response = await client.post(
        "/internal/sandbox-controller/sessions/start",
        headers=headers,
        json={
            "session_id": "sandbox-1",
            "tenant_id": "tenant-1",
            "app_id": "app-1",
            "user_id": "user-1",
            "revision_id": "rev-1",
            "entry_file": "src/main.tsx",
            "files": {"src/main.tsx": "export {}"},
            "idle_timeout_seconds": 180,
            "dependency_hash": "hash",
            "draft_dev_token": "token",
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["sandbox_id"] == "sandbox-1"
    assert start_response.json()["workspace_path"] == "/tmp/talmudpedia-draft-dev/sandbox-1"

    sync_response = await client.patch(
        "/internal/sandbox-controller/sessions/sandbox-1/sync",
        headers=headers,
        json={
            "entry_file": "src/main.tsx",
            "files": {"src/main.tsx": "export {}"},
            "idle_timeout_seconds": 180,
            "dependency_hash": "hash",
            "install_dependencies": False,
        },
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["status"] == "running"

    files_response = await client.request(
        "GET",
        "/internal/sandbox-controller/sessions/sandbox-1/files",
        headers=headers,
        json={"limit": 10},
    )
    assert files_response.status_code == 200
    assert files_response.json()["paths"] == ["src/main.tsx"]

    snapshot_response = await client.request(
        "GET",
        "/internal/sandbox-controller/sessions/sandbox-1/files/snapshot",
        headers=headers,
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["file_count"] == 1

    command_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/commands/run",
        headers=headers,
        json={"command": ["echo", "ok"], "timeout_seconds": 10, "max_output_bytes": 256},
    )
    assert command_response.status_code == 200
    assert command_response.json()["code"] == 0

    stop_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/stop",
        headers=headers,
        json={},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
    assert stopped_sandboxes == ["sandbox-1"]


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_stream_cancel(client, monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return "/tmp/talmudpedia-draft-dev/sandbox-2"

    class _FakeHostClient:
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            assert sandbox_id == "sandbox-2"
            assert workspace_path == "/tmp/talmudpedia-draft-dev/sandbox-2"
            return "host-run-ref-1"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "host-run-ref-1"
            yield {"event": "assistant.delta", "payload": {"content": "hello"}}
            yield {"event": "run.completed", "payload": {"status": "completed"}}

        async def cancel_run(self, *, run_ref):
            assert run_ref == "host-run-ref-1"
            return True

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    start_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-2/opencode/start",
        headers=headers,
        json={
            "run_id": "run-1",
            "app_id": "app-1",
            "workspace_path": "/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["run_ref"] == "host-run-ref-1"

    cancel_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-2/opencode/cancel",
        headers=headers,
        json={"run_ref": "host-run-ref-1"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancelled"] is True

    async with client.stream(
        "GET",
        "/internal/sandbox-controller/sessions/sandbox-2/opencode/events",
        headers=headers,
        params={"run_ref": "host-run-ref-1"},
    ) as stream_response:
        assert stream_response.status_code == 200
        body = (await stream_response.aread()).decode("utf-8")
        assert "assistant.delta" in body
        assert "run.completed" in body


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_rejects_when_sandbox_not_running(client, monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return None

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())

    headers = {"Authorization": "Bearer dev-token"}
    response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-3/opencode/start",
        headers=headers,
        json={
            "run_id": "run-2",
            "app_id": "app-1",
            "workspace_path": "/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Draft dev sandbox is not running"


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_uses_per_sandbox_client_when_enabled(client, monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "1")

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return "/tmp/talmudpedia-draft-dev/sandbox-4"

    captured: dict[str, str] = {}

    class _FakeOpenCodeClient:
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            captured["sandbox_id"] = sandbox_id
            captured["workspace_path"] = workspace_path
            return "sandbox-run-ref-4"

    async def _fake_get_per_sandbox_client(*, sandbox_id: str, workspace_path: str):
        captured["client_sandbox_id"] = sandbox_id
        captured["client_workspace_path"] = workspace_path
        return _FakeOpenCodeClient()

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_get_per_sandbox_opencode_client", _fake_get_per_sandbox_client)

    headers = {"Authorization": "Bearer dev-token"}
    response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-4/opencode/start",
        headers=headers,
        json={
            "run_id": "run-4",
            "app_id": "app-1",
            "workspace_path": "/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["run_ref"] == "sandbox-run-ref-4"
    assert captured["client_sandbox_id"] == "sandbox-4"
    assert captured["client_workspace_path"] == "/tmp/talmudpedia-draft-dev/sandbox-4"
    assert captured["sandbox_id"] == "sandbox-4"
    assert captured["workspace_path"] == "/tmp/talmudpedia-draft-dev/sandbox-4"
