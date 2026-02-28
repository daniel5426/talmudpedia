import pytest
from sqlalchemy import func, select

from app.db.postgres.models.chat import Chat, Message
from app.db.postgres.models.published_apps import PublishedAppRevision, PublishedAppRevisionKind
from tests.published_apps._helpers import seed_admin_tenant_and_agent, seed_published_app


def _host_headers(slug: str) -> dict[str, str]:
    return {"Host": f"{slug}.apps.localhost"}


@pytest.mark.asyncio
async def test_host_root_renders_same_url_auth_shell(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-auth-app",
        auth_enabled=True,
        auth_providers=["password"],
        description="Sign in to use this app",
        auth_template_key="auth-split",
    )

    resp = await client.get("/", headers=_host_headers(app.slug))
    assert resp.status_code == 200
    assert app.name in resp.text
    assert "Sign in to use this app" in resp.text
    assert "/_talmudpedia/auth/login" in resp.text


@pytest.mark.asyncio
async def test_host_signup_sets_cookie_and_auth_state(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-signup-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.slug),
        json={"email": "same-url-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    assert signup_resp.json()["status"] == "ok"
    assert "published_app_session=" in signup_resp.headers.get("set-cookie", "")

    state_resp = await client.get("/_talmudpedia/auth/state", headers=_host_headers(app.slug))
    assert state_resp.status_code == 200
    payload = state_resp.json()
    assert payload["authenticated"] is True
    assert payload["app"]["slug"] == app.slug
    assert payload["user"]["email"] == "same-url-user@example.com"


@pytest.mark.asyncio
async def test_host_chat_stream_requires_cookie_when_auth_enabled(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-chat-auth-required",
        auth_enabled=True,
        auth_providers=["password"],
    )

    resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers(app.slug),
        json={"input": "hello"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_host_chat_stream_uses_cookie_auth_and_persists(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-chat-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.slug),
        json={"email": "chat-cookie-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200

    async def fake_start_run(self, *args, **kwargs):
        return "host-run-123"

    async def fake_run_and_stream(self, *args, **kwargs):
        yield {
            "event": "token",
            "data": {"content": "Hello from host runtime"},
            "visibility": "client_safe",
        }

    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.start_run", fake_start_run)
    monkeypatch.setattr("app.api.routers.published_apps_public.AgentExecutorService.run_and_stream", fake_run_and_stream)

    stream_resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers(app.slug),
        json={"input": "Hi there"},
    )
    assert stream_resp.status_code == 200
    assert "Hello from host runtime" in stream_resp.text

    chat_count = await db_session.scalar(
        select(func.count(Chat.id)).where(Chat.published_app_id == app.id)
    )
    assert chat_count == 1

    message_count = await db_session.scalar(
        select(func.count(Message.id)).join(Chat, Message.chat_id == Chat.id).where(Chat.published_app_id == app.id)
    )
    assert message_count == 2


@pytest.mark.asyncio
async def test_legacy_public_published_path_endpoints_return_410(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="legacy-path-cut-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    runtime_resp = await client.get(f"/public/apps/{app.slug}/runtime")
    assert runtime_resp.status_code == 410

    signup_resp = await client.post(
        f"/public/apps/{app.slug}/auth/signup",
        json={"email": "legacy@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 410

    chat_resp = await client.post(
        f"/public/apps/{app.slug}/chat/stream",
        json={"input": "hello"},
    )
    assert chat_resp.status_code == 410


@pytest.mark.asyncio
async def test_host_assets_serve_dist_asset_with_assets_prefix(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-assets-app",
        auth_enabled=False,
        auth_providers=["password"],
    )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key="chat-classic",
        template_runtime="vite_static",
        files={"src/main.tsx": "export default {};"},
        dist_storage_prefix="apps/t/a/revisions/host-assets/dist",
        dist_manifest={"entry_html": "index.html"},
        created_by=owner.id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/host-assets/dist"
            assert asset_path == "assets/index-abc123.js"
            return b"console.log('ok')", "application/javascript"

    monkeypatch.setattr(
        "app.api.routers.published_apps_host_runtime.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    resp = await client.get("/assets/index-abc123.js", headers=_host_headers(app.slug))
    assert resp.status_code == 200
    assert "console.log('ok')" in resp.text
