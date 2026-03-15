from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, User
from app.db.postgres.models.published_apps import PublishedAppDraftDevSession, PublishedAppDraftWorkspace
from app.services import published_app_draft_dev_runtime as runtime_module
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _noop_scope_lock(self, *, app_id, user_id):
    _ = self, app_id, user_id
    return None


async def _create_builder_app(client, headers: dict[str, str], agent_id: str, *, name: str) -> str:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": name,
            "agent_id": agent_id,
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    return str(create_resp.json()["id"])


async def _seed_second_owner(db_session, *, tenant_id, org_unit_id) -> User:
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        OrgMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            org_unit_id=org_unit_id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    await db_session.commit()
    await db_session.refresh(user)
    return user


class _FakeSpriteRuntimeClient:
    backend_name = "sprite"
    is_remote_enabled = True

    def __init__(self):
        self.start_calls: list[dict[str, object]] = []
        self.sync_calls: list[dict[str, object]] = []
        self.stop_calls: list[str] = []
        self.reconciled: list[dict[str, object]] = []
        self.swept_payloads: list[dict[str, object]] = []
        self.deleted = False

    @staticmethod
    def _sandbox_id(app_id: str) -> str:
        return f"sprite-{str(app_id).replace('-', '')[:12]}"

    def expected_sandbox_id_for_app(self, *, app_id: str) -> str | None:
        return self._sandbox_id(app_id)

    def build_preview_proxy_path(self, session_id: str) -> str:
        return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/"

    def _metadata(self, *, sandbox_id: str, preview_base_path: str) -> dict[str, object]:
        return {
            "preview": {
                "upstream_base_url": f"https://{sandbox_id}.sprites.app",
                "base_path": preview_base_path,
                "upstream_path": "/",
                "auth_header_name": "Authorization",
                "auth_token_env": "APPS_SPRITE_API_TOKEN",
                "auth_token_prefix": "Bearer ",
            },
            "workspace": {
                "sprite_name": sandbox_id,
                "live_workspace_path": "/home/sprite/app",
                "stage_workspace_path": "/home/sprite/.talmudpedia/stage/current/workspace",
                "publish_workspace_path": "/home/sprite/.talmudpedia/publish/current/workspace",
            },
            "services": {
                "preview_service_name": "builder-preview",
                "opencode_service_name": "opencode",
            },
        }

    async def start_session(self, **kwargs):
        self.start_calls.append(dict(kwargs))
        sandbox_id = self._sandbox_id(str(kwargs["app_id"]))
        self.deleted = False
        return {
            "sandbox_id": sandbox_id,
            "status": "serving",
            "runtime_backend": "sprite",
            "runtime_generation": kwargs["runtime_generation"],
            "live_workspace_path": "/home/sprite/app",
            "stage_workspace_path": "/home/sprite/.talmudpedia/stage/current/workspace",
            "publish_workspace_path": "/home/sprite/.talmudpedia/publish/current/workspace",
            "preview_service_name": "builder-preview",
            "opencode_service_name": "opencode",
            "backend_metadata": self._metadata(
                sandbox_id=sandbox_id,
                preview_base_path=str(kwargs["preview_base_path"]),
            ),
        }

    async def sync_session(self, **kwargs):
        self.sync_calls.append(dict(kwargs))
        self.deleted = False
        sandbox_id = str(kwargs["sandbox_id"])
        return {
            "sandbox_id": sandbox_id,
            "status": "serving",
            "runtime_backend": "sprite",
            "backend_metadata": self._metadata(
                sandbox_id=sandbox_id,
                preview_base_path=str(kwargs.get("preview_base_path") or "/"),
            ),
        }

    async def heartbeat_session(self, **kwargs):
        if self.deleted:
            raise PublishedAppDraftDevRuntimeClientError(
                f"Sprite request failed (404) for /v1/sprites/{kwargs['sandbox_id']}: not found"
            )
        sandbox_id = str(kwargs["sandbox_id"])
        return {
            "sandbox_id": sandbox_id,
            "status": "serving",
            "runtime_backend": "sprite",
            "backend_metadata": self._metadata(
                sandbox_id=sandbox_id,
                preview_base_path="/public/apps-builder/draft-dev/sessions/heartbeat/preview/",
            ),
        }

    async def stop_session(self, **kwargs):
        self.stop_calls.append(str(kwargs["sandbox_id"]))
        return {
            "status": "stopped",
            "sandbox_id": kwargs["sandbox_id"],
            "runtime_backend": "sprite",
        }

    async def reconcile_session_scope(self, **kwargs):
        self.reconciled.append(dict(kwargs))
        return {"removed_sandbox_ids": []}

    async def sweep_remote_sessions(self, **kwargs):
        self.swept_payloads.append(dict(kwargs))
        return {"checked": 0, "removed_sandbox_ids": []}


@pytest.mark.asyncio
async def test_shared_workspace_is_reused_across_users(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user_a, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    user_b = await _seed_second_owner(db_session, tenant_id=tenant.id, org_unit_id=org_unit.id)
    headers_a = admin_headers(str(user_a.id), str(tenant.id), str(org_unit.id))
    headers_b = admin_headers(str(user_b.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers_a, str(agent.id), name="Shared Sprite App")

    first_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_a)
    second_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_b)

    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    first_payload = first_resp.json()
    second_payload = second_resp.json()
    assert first_payload["status"] == "serving"
    assert second_payload["status"] == "serving"
    assert first_payload["runtime_backend"] == "sprite"
    assert second_payload["runtime_backend"] == "sprite"

    first_session = await db_session.get(PublishedAppDraftDevSession, UUID(first_payload["session_id"]))
    second_session = await db_session.get(PublishedAppDraftDevSession, UUID(second_payload["session_id"]))
    assert first_session is not None
    assert second_session is not None
    assert first_session.draft_workspace_id == second_session.draft_workspace_id
    assert first_session.sandbox_id == second_session.sandbox_id
    assert len(fake_client.start_calls) == 1
    assert len(fake_client.sync_calls) == 1

    workspace = await db_session.scalar(
        select(PublishedAppDraftWorkspace).where(PublishedAppDraftWorkspace.published_app_id == UUID(app_id))
    )
    assert workspace is not None
    assert workspace.sandbox_id == first_session.sandbox_id


@pytest.mark.asyncio
async def test_heartbeat_refreshes_workspace_preview_metadata(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Heartbeat Refresh App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200
    session_id = UUID(str(ensure_resp.json()["session_id"]))
    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    workspace.backend_metadata = {
        "preview": {
            "upstream_base_url": "https://stale-sprite-host.example",
            "base_path": "/public/apps-builder/draft-dev/sessions/stale/preview/",
            "upstream_path": "/",
        }
    }
    await db_session.commit()

    heartbeat_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/heartbeat", headers=headers)
    assert heartbeat_resp.status_code == 200

    await db_session.refresh(workspace)
    await db_session.refresh(session)
    assert workspace.backend_metadata["preview"]["upstream_base_url"].startswith("https://sprite-")
    assert session.backend_metadata["preview"]["upstream_base_url"] == workspace.backend_metadata["preview"]["upstream_base_url"]
    assert workspace.backend_metadata["preview"]["base_path"] == str(session.preview_url)


@pytest.mark.asyncio
async def test_heartbeat_preserves_existing_preview_base_path_when_refresh_returns_root(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    async def _heartbeat_root_base_path(**kwargs):
        sandbox_id = str(kwargs["sandbox_id"])
        return {
            "sandbox_id": sandbox_id,
            "status": "serving",
            "runtime_backend": "sprite",
            "backend_metadata": {
                "preview": {
                    "upstream_base_url": f"https://{sandbox_id}.sprites.app",
                    "base_path": "/",
                    "upstream_path": "/",
                },
                "workspace": {
                    "sprite_name": sandbox_id,
                },
                "services": {
                    "preview_port": 8080,
                },
            },
        }

    fake_client.heartbeat_session = _heartbeat_root_base_path

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Heartbeat Base Path Preserve App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200
    payload = ensure_resp.json()
    session_id = UUID(str(payload["session_id"]))
    expected_base_path = urlparse(str(payload["preview_url"])).path

    heartbeat_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/heartbeat", headers=headers)
    assert heartbeat_resp.status_code == 200

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert workspace.backend_metadata["preview"]["base_path"] == expected_base_path
    assert session.backend_metadata["preview"]["base_path"] == expected_base_path


@pytest.mark.asyncio
async def test_stop_detaches_sessions_and_sweeper_destroys_dormant_workspace(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user_a, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    user_b = await _seed_second_owner(db_session, tenant_id=tenant.id, org_unit_id=org_unit.id)
    headers_a = admin_headers(str(user_a.id), str(tenant.id), str(org_unit.id))
    headers_b = admin_headers(str(user_b.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers_a, str(agent.id), name="Dormant Sprite App")

    first_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_a)
    second_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_b)
    assert first_resp.status_code == 200
    assert second_resp.status_code == 200

    first_stop = await client.delete(f"/admin/apps/{app_id}/builder/draft-dev/session", headers=headers_a)
    assert first_stop.status_code == 200
    assert first_stop.json()["status"] == "stopped"
    assert fake_client.stop_calls == []

    workspace = await db_session.scalar(
        select(PublishedAppDraftWorkspace).where(PublishedAppDraftWorkspace.published_app_id == UUID(app_id))
    )
    assert workspace is not None
    assert workspace.detached_at is None

    second_stop = await client.delete(f"/admin/apps/{app_id}/builder/draft-dev/session", headers=headers_b)
    assert second_stop.status_code == 200
    assert second_stop.json()["status"] == "stopped"
    assert fake_client.stop_calls == []

    workspace = await db_session.scalar(
        select(PublishedAppDraftWorkspace).where(PublishedAppDraftWorkspace.published_app_id == UUID(app_id))
    )
    assert workspace is not None
    assert workspace.detached_at is not None
    expected_sandbox_id = str(workspace.sandbox_id)
    workspace.detached_at = datetime.now(timezone.utc) - timedelta(seconds=999999)
    await db_session.commit()

    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    removed = await runtime_service.sweep_dormant_workspaces(app_id=UUID(app_id))

    assert removed == 1
    assert fake_client.stop_calls == [expected_sandbox_id]


@pytest.mark.asyncio
async def test_deleted_sprite_is_resynced_on_next_ensure(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Restart Sprite App")

    first_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    assert first_payload["status"] == "serving"

    fake_client.deleted = True
    second_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["status"] == "serving"

    session_row = await db_session.get(PublishedAppDraftDevSession, UUID(second_payload["session_id"]))
    assert session_row is not None
    assert session_row.sandbox_id == fake_client.expected_sandbox_id_for_app(app_id=app_id)
    assert len(fake_client.start_calls) == 1
    assert len(fake_client.sync_calls) == 1


@pytest.mark.asyncio
async def test_app_delete_destroys_shared_workspace(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Delete Sprite App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200

    delete_resp = await client.delete(f"/admin/apps/{app_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert fake_client.stop_calls

    workspace = await db_session.scalar(
        select(PublishedAppDraftWorkspace).where(PublishedAppDraftWorkspace.published_app_id == UUID(app_id))
    )
    assert workspace is None
