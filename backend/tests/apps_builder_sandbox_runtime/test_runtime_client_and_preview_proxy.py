from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.api.routers import published_apps_builder_preview_proxy as preview_proxy_router
from app.services import published_app_draft_dev_runtime_client as runtime_client_module
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientConfig,
)


def _fake_preview_app_and_revision():
    return (
        SimpleNamespace(
            id="app-1",
            slug="sefaria",
            name="Sefaria",
            description=None,
            logo_url=None,
            auth_enabled=True,
            auth_providers=["password"],
            auth_template_key="auth-classic",
            external_auth_oidc=False,
        ),
        SimpleNamespace(id="revision-1"),
    )


@pytest.mark.asyncio
async def test_runtime_client_delegates_start_session_to_selected_sprite_backend(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeBackend:
        backend_name = "sprite"
        is_remote = True

        async def start_session(self, **kwargs):
            captured.update(kwargs)
            return {"sandbox_id": "sprite-app-1", "status": "serving", "runtime_backend": "sprite"}

    monkeypatch.setattr(runtime_client_module, "build_published_app_sandbox_backend", lambda config: _FakeBackend())

    client = PublishedAppDraftDevRuntimeClient(
        PublishedAppDraftDevRuntimeClientConfig(
            controller_url=None,
            controller_token=None,
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
            backend="sprite",
            preview_proxy_base_path="/public/apps-builder/draft-dev/sessions",
            sprite_api_base_url="https://api.sprites.dev",
            sprite_api_token="sprite-test-token",
            sprite_name_prefix="apps-builder",
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

    assert result["runtime_backend"] == "sprite"
    assert captured["preview_base_path"] == "/public/apps-builder/draft-dev/sessions/session-1/preview/"


@pytest.mark.asyncio
async def test_builder_preview_proxy_accepts_valid_token_and_forwards_sprite_auth(monkeypatch: pytest.MonkeyPatch, client):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-secret")

    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={},
            draft_workspace=SimpleNamespace(
                backend_metadata={
                    "preview": {
                        "upstream_base_url": "https://sprite-host.example",
                        "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                        "upstream_path": "/",
                        "auth_header_name": "Authorization",
                        "auth_token_env": "APPS_SPRITE_API_TOKEN",
                        "auth_token_prefix": "Bearer ",
                        "extra_headers": {"x-sprite-service": "builder-preview"},
                    }
                }
            ),
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
            captured["content"] = content
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1&v=123",
    )

    assert response.status_code == 200
    assert response.headers["x-upstream"] == "vite"
    assert "runtime_token" not in str(captured["url"])
    assert captured["headers"]["Authorization"] == "Bearer sprite-secret"
    assert captured["headers"]["x-sprite-service"] == "builder-preview"
    assert preview_proxy_router.PREVIEW_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_builder_preview_proxy_rewrites_vite_html_asset_paths(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            },
            draft_workspace=None,
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = (
            b'<!doctype html><html><head>'
            b'<script type="module" src="/@vite/client"></script>'
            b'<script type="module">import RefreshRuntime from "/@react-refresh";</script>'
            b'</head><body><script type="module" src="/src/main.tsx"></script></body></html>'
        )

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, url, headers, content
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/@vite/client' in response.text
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/@react-refresh' in response.text
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/src/main.tsx' in response.text
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/chat/stream' in response.text
    assert "__talmudpediaPreviewPathShimInstalled" in response.text
    assert "previewBasePath = \"/public/apps-builder/draft-dev/sessions/session-1/preview\"" in response.text
    assert "window.__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH = previewBasePath" in response.text


@pytest.mark.asyncio
async def test_builder_preview_proxy_rewrites_asset_request_to_upstream_path(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            },
            draft_workspace=None,
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
            _ = headers, content
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/src/main.tsx?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert captured["url"] == "https://sprite-host.example/src/main.tsx"


@pytest.mark.asyncio
async def test_builder_preview_proxy_rewrites_vite_module_imports_and_disables_cache(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            },
            draft_workspace=None,
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {
            "content-type": "application/javascript; charset=utf-8",
            "etag": '"vite-etag"',
            "last-modified": "Sun, 09 Mar 2026 00:00:00 GMT",
        }
        content = (
            b'import "/@vite/client";'
            b'import "/node_modules/.vite/deps/react.js?v=abc123";'
            b'import "/runtime-sdk/src/index.ts";'
            b'import App from "/src/App.tsx";'
        )

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
            _ = content
            return _FakeResponse()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/src/main.tsx?runtime_token=preview-token-1",
        headers={"If-None-Match": '"old-etag"', "If-Modified-Since": "Sun, 09 Mar 2026 00:00:00 GMT"},
    )

    assert response.status_code == 200
    assert captured["url"] == "https://sprite-host.example/src/main.tsx"
    assert "If-None-Match" not in captured["headers"]
    assert "If-Modified-Since" not in captured["headers"]
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/@vite/client' in response.text
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/node_modules/.vite/deps/react.js?v=abc123' in response.text
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/runtime-sdk/src/index.ts' in response.text
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/src/App.tsx' in response.text
    assert response.headers.get("cache-control") == "no-store"
    assert "etag" not in response.headers
    assert "last-modified" not in response.headers


@pytest.mark.asyncio
async def test_builder_preview_proxy_rewrites_css_url_asset_paths(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            },
            draft_workspace=None,
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, url, headers, content
            return httpx.Response(
                200,
                headers={"content-type": "text/css; charset=utf-8"},
                text='@font-face{src:url("/node_modules/@fontsource-variable/noto-sans/files/noto-sans-latin-wght-normal.woff2")}',
            )

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/src/index.css?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert '/public/apps-builder/draft-dev/sessions/session-1/preview/node_modules/@fontsource-variable/noto-sans/files/noto-sans-latin-wght-normal.woff2' in response.text


@pytest.mark.asyncio
async def test_builder_preview_proxy_returns_504_on_upstream_timeout(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            },
            draft_workspace=None,
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, url, headers, content
            raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1",
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "Draft dev preview upstream timed out"


@pytest.mark.asyncio
async def test_builder_preview_proxy_retries_transient_warmup_errors(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            backend_metadata={
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            },
            draft_workspace=None,
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    attempts = {"count": 0}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, url, headers, content
            attempts["count"] += 1
            if attempts["count"] < 3:
                return httpx.Response(504, headers={"content-type": "text/plain"}, text="warming")
            return httpx.Response(200, headers={"content-type": "application/javascript"}, text="import '/@vite/client'")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/@vite/client?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_builder_preview_proxy_refreshes_stale_upstream_target_after_connect_error(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    workspace = SimpleNamespace(
        backend_metadata={
            "preview": {
                "upstream_base_url": "https://stale-sprite-host.example",
                "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                "upstream_path": "/",
            }
        }
    )
    session = SimpleNamespace(
        id="session-1",
        published_app_id="app-1",
        revision_id="revision-1",
        sandbox_id="sprite-app-1",
        backend_metadata={},
        draft_workspace=workspace,
    )

    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return session

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    class _FakeRuntimeClient:
        def build_preview_proxy_path(self, session_id: str) -> str:
            return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/"

        async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int):
            assert sandbox_id == "sprite-app-1"
            assert idle_timeout_seconds == 0
            return {
                "sandbox_id": sandbox_id,
                "status": "serving",
                "runtime_backend": "sprite",
                "backend_metadata": {
                    "preview": {
                        "upstream_base_url": "https://fresh-sprite-host.example",
                        "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                        "upstream_path": "/",
                    }
                },
            }

    attempts: list[str] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, headers, content
            attempts.append(url)
            if "stale-sprite-host.example" in url:
                raise httpx.ConnectError(
                    "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch"
                )
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<html>ok</html>")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        preview_proxy_router.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: _FakeRuntimeClient()),
    )

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert attempts[0] == "https://stale-sprite-host.example/"
    assert attempts[1] == "https://fresh-sprite-host.example/"
    assert session.draft_workspace.backend_metadata["preview"]["upstream_base_url"] == "https://fresh-sprite-host.example"


@pytest.mark.asyncio
async def test_builder_preview_proxy_refreshes_stale_upstream_target_after_remote_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    workspace = SimpleNamespace(
        backend_metadata={
            "preview": {
                "upstream_base_url": "http://127.0.0.1:41001",
                "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                "upstream_path": "/",
            }
        }
    )
    session = SimpleNamespace(
        id="session-1",
        published_app_id="app-1",
        revision_id="revision-1",
        sandbox_id="sprite-app-1",
        backend_metadata={},
        draft_workspace=workspace,
    )

    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return session

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    class _FakeRuntimeClient:
        def build_preview_proxy_path(self, session_id: str) -> str:
            return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/"

        async def heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int):
            assert sandbox_id == "sprite-app-1"
            assert idle_timeout_seconds == 0
            return {
                "sandbox_id": sandbox_id,
                "status": "serving",
                "runtime_backend": "sprite",
                "backend_metadata": {
                    "preview": {
                        "upstream_base_url": "http://127.0.0.1:41002",
                        "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                        "upstream_path": "/",
                    }
                },
            }

    attempts: list[str] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, headers, content
            attempts.append(url)
            if url == "http://127.0.0.1:41001/":
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<html>ok</html>")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        preview_proxy_router.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: _FakeRuntimeClient()),
    )

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert attempts == ["http://127.0.0.1:41001/", "http://127.0.0.1:41002/"]
    assert session.draft_workspace.backend_metadata["preview"]["upstream_base_url"] == "http://127.0.0.1:41002"


@pytest.mark.asyncio
async def test_builder_preview_proxy_uses_sprite_tunnel_target_when_sprite_metadata_present(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            sandbox_id="sprite-app-1",
            backend_metadata={},
            draft_workspace=SimpleNamespace(
                backend_metadata={
                    "provider": "sprite",
                    "preview": {
                        "upstream_base_url": "https://bad-provider-host.example",
                        "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                        "upstream_path": "/",
                    },
                    "workspace": {
                        "sprite_name": "sprite-app-1",
                    },
                    "services": {
                        "preview_port": 8080,
                    },
                }
            ),
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
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

    class _FakeTunnelManager:
        async def ensure_tunnel(self, *, api_base_url: str, api_token: str, sprite_name: str, remote_host: str, remote_port: int):
            assert sprite_name == "sprite-app-1"
            assert remote_host == "127.0.0.1"
            assert remote_port == 8080
            return "http://127.0.0.1:45678"

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    async def _fake_load_preview_app_and_revision(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(preview_proxy_router, "get_sprite_proxy_tunnel_manager", lambda: _FakeTunnelManager())
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-secret")

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert captured["url"] == "http://127.0.0.1:45678/"
    assert "Authorization" not in captured["headers"]


@pytest.mark.asyncio
async def test_builder_preview_runtime_bootstrap_uses_preview_internal_prefix(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(id="session-1", published_app_id="app-1", revision_id="revision-1")

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    async def _fake_load_preview_app_and_revision(*, db, session):
        _ = db, session
        return _fake_preview_app_and_revision()

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/runtime/bootstrap?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "builder-preview"
    assert payload["chat_stream_path"] == "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/chat/stream"


@pytest.mark.asyncio
async def test_builder_preview_auth_state_uses_preview_namespace(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return SimpleNamespace(id="session-1", published_app_id="app-1", revision_id="revision-1")

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    async def _fake_load_preview_app_and_revision(*, db, session):
        _ = db, session
        return _fake_preview_app_and_revision()

    async def _fake_resolve_principal_from_cookie(*, db, request, expected_app):
        _ = db, request, expected_app
        return None, False

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router, "_resolve_optional_principal_from_cookie", _fake_resolve_principal_from_cookie)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/auth/state?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False
    assert payload["auth_enabled"] is True
    assert payload["app"]["slug"] == "sefaria"


def test_builder_preview_websocket_connect_options_forward_sprite_headers():
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
        target={
            "auth_header_name": "Authorization",
            "auth_token": "sprite-secret",
            "auth_token_prefix": "Bearer ",
            "extra_headers": json.dumps({"x-sprite-service": "builder-preview"}),
        },
    )

    assert ("Authorization", "Bearer sprite-secret") in headers
    assert ("x-sprite-service", "builder-preview") in headers
    assert ("origin", "http://localhost:3000") in headers
    assert ("user-agent", "pytest-agent") in headers
    assert subprotocols == ["vite-hmr", "custom-protocol"]
