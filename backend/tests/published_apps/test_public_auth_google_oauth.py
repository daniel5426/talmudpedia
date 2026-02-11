from urllib.parse import parse_qs, urlparse

import pytest

from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.published_app_auth_service import PublishedAppAuthService
from ._helpers import seed_admin_tenant_and_agent, seed_published_app


@pytest.mark.asyncio
async def test_google_oauth_flow_callback_issues_token(client, db_session, monkeypatch):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="google-app",
        auth_enabled=True,
        auth_providers=["password", "google"],
    )

    credential = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.CUSTOM,
        provider_key="google_oauth",
        display_name="Google OAuth",
        credentials={
            "client_id": "test-google-client-id",
            "client_secret": "test-google-secret",
            "redirect_uri": f"http://test/public/apps/{app.slug}/auth/google/callback",
        },
        is_enabled=True,
    )
    db_session.add(credential)
    await db_session.commit()

    monkeypatch.setattr(
        PublishedAppAuthService,
        "exchange_google_code",
        lambda self, **_: {"id_token": "fake-google-id-token"},
    )
    monkeypatch.setattr(
        PublishedAppAuthService,
        "verify_google_id_token",
        lambda self, **_: {
            "email": "google-user@example.com",
            "sub": "google-sub-id",
            "name": "Google User",
            "picture": "https://example.com/avatar.png",
        },
    )

    start_resp = await client.get(
        f"/public/apps/{app.slug}/auth/google/start",
        params={"return_to": f"http://test/published/{app.slug}/auth/callback"},
        follow_redirects=False,
    )
    assert start_resp.status_code in {302, 307}
    assert "accounts.google.com" in start_resp.headers["location"]

    parsed_start = urlparse(start_resp.headers["location"])
    state = parse_qs(parsed_start.query)["state"][0]

    callback_resp = await client.get(
        f"/public/apps/{app.slug}/auth/google/callback",
        params={"code": "fake-auth-code", "state": state},
        follow_redirects=False,
    )
    assert callback_resp.status_code in {302, 307}
    assert "token=" in callback_resp.headers["location"]


@pytest.mark.asyncio
async def test_google_start_rejects_when_credentials_missing(client, db_session):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="google-no-creds",
        auth_enabled=True,
        auth_providers=["google"],
    )

    resp = await client.get(f"/public/apps/{app.slug}/auth/google/start")
    assert resp.status_code == 400
    assert "credentials" in resp.json()["detail"].lower()
