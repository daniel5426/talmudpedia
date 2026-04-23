from __future__ import annotations

import os
from types import SimpleNamespace
import pytest

from app.api.routers import sandbox_controller_dev_shim as shim_router


def test_dev_shim_opencode_command_bootstraps_official_cli(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_SERVER_COMMAND", raising=False)
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_SERVER_COMMAND", raising=False)

    command = shim_router._resolve_opencode_server_command("127.0.0.1", 4141)

    assert command is not None
    assert command[:2] == ["bash", "-lc"]
    rendered = str(command[2])
    assert "https://opencode.ai/install" in rendered
    assert "opencode serve --hostname 127.0.0.1 --port 4141" in rendered
    assert "opencode-ai" not in rendered


@pytest.mark.asyncio
async def test_dev_shim_session_lifecycle_and_file_routes(client, monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")

    class _FakeManager:
        async def start_session(self, *, session_id, files, dependency_hash, preview_base_path="/"):
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

        async def run_command(self, *, sandbox_id, command, timeout_seconds=180, max_output_bytes=12000, workspace_path=None):
            return {
                "sandbox_id": sandbox_id,
                "code": 0,
                "stdout": "ok",
                "stderr": "",
                "command": command,
                "workspace_path": workspace_path,
            }

        async def export_workspace_archive(self, *, sandbox_id, workspace_path, format="tar.gz"):
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": workspace_path,
                "format": format,
                "archive_base64": "",
                "size_bytes": 0,
            }

        async def sync_workspace_files(self, *, sandbox_id, workspace_path, files):
            return {"sandbox_id": sandbox_id, "workspace_path": workspace_path, "file_count": len(files or {})}

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
            "organization_id": "tenant-1",
            "app_id": "app-1",
            "user_id": "user-1",
            "revision_id": "rev-1",
            "entry_file": "src/main.tsx",
            "files": {"src/main.tsx": "export {}"},
            "idle_timeout_seconds": 180,
            "dependency_hash": "hash",
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

    workspace_sync_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/workspace/sync",
        headers=headers,
        json={
            "workspace_path": "/workspace/live",
            "files": {"src/main.tsx": "export {}"},
        },
    )
    assert workspace_sync_response.status_code == 200

    archive_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/workspace/archive",
        headers=headers,
        json={"workspace_path": "/workspace/live/dist", "format": "tar.gz"},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["format"] == "tar.gz"

    stop_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/stop",
        headers=headers,
        json={},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
    assert stopped_sandboxes == ["sandbox-1"]


@pytest.mark.asyncio
async def test_dev_shim_opencode_endpoint_returns_host_client_base_url(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-question"
    project_dir.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    class _FakeHostClient:
        _config = SimpleNamespace(base_url="http://127.0.0.1:4141", api_key=None, extra_headers=None)

        async def ensure_healthy(self, *, force=False):
            return None

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    endpoint_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-question/opencode/endpoint",
        headers=headers,
        json={
            "workspace_path": "/workspace",
        },
    )
    assert endpoint_response.status_code == 200
    payload = endpoint_response.json()
    assert payload["base_url"] == "http://127.0.0.1:4141"
    assert payload["workspace_path"] == str(project_dir)


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_prefers_stage_workspace_when_valid(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-2"
    stage_workspace = project_dir / ".talmudpedia" / "stage" / "run-1" / "workspace"
    stage_workspace.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    class _FakeHostClient:
        _config = SimpleNamespace(base_url="http://127.0.0.1:4141", api_key=None, extra_headers=None)

        async def ensure_healthy(self, *, force=False):
            return None

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    endpoint_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-2/opencode/endpoint",
        headers=headers,
        json={
            "workspace_path": str(stage_workspace),
        },
    )
    assert endpoint_response.status_code == 200
    assert endpoint_response.json()["workspace_path"] == str(stage_workspace)


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_maps_virtual_workspace_path(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-virtual"
    stage_workspace = project_dir / ".talmudpedia" / "stage" / "run-virtual" / "workspace"
    stage_workspace.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    class _FakeHostClient:
        _config = SimpleNamespace(base_url="http://127.0.0.1:4141", api_key=None, extra_headers=None)

        async def ensure_healthy(self, *, force=False):
            return None

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    endpoint_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-virtual/opencode/endpoint",
        headers=headers,
        json={
            "workspace_path": "/workspace/.talmudpedia/stage/run-virtual/workspace",
        },
    )
    assert endpoint_response.status_code == 200
    assert endpoint_response.json()["workspace_path"] == str(stage_workspace)


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
        "/internal/sandbox-controller/sessions/sandbox-3/opencode/endpoint",
        headers=headers,
        json={
            "workspace_path": "/workspace",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Draft dev sandbox is not running"


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_uses_per_sandbox_client_when_enabled(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "1")

    project_dir = tmp_path / "sandbox-4"
    stage_workspace = project_dir / ".talmudpedia" / "stage" / "run-4" / "workspace"
    stage_workspace.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    captured: dict[str, str] = {}

    class _FakeOpenCodeClient:
        _config = SimpleNamespace(base_url="http://127.0.0.1:4141", api_key=None, extra_headers=None)

        async def ensure_healthy(self, *, force=False):
            return None

    async def _fake_get_per_sandbox_client(*, sandbox_id: str, workspace_path: str):
        captured["client_sandbox_id"] = sandbox_id
        captured["client_workspace_path"] = workspace_path
        return _FakeOpenCodeClient()

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_get_per_sandbox_opencode_client", _fake_get_per_sandbox_client)

    headers = {"Authorization": "Bearer dev-token"}
    response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-4/opencode/endpoint",
        headers=headers,
        json={
            "workspace_path": "/workspace/.talmudpedia/stage/run-4/workspace",
        },
    )

    assert response.status_code == 200
    assert response.json()["base_url"] == "http://127.0.0.1:4141"
    assert captured["client_sandbox_id"] == "sandbox-4"
    assert captured["client_workspace_path"] == str(stage_workspace)


@pytest.mark.asyncio
async def test_dev_shim_opencode_start_rejects_invalid_requested_workspace(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-invalid"
    project_dir.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())

    headers = {"Authorization": "Bearer dev-token"}
    response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-invalid/opencode/endpoint",
        headers=headers,
        json={
            "workspace_path": "/workspace/.talmudpedia/stage/run-invalid/workspace",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Requested workspace path is invalid or outside sandbox project scope"
