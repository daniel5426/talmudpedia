from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routers import published_apps_builder_preview_proxy as preview_proxy_router
from app.api.routers.published_apps_preview_auth import create_preview_token
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.services import published_app_draft_dev_runtime_client as runtime_client_module
from app.services.published_app_auth_service import PublishedAppAuthRateLimitError
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientConfig,
)
from app.services.runtime_surface import RuntimeSurfaceService


def _fake_preview_app_and_revision(revision_id: str | None = "revision-1"):
    return (
        SimpleNamespace(
            id="app-1",
            organization_id="tenant-1",
            project_id="project-1",
            public_id="sefaria",
            name="Sefaria",
            description=None,
            logo_url=None,
            auth_enabled=True,
            auth_providers=["password"],
            auth_template_key="auth-classic",
            external_auth_oidc=False,
        ),
        SimpleNamespace(id=revision_id) if revision_id else None,
    )


async def _fake_load_preview_app_and_revision(**kwargs):
    _ = kwargs
    return _fake_preview_app_and_revision()


def _fake_session(preview_metadata: dict | None = None, *, revision_id: str | None = "revision-1"):
    return SimpleNamespace(
        id="session-1",
        published_app_id="app-1",
        revision_id=revision_id,
        backend_metadata=preview_metadata or {},
        draft_workspace=None,
    )


def _preview_token(*, app_id: str = "app-1", session_id: str = "session-1", revision_id: str | None = "revision-1") -> str:
    return create_preview_token(
        subject="user-1",
        organization_id="tenant-1",
        app_id=app_id,
        preview_target_type="draft_dev_session",
        preview_target_id=session_id,
        revision_id=revision_id,
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
        organization_id="tenant-1",
        app_id="app-1",
        user_id="user-1",
        revision_id="revision-1",
        app_public_id="app-1",
        agent_id="agent-1",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default 1;"},
        idle_timeout_seconds=180,
        dependency_hash="dep-hash",
    )

    assert result["runtime_backend"] == "sprite"
    assert captured["preview_base_path"] == "/public/apps-builder/draft-dev/sessions/session-1/preview/"


@pytest.mark.asyncio
async def test_runtime_client_delegates_live_preview_context_updates_to_selected_backend(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class _FakeBackend:
        backend_name = "sprite"
        is_remote = True

        async def update_live_preview_context(self, **kwargs):
            captured.update(kwargs)
            return {"sandbox_id": kwargs["sandbox_id"], "status": "updated"}

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

    result = await client.update_live_preview_context(
        sandbox_id="sprite-app-1",
        workspace_fingerprint="fp-1",
    )

    assert result["status"] == "updated"
    assert captured == {
        "sandbox_id": "sprite-app-1",
        "workspace_fingerprint": "fp-1",
    }


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
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    preview_token = _preview_token()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token={preview_token}&v=123",
    )

    assert response.status_code == 200
    assert response.headers["x-upstream"] == "static"
    assert "runtime_token" not in str(captured["url"])
    assert captured["headers"]["Authorization"] == "Bearer sprite-secret"
    assert captured["headers"]["x-sprite-service"] == "builder-static-preview"
    assert preview_proxy_router.PREVIEW_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_builder_preview_runtime_bootstrap_allows_revisionless_session(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return _fake_session(revision_id=None)

    async def _fake_load_preview_app_and_revision_none(**kwargs):
        _ = kwargs
        return _fake_preview_app_and_revision(revision_id=None)

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision_none)

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/runtime/bootstrap?runtime_token={_preview_token(revision_id=None)}",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["app_id"] == "app-1"
    assert payload["revision_id"] is None


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
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    stale_query_token = _preview_token(app_id="other-app")
    cookie_token = _preview_token()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token={stale_query_token}",
        cookies={preview_proxy_router.PREVIEW_COOKIE_NAME: cookie_token},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_builder_preview_thread_list_uses_runtime_surface(monkeypatch: pytest.MonkeyPatch, client):
    app = SimpleNamespace(id=uuid4(), organization_id=uuid4(), project_id=uuid4())
    thread = SimpleNamespace(
        id=uuid4(),
        title="Preview thread",
        status="active",
        surface=AgentThreadSurface.published_host_runtime,
        agent_id=None,
        last_run_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
        external_user_id=None,
        external_session_id=None,
    )
    calls: list[tuple[int, int, str, str]] = []

    async def _fake_load_preview_request_context(**kwargs):
        _ = kwargs
        return SimpleNamespace(id="session-1"), app, SimpleNamespace(id="revision-1"), {"scope": ["apps.preview"]}, "token-1"

    async def _fake_resolve_optional_principal_from_cookie(**kwargs):
        _ = kwargs
        return {"app_account_id": str(uuid4())}, False

    async def _fake_list_threads(self, *, scope, skip, limit):
        calls.append((skip, limit, str(scope.organization_id), str(scope.published_app_id)))
        return [thread], 1

    monkeypatch.setattr(preview_proxy_router, "_load_preview_request_context", _fake_load_preview_request_context)
    monkeypatch.setattr(preview_proxy_router, "_resolve_optional_principal_from_cookie", _fake_resolve_optional_principal_from_cookie)
    monkeypatch.setattr(RuntimeSurfaceService, "list_threads", _fake_list_threads)

    response = await client.get("/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/threads")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Preview thread"
    assert calls == [(0, 20, str(app.organization_id), str(app.id))]


@pytest.mark.asyncio
async def test_builder_preview_thread_detail_uses_runtime_surface(monkeypatch: pytest.MonkeyPatch, client):
    app = SimpleNamespace(id=uuid4(), organization_id=uuid4(), project_id=uuid4())
    thread_id = uuid4()
    calls: list[tuple[str, int, bool, str, str]] = []

    async def _fake_load_preview_request_context(**kwargs):
        _ = kwargs
        return SimpleNamespace(id="session-1"), app, SimpleNamespace(id="revision-1"), {"scope": ["apps.preview"]}, "token-1"

    async def _fake_resolve_optional_principal_from_cookie(**kwargs):
        _ = kwargs
        return {"app_account_id": str(uuid4())}, False

    async def _fake_get_thread_detail(self, *, scope, thread_id, options, event_view):
        _ = event_view
        calls.append(
            (
                str(thread_id),
                options.limit,
                options.include_subthreads,
                str(scope.organization_id),
                str(scope.published_app_id),
            )
        )
        return {"id": str(thread_id), "turns": [], "paging": {"has_more": False, "next_before_turn_index": None}}

    monkeypatch.setattr(preview_proxy_router, "_load_preview_request_context", _fake_load_preview_request_context)
    monkeypatch.setattr(preview_proxy_router, "_resolve_optional_principal_from_cookie", _fake_resolve_optional_principal_from_cookie)
    monkeypatch.setattr(RuntimeSurfaceService, "get_thread_detail", _fake_get_thread_detail)

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/threads/{thread_id}?include_subthreads=true&limit=7",
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(thread_id)
    assert calls == [(str(thread_id), 7, True, str(app.organization_id), str(app.id))]


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
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    stale_cookie_token = _preview_token(app_id="other-app")
    fresh_query_token = _preview_token()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token={fresh_query_token}",
        cookies={preview_proxy_router.PREVIEW_COOKIE_NAME: stale_cookie_token},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_builder_preview_proxy_clears_stale_preview_cookie_on_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return _fake_session()

    def _fake_resolve_preview_token_for_session(**kwargs):
        _ = kwargs
        raise HTTPException(status_code=401, detail="Preview token has expired")

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_resolve_preview_token_for_session", _fake_resolve_preview_token_for_session)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/",
        cookies={preview_proxy_router.PREVIEW_COOKIE_NAME: "stale-preview-cookie"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Preview token has expired"
    set_cookie_header = response.headers.get("set-cookie") or ""
    assert f"{preview_proxy_router.PREVIEW_COOKIE_NAME}=" in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "expires=" in set_cookie_header.lower()


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
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    preview_token = _preview_token()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/?runtime_token={preview_token}&preview_route=%2Fchat",
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
    monkeypatch.setattr(preview_proxy_router.httpx, "AsyncClient", _FakeAsyncClient)
    preview_token = _preview_token()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/assets/index-abc.js?runtime_token={preview_token}",
    )

    assert response.status_code == 200
    assert captured["url"] == "https://sprite-host.example/assets/index-abc.js"
    assert response.text == "console.log('ok')"


@pytest.mark.asyncio
async def test_builder_preview_status_route_returns_stored_live_preview_without_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    session = _fake_session(
        {
            "live_preview": {
                "mode": "build_watch_static",
                "status": "building",
            }
        }
    )
    session.draft_workspace = SimpleNamespace(
        backend_metadata={
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
    )

    async def _fake_load_session(*, db, session_id):
        _ = db, session_id
        return session

    async def _fake_touch_preview_session_activity(*, db, session, **kwargs):
        _ = db, session, kwargs
        return False

    monkeypatch.setattr(preview_proxy_router, "_load_session", _fake_load_session)
    monkeypatch.setattr(preview_proxy_router, "_load_preview_app_and_revision", _fake_load_preview_app_and_revision)
    monkeypatch.setattr(preview_proxy_router, "_touch_preview_session_activity", _fake_touch_preview_session_activity)
    preview_token = _preview_token()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/status?runtime_token={preview_token}",
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


@pytest.mark.asyncio
async def test_builder_preview_login_maps_password_throttle_to_429(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_preview_request_context(**kwargs):
        _ = kwargs
        session = _fake_session()
        app, revision = _fake_preview_app_and_revision()
        return session, app, revision, None, None

    async def _fake_login_with_password(self, *, app, email, password, client_ip=None):
        _ = self, app, email, password, client_ip
        raise PublishedAppAuthRateLimitError("Too many failed login attempts. Try again later.")

    monkeypatch.setattr(preview_proxy_router, "_load_preview_request_context", _fake_load_preview_request_context)
    monkeypatch.setattr(
        "app.services.published_app_auth_service.PublishedAppAuthService.login_with_password",
        _fake_login_with_password,
    )

    response = await client.post(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/auth/login",
        json={"email": "preview@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many failed login attempts. Try again later."


@pytest.mark.asyncio
async def test_builder_preview_google_start_sets_csrf_state_cookie(monkeypatch: pytest.MonkeyPatch, client):
    async def _fake_load_preview_request_context(**kwargs):
        _ = kwargs
        session = _fake_session()
        app, revision = _fake_preview_app_and_revision()
        app.auth_providers = ["google"]
        return session, app, revision, None, None

    async def _fake_get_google_credential(self, organization_id):
        _ = self, organization_id
        return SimpleNamespace(credentials={"client_id": "google-client", "redirect_uri": "https://accounts.example/callback"})

    monkeypatch.setattr(preview_proxy_router, "_load_preview_request_context", _fake_load_preview_request_context)
    monkeypatch.setattr("app.services.published_app_auth_service.PublishedAppAuthService.get_google_credential", _fake_get_google_credential)

    response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/auth/google/start?return_to=/done",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "published_app_google_oauth_state_preview=" in response.headers.get("set-cookie", "")
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert state


@pytest.mark.asyncio
async def test_builder_preview_google_callback_rejects_missing_csrf_state_cookie(
    monkeypatch: pytest.MonkeyPatch,
    client,
):
    async def _fake_load_preview_request_context(**kwargs):
        _ = kwargs
        session = _fake_session()
        app, revision = _fake_preview_app_and_revision()
        app.auth_providers = ["google"]
        return session, app, revision, None, None

    async def _fake_get_google_credential(self, organization_id):
        _ = self, organization_id
        return SimpleNamespace(
            credentials={
                "client_id": "google-client",
                "client_secret": "google-secret",
                "redirect_uri": "https://accounts.example/callback",
            }
        )

    monkeypatch.setattr(preview_proxy_router, "_load_preview_request_context", _fake_load_preview_request_context)
    monkeypatch.setattr("app.services.published_app_auth_service.PublishedAppAuthService.get_google_credential", _fake_get_google_credential)

    start_response = await client.get(
        "/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/auth/google/start?return_to=/done",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start_response.headers["location"]).query)["state"][0]
    client.cookies.clear()

    response = await client.get(
        f"/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/auth/google/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid OAuth state" in response.json()["detail"]
