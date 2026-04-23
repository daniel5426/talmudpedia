import pytest
from sqlalchemy import select
from types import SimpleNamespace
from uuid import UUID

from app.db.postgres.models.published_apps import PublishedApp, PublishedAppCustomDomain
from ._helpers import admin_headers, install_app_create_stub, seed_admin_tenant_and_agent


def _host_headers(public_id: str) -> dict[str, str]:
    return {"Host": f"{public_id}.apps.localhost"}

@pytest.mark.asyncio
async def test_admin_apps_crud(client, db_session, monkeypatch):
    install_app_create_stub(monkeypatch)
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
            "template_key": "classic-chat",
            "visibility": "public",
            "auth_enabled": True,
            "auth_providers": ["password"],
            "auth_template_key": "auth-split",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["public_id"]
    assert created["description"] == "App description"
    assert created["logo_url"] == "https://cdn.example.com/logo.png"
    assert created["visibility"] == "public"
    assert created["auth_template_key"] == "auth-split"
    assert created["template_key"] == "classic-chat"
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
async def test_admin_app_create_returns_no_draft_until_first_real_build(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Init Build App",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    payload = state_resp.json()
    assert payload["current_draft_revision"] is None


@pytest.mark.asyncio
async def test_admin_app_ensure_session_bootstraps_live_workspace_without_inline_app_init_revision(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Init Build Fail App",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    async def _provision_workspace(self, *, app, user_id, files, entry_file, trace_source=None):
        _ = self, app, user_id, files, entry_file, trace_source
        return None

    async def _ensure_live_workspace_session(self, *, app, user_id, trace_source=None):
        _ = self, app, trace_source
        return type(
            "Session",
            (),
            {
                "id": UUID("00000000-0000-0000-0000-000000000001"),
                "published_app_id": app.id,
                "user_id": user_id,
                "revision_id": None,
                "status": "serving",
                "preview_url": "/preview/session-1",
                "last_error": None,
                "active_coding_run_count": 0,
                "preview_transport_generation": 1,
                "workspace_revision_token": None,
                "live_preview": None,
                "live_workspace_snapshot": None,
                "backend_metadata": {},
                "draft_workspace_id": None,
                "sandbox_id": None,
                "runtime_generation": 1,
            },
        )()

    async def _decorate(*, db, request, session, app, actor_id, revision_id):
        _ = db, request, actor_id
        return {
            "session_id": str(session.id),
            "app_id": str(app.id),
            "revision_id": str(revision_id) if revision_id else None,
            "status": "serving",
            "runtime_backend": "sprite",
            "has_active_coding_runs": False,
            "active_coding_run_count": 0,
            "preview_url": session.preview_url,
            "last_error": None,
            "preview_transport_generation": 1,
            "workspace_revision_token": None,
            "live_preview": None,
            "live_workspace_snapshot": None,
        }

    scheduled: list[object] = []

    def _fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        "app.api.routers.published_apps_admin_routes_builder.PublishedAppDraftDevRuntimeService.provision_workspace_from_files",
        _provision_workspace,
    )
    monkeypatch.setattr(
        "app.api.routers.published_apps_admin_routes_builder.PublishedAppDraftDevRuntimeService.ensure_live_workspace_session",
        _ensure_live_workspace_session,
    )
    monkeypatch.setattr(
        "app.api.routers.published_apps_admin_routes_builder._decorate_draft_dev_session_response",
        _decorate,
    )
    monkeypatch.setattr(
        "app.api.routers.published_apps_admin_routes_builder.asyncio.create_task",
        _fake_create_task,
    )

    ensure_resp = await client.post(
        f"/admin/apps/{app_id}/builder/draft-dev/session/ensure",
        headers=headers,
        json={},
    )
    assert ensure_resp.status_code == 200
    assert ensure_resp.json()["revision_id"] is None
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None
    assert app.current_draft_revision_id is None
    assert scheduled


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
async def test_admin_users_list_block_unblock_and_revoke_session(client, db_session, monkeypatch):
    install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Users App",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app = create_resp.json()
    publish_toggle_resp = await client.patch(
        f"/admin/apps/{app['id']}",
        headers=headers,
        json={
            "status": "published",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert publish_toggle_resp.status_code == 200

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app["public_id"]),
        json={
            "email": "member@example.com",
            "password": "secret123",
            "full_name": "Member User",
        },
    )
    assert signup_resp.status_code == 200

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

    state_resp = await client.get(
        "/_talmudpedia/auth/state",
        headers=_host_headers(app["public_id"]),
    )
    assert state_resp.status_code == 200
    assert state_resp.json()["authenticated"] is False

    unblock_resp = await client.patch(
        f"/admin/apps/{app['id']}/users/{user_id}",
        headers=headers,
        json={"membership_status": "active"},
    )
    assert unblock_resp.status_code == 200
    assert unblock_resp.json()["membership_status"] == "active"


@pytest.mark.asyncio
async def test_admin_custom_domains_crud(client, db_session, monkeypatch):
    install_app_create_stub(monkeypatch)
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Domains App",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
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
