import pytest
from sqlalchemy import select
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from ._helpers import admin_headers, seed_admin_tenant_and_agent, seed_published_app, start_publish_and_wait
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppVisibility,
)


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

@pytest.mark.asyncio
async def test_public_ui_source_removed_endpoint_still_returns_410(client):
    resp = await client.get("/public/apps/some-app/ui")
    assert resp.status_code == 410
    detail = resp.json().get("detail", {})
    assert detail.get("code") == "UI_SOURCE_MODE_REMOVED"


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
    asset_resp = await client.get(
        asset_path,
        headers={"Authorization": f"Bearer {preview_token}"},
    )
    assert asset_resp.status_code == 200
    assert asset_resp.headers["content-type"].startswith("application/javascript")
    assert "console.log('ok');" in asset_resp.text
    set_cookie_header = asset_resp.headers.get("set-cookie") or ""
    assert "published_app_preview_token=" in set_cookie_header
    assert f"Path=/public/apps/preview/revisions/{draft_revision_id}" in set_cookie_header

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
    assert preview_query.get("preview_token") in (None, [])
    assert runtime_payload["asset_base_url"].endswith("/assets/")


@pytest.mark.asyncio
async def test_preview_runtime_rejects_query_token_fallback_when_auth_header_is_invalid(client, db_session):
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
    assert runtime_resp.status_code == 401


@pytest.mark.asyncio
async def test_preview_asset_html_keeps_relative_assets_tokenless(client, db_session, monkeypatch):
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
        f"/public/apps/preview/revisions/{draft_revision_id}/assets/index.html",
        headers={"Authorization": f"Bearer {preview_token}"},
    )
    assert resp.status_code == 200
    text = resp.text
    assert "./assets/main.css" in text
    assert "./assets/main.js" in text
    assert "preview_token=" not in text
    assert "window.__APP_RUNTIME_CONTEXT=" in text
    assert "\"mode\":\"builder-preview\"" in text



@pytest.mark.asyncio
async def test_preview_runtime_bootstrap_contract(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Preview Bootstrap App",
            "slug": "preview-bootstrap-app",
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

    bootstrap_resp = await client.get(
        f"/public/apps/preview/revisions/{draft_revision_id}/runtime/bootstrap",
        headers={"Authorization": f"Bearer {preview_token}"},
    )
    assert bootstrap_resp.status_code == 200
    payload = bootstrap_resp.json()
    assert payload["version"] == "runtime-bootstrap.v1"
    assert payload["mode"] == "builder-preview"
    assert payload["revision_id"] == draft_revision_id
    assert payload["request_contract_version"] == "thread.v1"
    assert "preview_token" not in payload
    assert payload["chat_stream_path"].endswith(f"/public/apps/preview/revisions/{draft_revision_id}/chat/stream")
