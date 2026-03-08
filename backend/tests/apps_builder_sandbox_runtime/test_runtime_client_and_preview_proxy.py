from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routers import published_apps_builder_preview_proxy as preview_proxy_router
from app.services import published_app_draft_dev_runtime_client as runtime_client_module
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientConfig,
)


@pytest.mark.asyncio
async def test_runtime_client_delegates_start_session_to_selected_backend(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeBackend:
        backend_name = "e2b"
        is_remote = True

        async def start_session(self, **kwargs):
            captured.update(kwargs)
            return {"sandbox_id": "sandbox-1", "status": "running", "runtime_backend": "e2b"}

    monkeypatch.setattr(runtime_client_module, "build_published_app_sandbox_backend", lambda config: _FakeBackend())

    client = PublishedAppDraftDevRuntimeClient(
        PublishedAppDraftDevRuntimeClientConfig(
            controller_url=None,
            controller_token=None,
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
            backend="e2b",
            preview_proxy_base_path="/public/apps-builder/draft-dev/sessions",
        )
    )

    result = await client.start_session(
        session_id="session-1",
        runtime_generation=1,
        tenant_id="tenant-1",
        app_id="app-1",
        user_id="user-1",
        revision_id="revision-1",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default 1;"},
        idle_timeout_seconds=180,
        dependency_hash="dep-hash",
        draft_dev_token="draft-token",
    )

    assert result["runtime_backend"] == "e2b"
    assert captured["preview_base_path"] == "/public/apps-builder/draft-dev/sessions/session-1/preview/"


@pytest.mark.asyncio
async def test_builder_preview_proxy_sets_cookie_and_forwards_traffic_token(client, monkeypatch: pytest.MonkeyPatch):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sandbox-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "traffic_access_token": "traffic-secret",
                }
            },
        )

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8", "x-upstream": "vite"}
        content = b"<html>ok</html>"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["content"] = content
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1",
        headers={"Authorization": "Bearer ignored"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_builder_preview_proxy_accepts_valid_token_and_hides_runtime_token_from_upstream(client, monkeypatch: pytest.MonkeyPatch):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sandbox-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "traffic_access_token": "traffic-secret",
                }
            },
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8", "x-upstream": "vite"}
        content = b"<html>ok</html>"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers or {}
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1&v=123",
    )

    assert response.status_code == 200
    assert response.headers["x-upstream"] == "vite"
    assert "runtime_token" not in str(captured["url"])
    assert captured["headers"][preview_proxy_router.PREVIEW_PROXY_HEADER] == "traffic-secret"
    assert preview_proxy_router.PREVIEW_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_builder_preview_proxy_rewrites_asset_request_to_upstream_preview_base_path(client, monkeypatch: pytest.MonkeyPatch):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sandbox-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "traffic_access_token": "traffic-secret",
                }
            },
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "application/javascript"}
        content = b"console.log('ok')"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/src/main.tsx?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert captured["url"] == "https://sandbox-host.example/public/apps-builder/draft-dev/sessions/session-1/preview/src/main.tsx"


def test_builder_preview_websocket_connect_options_forward_origin_user_agent_and_protocols():
    websocket = SimpleNamespace(
        headers=SimpleNamespace(
            get=lambda key, default=None: {
                "origin": "http://localhost:3000",
                "user-agent": "pytest-agent",
            }.get(key, default),
            getlist=lambda key: ["vite-hmr, custom-protocol"] if key == "sec-websocket-protocol" else [],
        )
    )

    headers, subprotocols = preview_proxy_router._websocket_proxy_connect_options(
        websocket,
        target={"traffic_access_token": "traffic-secret"},
    )

    assert (preview_proxy_router.PREVIEW_PROXY_HEADER, "traffic-secret") in headers
    assert ("origin", "http://localhost:3000") in headers
    assert ("user-agent", "pytest-agent") in headers
    assert subprotocols == ["vite-hmr", "custom-protocol"]
