import pytest
from sqlalchemy import select
from uuid import UUID
from types import SimpleNamespace

from app.db.postgres.models.published_apps import PublishedAppCustomDomain
from app.db.postgres.models.published_apps import PublishedAppRevision, PublishedAppRevisionBuildStatus, PublishedAppRevisionKind
from app.services.published_app_templates import build_template_files, get_template
from app.services.published_app_versioning import create_app_version
from ._helpers import admin_headers, seed_admin_tenant_and_agent


def _host_headers(slug: str) -> dict[str, str]:
    return {"Host": f"{slug}.apps.localhost"}


def _install_app_create_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _provision_workspace_from_files(self, *, app, user_id, files, entry_file, trace_source=None):
        _ = self, app, user_id, files, entry_file, trace_source
        return None

    async def _materialize_live_workspace(self, *, app, entry_file, source_revision_id, created_by, origin_kind, **kwargs):
        _ = kwargs
        template = get_template(app.template_key)
        files = build_template_files(
            app.template_key,
            runtime_context={
                "app_id": str(app.id),
                "app_slug": app.slug,
                "agent_id": str(app.agent_id),
            },
        )
        revision = await create_app_version(
            self.db,
            app=app,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=entry_file or template.entry_file,
            files=files,
            created_by=created_by,
            source_revision_id=source_revision_id,
            origin_kind=origin_kind,
            build_status=PublishedAppRevisionBuildStatus.succeeded,
            build_seq=1,
            dist_storage_prefix=f"apps/{app.id}/revisions/init/dist",
            dist_manifest={"entry_html": "index.html", "assets": [], "source_fingerprint": f"fp-{app.id}"},
            template_runtime="vite_static",
        )
        app.current_draft_revision_id = revision.id
        return SimpleNamespace(
            revision=revision,
            reused=False,
            source_fingerprint=f"fp-{app.id}",
            workspace_revision_token=None,
        )

    monkeypatch.setattr(
        "app.services.published_app_draft_dev_runtime.PublishedAppDraftDevRuntimeService.provision_workspace_from_files",
        _provision_workspace_from_files,
    )
    monkeypatch.setattr(
        "app.services.published_app_draft_revision_materializer.PublishedAppDraftRevisionMaterializerService.materialize_live_workspace",
        _materialize_live_workspace,
    )


@pytest.mark.asyncio
async def test_admin_apps_crud(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
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
    assert created["slug"] == "support-app"
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
async def test_admin_app_create_materializes_first_draft_revision(client, db_session, monkeypatch):
    _install_app_create_stub(monkeypatch)
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
    revision_id = state_resp.json()["current_draft_revision"]["id"]
    revision = await db_session.get(PublishedAppRevision, UUID(revision_id))
    assert revision is not None
    assert revision.build_status == PublishedAppRevisionBuildStatus.succeeded
    assert revision.workspace_build_id is None or isinstance(revision.workspace_build_id, UUID)
    assert revision.dist_storage_prefix
    assert revision.dist_manifest


@pytest.mark.asyncio
async def test_admin_app_create_fails_when_initial_materialization_fails(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    async def _provision_workspace_from_files(self, *, app, user_id, files, entry_file, trace_source=None):
        _ = self, app, user_id, files, entry_file, trace_source
        return None

    monkeypatch.setattr(
        "app.services.published_app_draft_dev_runtime.PublishedAppDraftDevRuntimeService.provision_workspace_from_files",
        _provision_workspace_from_files,
    )

    async def _materialize_fail(self, *, app, **kwargs):
        _ = self, app, kwargs
        from app.services.published_app_draft_revision_materializer import PublishedAppDraftRevisionMaterializerError

        raise PublishedAppDraftRevisionMaterializerError("watcher never became ready")

    monkeypatch.setattr(
        "app.services.published_app_draft_revision_materializer.PublishedAppDraftRevisionMaterializerService.materialize_live_workspace",
        _materialize_fail,
    )

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
    assert create_resp.status_code == 409
    detail = create_resp.json()["detail"]
    assert detail["code"] == "APP_INIT_MATERIALIZATION_FAILED"
    assert "watcher never became ready" in detail["reason"]


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
        json={"status": "published"},
    )
    assert publish_toggle_resp.status_code == 200

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app["slug"]),
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
        headers=_host_headers(app["slug"]),
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
