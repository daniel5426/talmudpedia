import pytest
from sqlalchemy import select
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from ._helpers import admin_headers, seed_admin_tenant_and_agent, seed_published_app, start_publish_and_wait
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionKind,
    PublishedAppVisibility,
)
from app.services.published_app_bundle_storage import PublishedAppBundleAssetNotFound


@pytest.mark.asyncio
async def test_public_resolve_and_config(client, db_session):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="resolver-app",
        auth_enabled=True,
        auth_providers=["password", "google"],
        description="Resolver app description",
        logo_url="https://cdn.example.com/resolver.png",
        auth_template_key="auth-split",
    )

    resolve_resp = await client.get("/public/apps/resolve?host=resolver-app.apps.localhost")
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["app"]["slug"] == "resolver-app"

    config_resp = await client.get(f"/public/apps/{app.slug}/config")
    assert config_resp.status_code == 200
    payload = config_resp.json()
    assert payload["id"] == str(app.id)
    assert payload["description"] == "Resolver app description"
    assert payload["logo_url"] == "https://cdn.example.com/resolver.png"
    assert payload["visibility"] == "public"
    assert payload["auth_enabled"] is True
    assert "google" in payload["auth_providers"]
    assert payload["auth_template_key"] == "auth-split"


@pytest.mark.asyncio
async def test_public_resolve_rejects_unknown_host(client):
    resp = await client.get("/public/apps/resolve?host=example.com")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_private_published_app_is_hidden_from_public_endpoints(client, db_session):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="private-resolver-app",
        visibility=PublishedAppVisibility.private,
        auth_enabled=True,
        auth_providers=["password"],
    )

    resolve_resp = await client.get("/public/apps/resolve?host=private-resolver-app.apps.localhost")
    assert resolve_resp.status_code == 404

    config_resp = await client.get(f"/public/apps/{app.slug}/config")
    assert config_resp.status_code == 404

    runtime_resp = await client.get(f"/public/apps/{app.slug}/runtime")
    assert runtime_resp.status_code == 404

    signup_resp = await client.post(
        f"/public/apps/{app.slug}/auth/signup",
        json={"email": "private-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 404

    chat_resp = await client.post(
        f"/public/apps/{app.slug}/chat/stream",
        json={"input": "hello", "messages": []},
    )
    assert chat_resp.status_code == 404


@pytest.mark.asyncio
async def test_public_runtime_descriptor_and_ui_source_removed(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Runtime Descriptor App",
            "slug": "runtime-descriptor-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    _, publish_status = await start_publish_and_wait(client, app_id=app_id, headers=headers)
    assert publish_status["status"] == "succeeded"
    assert publish_status["published_revision_id"]

    runtime_resp = await client.get("/public/apps/runtime-descriptor-app/runtime")
    assert runtime_resp.status_code == 200
    runtime_payload = runtime_resp.json()
    assert runtime_payload["slug"] == "runtime-descriptor-app"
    assert runtime_payload["runtime_mode"] == "vite_static"
    assert runtime_payload["api_base_path"] == "/api/py"
    assert runtime_payload["revision_id"] == publish_status["published_revision_id"]

    ui_resp = await client.get("/public/apps/runtime-descriptor-app/ui")
    assert ui_resp.status_code == 410
    detail = ui_resp.json()["detail"]
    assert detail["code"] == "UI_SOURCE_MODE_REMOVED"


@pytest.mark.asyncio
async def test_preview_asset_proxy_streams_dist_asset(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Preview Asset App",
            "slug": "preview-asset-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    state_payload = state_resp.json()
    draft_revision_id = state_payload["current_draft_revision"]["id"]
    preview_token = state_payload["preview_token"]
    assert preview_token

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    revision_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert revision_row is not None
    revision_row.dist_storage_prefix = "apps/t/a/revisions/r1/dist"
    revision_row.dist_manifest = {"entry_html": "index.html"}
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/r1/dist"
            assert asset_path == "assets/main.js"
            return b"console.log('ok');", "application/javascript"

    monkeypatch.setattr(
        "app.api.routers.published_apps_public.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    asset_path = f"/public/apps/preview/revisions/{draft_revision_id}/assets/assets/main.js"
    asset_resp = await client.get(f"{asset_path}?preview_token={preview_token}")
    assert asset_resp.status_code == 200
    assert asset_resp.headers["content-type"].startswith("application/javascript")
    assert "console.log('ok');" in asset_resp.text
    assert "published_app_preview_token=" in (asset_resp.headers.get("set-cookie") or "")

    cookie_asset_resp = await client.get(asset_path)
    assert cookie_asset_resp.status_code == 200
    assert "console.log('ok');" in cookie_asset_resp.text

    runtime_resp = await client.get(
        f"/public/apps/preview/revisions/{draft_revision_id}/runtime",
        headers={"Authorization": f"Bearer {preview_token}"},
    )
    assert runtime_resp.status_code == 200
    runtime_payload = runtime_resp.json()
    preview_url = runtime_payload["preview_url"]
    assert "/assets/index.html" in preview_url
    preview_query = parse_qs(urlparse(preview_url).query)
    assert preview_query.get("preview_token") == [preview_token]
    assert runtime_payload["asset_base_url"].endswith("/assets/")


@pytest.mark.asyncio
async def test_preview_runtime_allows_valid_query_token_when_auth_header_is_invalid(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Preview Runtime Token Fallback App",
            "slug": "preview-runtime-token-fallback-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    state_payload = state_resp.json()
    draft_revision_id = state_payload["current_draft_revision"]["id"]
    preview_token = state_payload["preview_token"]
    assert preview_token

    runtime_resp = await client.get(
        f"/public/apps/preview/revisions/{draft_revision_id}/runtime?preview_token={preview_token}",
        headers={"Authorization": "Bearer invalid-preview-token"},
    )
    assert runtime_resp.status_code == 200
    payload = runtime_resp.json()
    assert payload["revision_id"] == draft_revision_id
    assert "/assets/" in payload["asset_base_url"]


@pytest.mark.asyncio
async def test_preview_asset_html_rewrites_relative_assets_with_preview_token(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Preview HTML Rewrite App",
            "slug": "preview-html-rewrite-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    state_payload = state_resp.json()
    draft_revision_id = state_payload["current_draft_revision"]["id"]
    preview_token = state_payload["preview_token"]
    assert preview_token

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    revision_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert revision_row is not None
    revision_row.dist_storage_prefix = "apps/t/a/revisions/rewrite/dist"
    revision_row.dist_manifest = {"entry_html": "index.html"}
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/rewrite/dist"
            assert asset_path == "index.html"
            html = (
                '<!doctype html><html><head>'
                '<link rel="stylesheet" href="./assets/main.css">'
                '</head><body>'
                '<script type="module" src="./assets/main.js"></script>'
                "</body></html>"
            )
            return html.encode("utf-8"), "text/html"

    monkeypatch.setattr(
        "app.api.routers.published_apps_public.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    resp = await client.get(
        f"/public/apps/preview/revisions/{draft_revision_id}/assets/index.html?preview_token={preview_token}"
    )
    assert resp.status_code == 200
    text = resp.text
    assert f"./assets/main.css?preview_token={preview_token}" in text
    assert f"./assets/main.js?preview_token={preview_token}" in text


@pytest.mark.asyncio
async def test_published_asset_proxy_streams_dist_asset(client, db_session, monkeypatch):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="published-asset-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key="chat-classic",
        template_runtime="vite_static",
        files={"src/main.tsx": "export default {};"},
        dist_storage_prefix="apps/t/a/revisions/published/dist",
        dist_manifest={"entry_html": "index.html"},
        created_by=user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/published/dist"
            assert asset_path == "assets/main.js"
            return b"console.log('published-ok');", "application/javascript"

    monkeypatch.setattr(
        "app.api.routers.published_apps_public.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    resp = await client.get(f"/public/apps/{app.slug}/assets/assets/main.js")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/javascript")
    assert "console.log('published-ok');" in resp.text


@pytest.mark.asyncio
async def test_published_asset_proxy_falls_back_to_index_for_spa_routes(client, db_session, monkeypatch):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="published-spa-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key="chat-classic",
        template_runtime="vite_static",
        files={"src/main.tsx": "export default {};"},
        dist_storage_prefix="apps/t/a/revisions/published-spa/dist",
        dist_manifest={"entry_html": "index.html"},
        created_by=user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/published-spa/dist"
            if asset_path == "nested/client-route":
                raise PublishedAppBundleAssetNotFound("missing")
            assert asset_path == "index.html"
            return b"<html><body>Published SPA</body></html>", "text/html"

    monkeypatch.setattr(
        "app.api.routers.published_apps_public.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    resp = await client.get(f"/public/apps/{app.slug}/assets/nested/client-route")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Published SPA" in resp.text
