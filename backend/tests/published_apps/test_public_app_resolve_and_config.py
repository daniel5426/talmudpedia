import pytest
from sqlalchemy import select
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from ._helpers import admin_headers, seed_admin_tenant_and_agent, seed_published_app
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision, PublishedAppRevisionBuildStatus


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
    )

    resolve_resp = await client.get("/public/apps/resolve?host=resolver-app.apps.localhost")
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["app"]["slug"] == "resolver-app"

    config_resp = await client.get(f"/public/apps/{app.slug}/config")
    assert config_resp.status_code == 200
    payload = config_resp.json()
    assert payload["id"] == str(app.id)
    assert payload["auth_enabled"] is True
    assert "google" in payload["auth_providers"]


@pytest.mark.asyncio
async def test_public_resolve_rejects_unknown_host(client):
    resp = await client.get("/public/apps/resolve?host=example.com")
    assert resp.status_code == 404


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

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    draft_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert draft_row is not None
    draft_row.build_status = PublishedAppRevisionBuildStatus.succeeded
    draft_row.build_error = None
    await db_session.commit()

    publish_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_resp.status_code == 200
    app_payload = publish_resp.json()
    assert app_payload["current_published_revision_id"]

    runtime_resp = await client.get("/public/apps/runtime-descriptor-app/runtime")
    assert runtime_resp.status_code == 200
    runtime_payload = runtime_resp.json()
    assert runtime_payload["slug"] == "runtime-descriptor-app"
    assert runtime_payload["runtime_mode"] == "vite_static"
    assert runtime_payload["api_base_path"] == "/api/py"
    assert runtime_payload["revision_id"] == app_payload["current_published_revision_id"]

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
