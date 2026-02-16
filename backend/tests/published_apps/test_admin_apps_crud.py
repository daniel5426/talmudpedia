import pytest
from sqlalchemy import select
from uuid import UUID

from app.db.postgres.models.published_apps import PublishedAppCustomDomain
from ._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_admin_apps_crud(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Support App",
            "description": "App description",
            "logo_url": "https://cdn.example.com/logo.png",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "visibility": "public",
            "auth_enabled": True,
            "auth_providers": ["password"],
            "auth_template_key": "auth-split",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["slug"] == "support-app"
    assert created["description"] == "App description"
    assert created["logo_url"] == "https://cdn.example.com/logo.png"
    assert created["visibility"] == "public"
    assert created["auth_template_key"] == "auth-split"
    assert created["template_key"] == "chat-classic"
    app_id = created["id"]

    list_resp = await client.get("/admin/apps", headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == app_id for item in list_resp.json())

    patch_resp = await client.patch(
        f"/admin/apps/{app_id}",
        headers=headers,
        json={
            "name": "Support App v2",
            "description": "Updated description",
            "logo_url": "https://cdn.example.com/logo-v2.png",
            "visibility": "private",
            "auth_enabled": False,
            "auth_providers": ["password", "google"],
            "auth_template_key": "auth-minimal",
        },
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == "Support App v2"
    assert updated["description"] == "Updated description"
    assert updated["logo_url"] == "https://cdn.example.com/logo-v2.png"
    assert updated["visibility"] == "private"
    assert updated["auth_enabled"] is False
    assert "google" in updated["auth_providers"]
    assert updated["auth_template_key"] == "auth-minimal"

    get_resp = await client.get(f"/admin/apps/{app_id}", headers=headers)
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert payload["id"] == app_id
    assert payload["visibility"] == "private"
    assert payload["auth_template_key"] == "auth-minimal"

    delete_resp = await client.delete(f"/admin/apps/{app_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_admin_lists_auth_templates(client, db_session):
    tenant, user, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    resp = await client.get("/admin/apps/auth/templates", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    assert any(item["key"] == "auth-classic" for item in payload)


@pytest.mark.asyncio
async def test_admin_users_list_block_unblock_and_revoke_session(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Users App",
            "slug": "users-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app = create_resp.json()
    publish_toggle_resp = await client.patch(
        f"/admin/apps/{app['id']}",
        headers=headers,
        json={"status": "published"},
    )
    assert publish_toggle_resp.status_code == 200

    signup_resp = await client.post(
        f"/public/apps/{app['slug']}/auth/signup",
        json={
            "email": "member@example.com",
            "password": "secret123",
            "full_name": "Member User",
        },
    )
    assert signup_resp.status_code == 200
    session_token = signup_resp.json()["token"]

    users_resp = await client.get(f"/admin/apps/{app['id']}/users", headers=headers)
    assert users_resp.status_code == 200
    users = users_resp.json()
    assert len(users) == 1
    assert users[0]["membership_status"] == "active"
    assert users[0]["active_sessions"] >= 1
    user_id = users[0]["user_id"]

    block_resp = await client.patch(
        f"/admin/apps/{app['id']}/users/{user_id}",
        headers=headers,
        json={"membership_status": "blocked"},
    )
    assert block_resp.status_code == 200
    blocked = block_resp.json()
    assert blocked["membership_status"] == "blocked"
    assert blocked["active_sessions"] == 0

    me_resp = await client.get(
        f"/public/apps/{app['slug']}/auth/me",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert me_resp.status_code == 401

    unblock_resp = await client.patch(
        f"/admin/apps/{app['id']}/users/{user_id}",
        headers=headers,
        json={"membership_status": "active"},
    )
    assert unblock_resp.status_code == 200
    assert unblock_resp.json()["membership_status"] == "active"


@pytest.mark.asyncio
async def test_admin_custom_domains_crud(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Domains App",
            "slug": "domains-app",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app = create_resp.json()

    list_empty_resp = await client.get(f"/admin/apps/{app['id']}/domains", headers=headers)
    assert list_empty_resp.status_code == 200
    assert list_empty_resp.json() == []

    create_domain_resp = await client.post(
        f"/admin/apps/{app['id']}/domains",
        headers=headers,
        json={"host": "APP.Example.COM", "notes": "My domain"},
    )
    assert create_domain_resp.status_code == 200
    created_domain = create_domain_resp.json()
    assert created_domain["host"] == "app.example.com"
    assert created_domain["status"] == "pending"
    assert created_domain["notes"] == "My domain"

    list_resp = await client.get(f"/admin/apps/{app['id']}/domains", headers=headers)
    assert list_resp.status_code == 200
    domains = list_resp.json()
    assert len(domains) == 1
    assert domains[0]["id"] == created_domain["id"]

    domain_row = await db_session.scalar(
        select(PublishedAppCustomDomain).where(PublishedAppCustomDomain.id == UUID(created_domain["id"]))
    )
    assert domain_row is not None

    delete_resp = await client.delete(
        f"/admin/apps/{app['id']}/domains/{created_domain['id']}",
        headers=headers,
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deleted"
