import pytest
from sqlalchemy import select

from app.db.postgres.models.published_apps import PublishedAppExternalIdentity
from app.services.published_app_auth_service import PublishedAppAuthError
from ._helpers import seed_admin_tenant_and_agent, seed_published_app


@pytest.mark.asyncio
async def test_public_auth_exchange_mints_platform_session_token(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="oidc-exchange-app",
        auth_enabled=True,
        auth_providers=["password"],
    )
    app.external_auth_oidc = {
        "issuer": "https://issuer.example.com",
        "audience": "oidc-exchange-app",
        "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
        "email_claim": "email",
        "name_claim": "name",
    }
    await db_session.commit()

    def _verify(self, *, token: str, config: dict):
        _ = (self, token, config)
        return {
            "sub": "ext-user-1",
            "email": "ext-user-1@example.com",
            "name": "External User",
        }

    monkeypatch.setattr(
        "app.services.published_app_auth_service.PublishedAppAuthService.verify_external_oidc_token",
        _verify,
    )

    exchange_resp = await client.post(
        f"/public/apps/{app.slug}/auth/exchange",
        json={"token": "external-jwt"},
    )
    assert exchange_resp.status_code == 200
    payload = exchange_resp.json()
    assert payload["token"]
    assert payload["user"]["email"] == "ext-user-1@example.com"

    me_resp = await client.get(
        f"/public/apps/{app.slug}/auth/me",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "ext-user-1@example.com"

    identity = await db_session.scalar(
        select(PublishedAppExternalIdentity).where(PublishedAppExternalIdentity.published_app_id == app.id)
    )
    assert identity is not None
    assert identity.subject == "ext-user-1"
    assert identity.issuer == "https://issuer.example.com"


@pytest.mark.asyncio
async def test_public_auth_exchange_rejects_invalid_external_token(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="oidc-exchange-invalid-app",
        auth_enabled=True,
        auth_providers=["password"],
    )
    app.external_auth_oidc = {
        "issuer": "https://issuer.example.com",
        "audience": "oidc-exchange-invalid-app",
        "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
    }
    await db_session.commit()

    def _verify(self, *, token: str, config: dict):
        _ = (self, token, config)
        raise PublishedAppAuthError("Failed to verify external OIDC token: signature mismatch")

    monkeypatch.setattr(
        "app.services.published_app_auth_service.PublishedAppAuthService.verify_external_oidc_token",
        _verify,
    )

    resp = await client.post(
        f"/public/apps/{app.slug}/auth/exchange",
        json={"token": "bad-token"},
    )
    assert resp.status_code == 400
    assert "signature mismatch" in str(resp.json()["detail"])
