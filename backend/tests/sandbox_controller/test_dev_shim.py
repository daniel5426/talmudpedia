from __future__ import annotations

import asyncio
import os
import pytest

from app.api.routers import sandbox_controller_dev_shim as shim_router


@pytest.mark.asyncio
async def test_dev_shim_session_lifecycle_and_file_routes(client, monkeypatch):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")

    class _FakeManager:
        async def start_session(self, *, session_id, files, dependency_hash, draft_dev_token, preview_base_path="/"):
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

        async def prepare_publish_workspace(self, *, sandbox_id):
            return {
                "sandbox_id": sandbox_id,
                "workspace_path": f"/tmp/talmudpedia-draft-dev/{sandbox_id}/.talmudpedia/publish/current/workspace",
                "publish_workspace_path": f"/tmp/talmudpedia-draft-dev/{sandbox_id}/.talmudpedia/publish/current/workspace",
                "live_workspace_path": f"/tmp/talmudpedia-draft-dev/{sandbox_id}",
                "files": {"src/main.tsx": "export {}"},
                "file_count": 1,
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

    publish_prepare_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/publish/prepare",
        headers=headers,
        json={},
    )
    assert publish_prepare_response.status_code == 200
    assert publish_prepare_response.json()["file_count"] == 1

    workspace_sync_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/workspace/sync",
        headers=headers,
        json={
            "workspace_path": "/workspace/.talmudpedia/publish/current/workspace",
            "files": {"src/main.tsx": "export {}"},
        },
    )
    assert workspace_sync_response.status_code == 200

    archive_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-1/workspace/archive",
        headers=headers,
        json={"workspace_path": "/workspace/.talmudpedia/publish/current/workspace/dist", "format": "tar.gz"},
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
async def test_dev_shim_opencode_start_stream_cancel(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-2"
    project_dir.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    class _FakeHostClient:
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages, selected_agent_contract=None):
            assert sandbox_id == "sandbox-2"
            assert workspace_path == str(project_dir)
            return "host-run-ref-1"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "host-run-ref-1"
            yield {"event": "assistant.delta", "payload": {"content": "hello"}}
            yield {"event": "run.completed", "payload": {"status": "completed"}}

        async def cancel_run(self, *, run_ref, sandbox_id=None):
            assert run_ref == "host-run-ref-1"
            return True

        async def answer_question(self, *, run_ref, question_id, answers, sandbox_id=None):
            assert run_ref == "host-run-ref-1"
            assert question_id == "que_1"
            assert answers == [["A"]]
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
async def test_dev_shim_opencode_question_answer(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-question"
    project_dir.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    class _FakeHostClient:
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages, selected_agent_contract=None):
            return "host-run-ref-question"

        async def stream_run_events(self, *, run_ref):
            await asyncio.sleep(0.05)
            yield {
                "event": "tool.question",
                "payload": {
                    "request_id": "que_1",
                    "questions": [{"question": "Pick one", "options": [{"label": "A"}, {"label": "B"}]}],
                },
            }
            await asyncio.sleep(5)
            if False:  # pragma: no cover - keeps generator shape
                yield {"event": "noop"}

        async def cancel_run(self, *, run_ref, sandbox_id=None):
            return True

        async def answer_question(self, *, run_ref, question_id, answers, sandbox_id=None):
            assert run_ref == "host-run-ref-question"
            assert question_id == "que_1"
            assert answers == [["A"]]
            return True

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    start_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-question/opencode/start",
        headers=headers,
        json={
            "run_id": "run-question",
            "app_id": "app-1",
            "workspace_path": "/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["run_ref"] == "host-run-ref-question"

    answer_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-question/opencode/question-answer",
        headers=headers,
        json={"run_ref": "host-run-ref-question", "question_id": "que_1", "answers": [["A"]]},
    )
    assert answer_response.status_code == 200
    assert answer_response.json()["ok"] is True


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
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages, selected_agent_contract=None):
            assert sandbox_id == "sandbox-2"
            assert workspace_path == str(stage_workspace)
            return "host-run-ref-stage"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "host-run-ref-stage"
            yield {"event": "run.completed", "payload": {"status": "completed"}}

        async def cancel_run(self, *, run_ref, sandbox_id=None):
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
            "workspace_path": str(stage_workspace),
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["run_ref"] == "host-run-ref-stage"


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
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages, selected_agent_contract=None):
            assert workspace_path == str(stage_workspace)
            return "host-run-ref-virtual"

        async def stream_run_events(self, *, run_ref):
            yield {"event": "run.completed", "payload": {"status": "completed"}}

        async def cancel_run(self, *, run_ref, sandbox_id=None):
            return True

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    start_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-virtual/opencode/start",
        headers=headers,
        json={
            "run_id": "run-virtual",
            "app_id": "app-1",
            "workspace_path": "/workspace/.talmudpedia/stage/run-virtual/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["run_ref"] == "host-run-ref-virtual"


@pytest.mark.asyncio
async def test_dev_shim_opencode_cancel_flushes_terminal_event_for_hung_stream(client, monkeypatch, tmp_path):
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "1")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_TOKEN", "dev-token")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX", "0")

    project_dir = tmp_path / "sandbox-hung"
    project_dir.mkdir(parents=True, exist_ok=True)

    class _FakeManager:
        async def resolve_project_dir(self, *, sandbox_id):
            return str(project_dir)

    class _FakeHostClient:
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages, selected_agent_contract=None):
            return "host-run-ref-hung"

        async def stream_run_events(self, *, run_ref):
            while True:
                await asyncio.sleep(60)
                if False:  # pragma: no cover - keeps this as an async generator for shim pump typing
                    yield {"event": "noop"}

        async def cancel_run(self, *, run_ref, sandbox_id=None):
            return True

    monkeypatch.setattr(shim_router, "get_local_draft_dev_runtime_manager", lambda: _FakeManager())
    monkeypatch.setattr(shim_router, "_build_host_opencode_client", lambda: _FakeHostClient())

    headers = {"Authorization": "Bearer dev-token"}
    start_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-hung/opencode/start",
        headers=headers,
        json={
            "run_id": "run-hung",
            "app_id": "app-1",
            "workspace_path": "/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["run_ref"] == "host-run-ref-hung"

    cancel_response = await client.post(
        "/internal/sandbox-controller/sessions/sandbox-hung/opencode/cancel",
        headers=headers,
        json={"run_ref": "host-run-ref-hung"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancelled"] is True

    async with client.stream(
        "GET",
        "/internal/sandbox-controller/sessions/sandbox-hung/opencode/events",
        headers=headers,
        params={"run_ref": "host-run-ref-hung"},
    ) as stream_response:
        assert stream_response.status_code == 200
        body = (await stream_response.aread()).decode("utf-8")
        assert "run.cancelled" in body
        assert "run cancelled" in body.lower()


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
        async def ensure_healthy(self, *, force=False):
            return None

        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages, selected_agent_contract=None):
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
            "workspace_path": "/workspace/.talmudpedia/stage/run-4/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["run_ref"] == "sandbox-run-ref-4"
    assert captured["client_sandbox_id"] == "sandbox-4"
    assert captured["client_workspace_path"] == str(stage_workspace)
    assert captured["sandbox_id"] == "sandbox-4"
    assert captured["workspace_path"] == str(stage_workspace)


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
        "/internal/sandbox-controller/sessions/sandbox-invalid/opencode/start",
        headers=headers,
        json={
            "run_id": "run-invalid",
            "app_id": "app-1",
            "workspace_path": "/workspace/.talmudpedia/stage/run-invalid/workspace",
            "model_id": "openai/gpt-5",
            "prompt": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Requested workspace path is invalid or outside sandbox project scope"
