from __future__ import annotations

import json

import httpx
import pytest

from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientConfig,
    PublishedAppDraftDevRuntimeClientError,
)


def _client() -> PublishedAppDraftDevRuntimeClient:
    return PublishedAppDraftDevRuntimeClient(
        PublishedAppDraftDevRuntimeClientConfig(
            controller_url="http://sandbox-controller.local",
            controller_token="dev-token",
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
        )
    )


@pytest.mark.asyncio
async def test_ensure_opencode_endpoint_uses_dedicated_start_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        reason_phrase = "OK"
        text = ""

        def json(self):
            return {
                "sandbox_id": "sandbox-1",
                "base_url": "http://127.0.0.1:4141",
                "workspace_path": "/workspace",
                "extra_headers": {"x-test": "1"},
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            captured["method"] = method
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("APPS_DRAFT_DEV_CONTROLLER_OPENCODE_START_TIMEOUT_SECONDS", "42")

    client = _client()
    result = await client.ensure_opencode_endpoint(
        sandbox_id="sandbox-1",
        workspace_path="/workspace",
    )
    assert result.base_url == "http://127.0.0.1:4141"
    assert result.workspace_path == "/workspace"
    assert result.extra_headers == {"x-test": "1"}
    timeout = captured.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 42


@pytest.mark.asyncio
async def test_ensure_opencode_endpoint_reports_exception_class_when_message_empty(monkeypatch: pytest.MonkeyPatch):
    class _SilentStartError(Exception):
        def __str__(self) -> str:
            return ""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            raise _SilentStartError()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    client = _client()
    with pytest.raises(PublishedAppDraftDevRuntimeClientError) as exc_info:
        await client.ensure_opencode_endpoint(
            sandbox_id="sandbox-1",
            workspace_path="/workspace",
        )
    assert "SilentStartError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_start_session_uses_dedicated_start_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        reason_phrase = "OK"
        text = ""

        def json(self):
            return {"sandbox_id": "sandbox-1", "preview_url": "https://preview.local/sandbox/sandbox-1/"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("APPS_DRAFT_DEV_CONTROLLER_START_TIMEOUT_SECONDS", "77")

    client = _client()
    result = await client.start_session(
        session_id="session-1",
        runtime_generation=1,
        tenant_id="tenant-1",
        app_id="app-1",
        user_id="user-1",
        revision_id="revision-1",
        app_slug="app-1",
        agent_id="agent-1",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default 1;"},
        idle_timeout_seconds=180,
        dependency_hash="dep-hash",
        draft_dev_token="token-1",
    )
    assert result["sandbox_id"] == "sandbox-1"
    timeout = captured.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 77


@pytest.mark.asyncio
async def test_sync_session_uses_dedicated_sync_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        reason_phrase = "OK"
        text = ""

        def json(self):
            return {"sandbox_id": "sandbox-1", "status": "running"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("APPS_DRAFT_DEV_CONTROLLER_SYNC_TIMEOUT_SECONDS", "64")

    client = _client()
    result = await client.sync_session(
        sandbox_id="sandbox-1",
        app_id="app-1",
        app_slug="app-1",
        agent_id="agent-1",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default 1;"},
        idle_timeout_seconds=180,
        dependency_hash="dep-hash",
        install_dependencies=True,
    )
    assert result["status"] == "running"
    timeout = captured.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 64
