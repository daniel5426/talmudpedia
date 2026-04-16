from __future__ import annotations

from types import SimpleNamespace

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


async def _fake_load_preview_app_and_revision(**kwargs):
    _ = kwargs
    return _fake_preview_app_and_revision()


def _fake_session(preview_metadata: dict | None = None):
    return SimpleNamespace(
        id="session-1",
        published_app_id="app-1",
        revision_id="revision-1",
        backend_metadata=preview_metadata or {},
        draft_workspace=None,
    )


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, headers: dict[str, str] | None = None, content: bytes = b""):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content


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
        return _fake_session(
            {
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                    "auth_header_name": "Authorization",
                    "auth_token_env": "APPS_SPRITE_API_TOKEN",
                    "auth_token_prefix": "Bearer ",
                    "extra_headers": {"x-sprite-service": "builder-static-preview"},
                }
            }
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    captured: dict[str, object] = {}

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
            return _FakeResponse(
                headers={"content-type": "text/html; charset=utf-8", "x-upstream": "static"},
                content=b"<html><head></head><body><div id='root'></div></body></html>",
            )

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1&v=123",
    )

    assert response.status_code == 200
    assert response.headers["x-upstream"] == "static"
    assert "runtime_token" not in str(captured["url"])
    assert captured["headers"]["Authorization"] == "Bearer sprite-secret"
    assert captured["headers"]["x-sprite-service"] == "builder-static-preview"
    assert preview_proxy_router.PREVIEW_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_builder_preview_proxy_prefers_cookie_token_over_stale_query_token(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return _fake_session(
            {
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            }
        )

    def _fake_decode(token: str):
        if token == "stale-query-token":
            return {"app_id": "other-app", "revision_id": "revision-1", "scope": ["apps.preview"]}
        if token == "cookie-token":
            return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}
        raise AssertionError(f"unexpected token {token}")

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, url, headers, content
            return _FakeResponse(headers={"content-type": "text/html; charset=utf-8"}, content=b"<html>ok</html>")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=stale-query-token",
        cookies={preview_proxy_router.PREVIEW_COOKIE_NAME: "cookie-token"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_builder_preview_proxy_falls_back_to_query_token_when_cookie_is_for_other_app(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return _fake_session(
            {
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            }
        )

    def _fake_decode(token: str):
        if token == "stale-cookie-token":
            return {"app_id": "other-app", "revision_id": "revision-1", "scope": ["apps.preview"]}
        if token == "fresh-query-token":
            return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}
        raise AssertionError(f"unexpected token {token}")

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            _ = method, url, headers, content
            return _FakeResponse(headers={"content-type": "text/html; charset=utf-8"}, content=b"<html>ok</html>")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=fresh-query-token",
        cookies={preview_proxy_router.PREVIEW_COOKIE_NAME: "stale-cookie-token"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_builder_preview_proxy_injects_runtime_context_and_static_route_bridge(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return _fake_session(
            {
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            }
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
            return _FakeResponse(
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"<!doctype html><html><head></head><body><div id='root'></div></body></html>",
            )

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token=preview-token-1&preview_route=%2Fchat",
    )

    assert response.status_code == 200
    assert "__APP_RUNTIME_CONTEXT" in response.text
    assert "__talmudpediaPreviewPathShimInstalled" in response.text
    assert "__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH" in response.text
    assert "runtime_token" not in response.text


@pytest.mark.asyncio
async def test_builder_preview_proxy_passthroughs_static_assets(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return _fake_session(
            {
                "preview": {
                    "upstream_base_url": "https://sprite-host.example",
                    "base_path": "/public/apps-builder/draft-dev/sessions/session-1/preview/",
                    "upstream_path": "/",
                }
            }
        )

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    captured: dict[str, object] = {}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            captured["url"] = url
            _ = method, headers, content
            return _FakeResponse(
                headers={"content-type": "application/javascript"},
                content=b"console.log('ok')",
            )

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/assets/index-abc.js?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert captured["url"] == "https://sprite-host.example/assets/index-abc.js"
    assert response.text == "console.log('ok')"


@pytest.mark.asyncio
async def test_builder_preview_status_route_heartbeats_and_returns_live_preview(monkeypatch: pytest.MonkeyPatch, client):
    session = _fake_session(
        {
            "live_preview": {
                "mode": "build_watch_static",
                "status": "building",
            }
        }
    )

    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return session

    def _fake_decode(token: str):
        assert token == "preview-token-1"
        return {"app_id": "app-1", "revision_id": "revision-1", "scope": ["apps.preview"]}

    class _FakeRuntimeService:
        def __init__(self, db):
            _ = db

        async def touch_session_activity(self, *, session, throttle_seconds):
            _ = session, throttle_seconds
            return False

        async def heartbeat_session(self, *, session):
            session.backend_metadata = {
                "live_preview": {
                    "mode": "build_watch_static",
                    "status": "ready",
                    "current_build_id": "build-2",
                    "last_successful_build_id": "build-2",
                    "workspace_fingerprint": "fp-1",
                    "supervisor": {
                        "build_watch_status": "running",
                        "static_server_status": "running",
                    },
                }
            }
            return session

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "decode_published_app_preview_token", _fake_decode)
    monkeypatch.setattr(preview_proxy_router, "PublishedAppDraftDevRuntimeService", _FakeRuntimeService)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/status?runtime_token=preview-token-1",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["last_successful_build_id"] == "build-2"
    assert response.json()["supervisor"]["static_server_status"] == "running"


@pytest.mark.asyncio
async def test_builder_preview_target_falls_back_to_sprite_session_identity_when_preview_metadata_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_tunnel(**kwargs):
        assert kwargs["sprite_name"] == "sprite-session-1"
        assert kwargs["remote_port"] == 8080
        return "http://127.0.0.1:49000"

    monkeypatch.setattr(
        preview_proxy_router,
        "load_published_app_sandbox_backend_config",
        lambda: SimpleNamespace(sprite_api_base_url="https://api.sprites.dev", sprite_api_token="sprite-token", sprite_preview_port=8080),
    )
    monkeypatch.setattr(
        preview_proxy_router,
        "get_sprite_proxy_tunnel_manager",
        lambda: SimpleNamespace(ensure_tunnel=_fake_tunnel),
    )

    target = await preview_proxy_router._resolve_preview_target(
        SimpleNamespace(
            id="session-1",
            published_app_id="app-1",
            revision_id="revision-1",
            sandbox_id="sprite-session-1",
            runtime_backend="sprite",
            backend_metadata={},
            draft_workspace=None,
        )
    )

    assert target["upstream_base_url"] == "http://127.0.0.1:49000"
    assert target["resolver_kind"] == "sprite_tunnel_fallback"
    assert target["provider"] == "sprite"
