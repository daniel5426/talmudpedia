import pytest

from ._helpers import seed_admin_tenant_and_agent, seed_published_app


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
