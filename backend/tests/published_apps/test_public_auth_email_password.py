import pytest
from sqlalchemy import func, select

from app.db.postgres.models.published_apps import PublishedAppUserMembership
from ._helpers import seed_admin_tenant_and_agent, seed_published_app


@pytest.mark.asyncio
async def test_public_signup_login_and_me(client, db_session):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="auth-email-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        f"/public/apps/{app.slug}/auth/signup",
        json={
            "email": "end-user@example.com",
            "password": "secret123",
            "full_name": "End User",
        },
    )
    assert signup_resp.status_code == 200
    token = signup_resp.json()["token"]
    assert token

    me_resp = await client.get(
        f"/public/apps/{app.slug}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "end-user@example.com"

    membership_count = await db_session.scalar(
        select(func.count(PublishedAppUserMembership.id)).where(
            PublishedAppUserMembership.published_app_id == app.id
        )
    )
    assert membership_count == 1

    logout_resp = await client.post(
        f"/public/apps/{app.slug}/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200

    login_resp = await client.post(
        f"/public/apps/{app.slug}/auth/login",
        json={"email": "end-user@example.com", "password": "secret123"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["token"]


@pytest.mark.asyncio
async def test_public_signup_rejects_short_password(client, db_session):
    tenant, user, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        user.id,
        slug="password-policy-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    resp = await client.post(
        f"/public/apps/{app.slug}/auth/signup",
        json={"email": "short@example.com", "password": "123"},
    )
    assert resp.status_code == 400
    assert "at least 6" in resp.json()["detail"]
