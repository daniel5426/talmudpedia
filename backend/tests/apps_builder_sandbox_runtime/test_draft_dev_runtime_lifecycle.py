from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.api.routers import published_apps_admin_routes_builder as builder_routes_module
from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, User
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftWorkspace,
    PublishedAppRevision,
    PublishedAppRevisionKind,
)
from app.services import published_app_draft_dev_runtime as runtime_module
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError
from app.services.published_app_versioning import create_app_version
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
async def test_prefer_live_workspace_reuses_healthy_session_across_revision_mismatch(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Prefer Live Workspace App")
    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None
    first_revision = await db_session.get(PublishedAppRevision, app.current_draft_revision_id)
    assert first_revision is not None
    next_revision = await create_app_version(
        db_session,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=first_revision.entry_file,
        files=dict(first_revision.files or {}),
        created_by=user.id,
        source_revision_id=first_revision.id,
        origin_kind="test",
    )
    app.current_draft_revision_id = next_revision.id
    await db_session.commit()

    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    reused = await runtime_service.ensure_active_session(
        app=app,
        revision=next_revision,
        user_id=user.id,
        prefer_live_workspace=True,
    )

    await db_session.refresh(reused)
    assert reused.revision_id == first_revision.id
    assert len(fake_client.start_calls) == 1
    assert len(fake_client.sync_calls) == 0


@pytest.mark.asyncio
async def test_touch_session_activity_renews_expiry_without_detaching_workspace(
    monkeypatch: pytest.MonkeyPatch,
):
    db = AsyncMock()
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    previous_activity = datetime.now(timezone.utc) - timedelta(seconds=120)
    previous_expiry = previous_activity + timedelta(seconds=30)
    workspace = SimpleNamespace(last_activity_at=None, detached_at=datetime.now(timezone.utc))
    db.get.return_value = workspace
    session = SimpleNamespace(
        id=uuid4(),
        draft_workspace_id=uuid4(),
        last_activity_at=previous_activity,
        expires_at=previous_expiry,
    )
    changed = await runtime_service.touch_session_activity(session=session, throttle_seconds=0)
    assert changed is True
    assert session.draft_workspace_id is not None
    assert session.expires_at is not None
    assert session.expires_at >= previous_expiry
    assert workspace.last_activity_at == session.last_activity_at
    assert workspace.detached_at is None


@pytest.mark.asyncio
async def test_ensure_endpoint_reuses_live_session_without_calling_legacy_ensure_session(
    monkeypatch: pytest.MonkeyPatch,
):
    tenant_id = uuid4()
    user_id = uuid4()
    app_id = uuid4()
    revision_id = uuid4()
    session_id = uuid4()
    ctx = {"tenant_id": tenant_id, "user": SimpleNamespace(id=user_id)}
    app = SimpleNamespace(id=app_id, tenant_id=tenant_id)
    revision = SimpleNamespace(id=revision_id)
    session = SimpleNamespace(id=session_id)
    db = AsyncMock()
    request = SimpleNamespace()
    ensure_active_calls: list[dict[str, object]] = []

    async def _fake_ensure_active_session(
        self,
        *,
        app,
        revision,
        user_id,
        prefer_live_workspace=False,
        trace_source=None,
    ):
        ensure_active_calls.append(
            {
                "app_id": app.id,
                "revision_id": revision.id,
                "user_id": user_id,
                "prefer_live_workspace": prefer_live_workspace,
                "trace_source": trace_source,
            }
        )
        return session

    async def _unexpected_ensure_session(*args, **kwargs):
        raise AssertionError("legacy ensure_session should not be called by the ensure route")

    monkeypatch.setattr(builder_routes_module, "_resolve_tenant_admin_context", AsyncMock(return_value=ctx))
    monkeypatch.setattr(builder_routes_module, "_assert_can_manage_apps", lambda resolved_ctx: None)
    monkeypatch.setattr(builder_routes_module, "_assert_no_active_coding_run_for_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(builder_routes_module, "_get_app_for_tenant", AsyncMock(return_value=app))
    monkeypatch.setattr(builder_routes_module, "_ensure_current_draft_revision", AsyncMock(return_value=revision))
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeService,
        "ensure_active_session",
        _fake_ensure_active_session,
    )
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeService,
        "ensure_session",
        _unexpected_ensure_session,
    )
    monkeypatch.setattr(
        builder_routes_module,
        "_decorate_draft_dev_session_response",
        AsyncMock(return_value={"session_id": str(session_id)}),
    )

    result = await builder_routes_module.ensure_builder_draft_dev_session(
        app_id=app_id,
        request=request,
        _={},
        principal={},
        db=db,
    )

    assert result == {"session_id": str(session_id)}
    assert ensure_active_calls == [
        {
            "app_id": app_id,
            "revision_id": revision_id,
            "user_id": user_id,
            "prefer_live_workspace": True,
            "trace_source": "builder.ensure_route",
        }
    ]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_route_ignores_delete_error_when_file_is_already_absent(
    monkeypatch: pytest.MonkeyPatch,
):
    tenant_id = uuid4()
    user_id = uuid4()
    app_id = uuid4()
    revision_id = uuid4()
    session_id = uuid4()
    sandbox_id = "sprite-sandbox-1"
    ctx = {"tenant_id": tenant_id, "user": SimpleNamespace(id=user_id)}
    app = SimpleNamespace(id=app_id, tenant_id=tenant_id)
    revision = SimpleNamespace(id=revision_id, files={"src/App.tsx": "app"}, entry_file="src/App.tsx")
    session = SimpleNamespace(
        id=session_id,
        sandbox_id=sandbox_id,
        revision_id=revision_id,
        backend_metadata={
            "live_workspace_snapshot": {
                "entry_file": "src/App.tsx",
                "files": {
                    "src/App.tsx": "app",
                    "src/deleted.tsx": "stale",
                },
            }
        },
    )
    db = AsyncMock()
    request = SimpleNamespace()
    fake_client = SimpleNamespace(
        delete_file=AsyncMock(side_effect=PublishedAppDraftDevRuntimeClientError("Sprite request failed: ")),
        snapshot_files=AsyncMock(return_value={"files": {"src/App.tsx": "app"}, "revision_token": "snap-1"}),
    )
    fake_runtime_service = SimpleNamespace(
        client=fake_client,
        record_workspace_live_snapshot=AsyncMock(return_value=None),
        record_live_workspace_revision_token=AsyncMock(return_value=session),
    )

    monkeypatch.setattr(builder_routes_module, "_resolve_tenant_admin_context", AsyncMock(return_value=ctx))
    monkeypatch.setattr(builder_routes_module, "_assert_can_manage_apps", lambda resolved_ctx: None)
    monkeypatch.setattr(builder_routes_module, "_assert_no_active_coding_run_for_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(builder_routes_module, "_get_app_for_tenant", AsyncMock(return_value=app))
    monkeypatch.setattr(builder_routes_module, "_ensure_current_draft_revision", AsyncMock(return_value=revision))
    monkeypatch.setattr(builder_routes_module, "_get_draft_dev_session_for_scope", AsyncMock(return_value=session))
    monkeypatch.setattr(builder_routes_module, "PublishedAppDraftDevRuntimeService", lambda db: fake_runtime_service)
    monkeypatch.setattr(
        builder_routes_module,
        "_decorate_draft_dev_session_response",
        AsyncMock(return_value={"session_id": str(session_id)}),
    )

    result = await builder_routes_module.sync_builder_draft_dev_session(
        app_id=app_id,
        payload=builder_routes_module.DraftDevSyncRequest(
            operations=[{"op": "delete_file", "path": "src/deleted.tsx"}],
        ),
        request=request,
        _={},
        principal={},
        db=db,
    )

    assert result == {"session_id": str(session_id)}
    fake_client.delete_file.assert_awaited_once_with(
        sandbox_id=sandbox_id,
        path="src/deleted.tsx",
    )
    fake_client.snapshot_files.assert_awaited_once_with(sandbox_id=sandbox_id)
    fake_runtime_service.record_workspace_live_snapshot.assert_awaited_once()
    fake_runtime_service.record_live_workspace_revision_token.assert_awaited_once()
    db.commit.assert_awaited_once()


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
async def test_heartbeat_preserves_live_workspace_snapshot_metadata(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Heartbeat Snapshot Preserve App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200
    payload = ensure_resp.json()
    session_id = UUID(str(payload["session_id"]))

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    await runtime_service.record_workspace_live_snapshot(
        app_id=app.id,
        revision_id=app.current_draft_revision_id,
        entry_file="src/App.tsx",
        files={"src/App.tsx": "export default function App() { return <div>hi</div>; }"},
        revision_token="snapshot-token",
        workspace_fingerprint="fingerprint-1",
    )
    await db_session.commit()

    heartbeat_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/heartbeat", headers=headers)
    assert heartbeat_resp.status_code == 200

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert session.backend_metadata["live_workspace_snapshot"]["entry_file"] == "src/App.tsx"
    assert session.backend_metadata["live_workspace_snapshot"]["files"]["src/App.tsx"].startswith("export default")
    assert workspace.backend_metadata["live_workspace_snapshot"]["revision_token"] == "snapshot-token"


@pytest.mark.asyncio
async def test_heartbeat_restores_missing_live_workspace_snapshot_from_runtime(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    async def _snapshot_files(**kwargs):
        _ = kwargs
        return {
            "files": {
                "src/App.tsx": "export default function App() { return <div>restored</div>; }",
                "index.html": "<html></html>",
            },
            "revision_token": "restored-token",
        }

    fake_client.snapshot_files = _snapshot_files

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Heartbeat Snapshot Restore App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200
    payload = ensure_resp.json()
    session_id = UUID(str(payload["session_id"]))

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    session.backend_metadata = {
        key: value for key, value in dict(session.backend_metadata or {}).items() if key != "live_workspace_snapshot"
    }
    workspace.backend_metadata = {
        key: value for key, value in dict(workspace.backend_metadata or {}).items() if key != "live_workspace_snapshot"
    }
    await db_session.commit()

    heartbeat_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/heartbeat", headers=headers)
    assert heartbeat_resp.status_code == 200
    heartbeat_payload = heartbeat_resp.json()
    assert heartbeat_payload["live_workspace_snapshot"]["files"]["src/App.tsx"].endswith("restored</div>; }")

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert session.backend_metadata["live_workspace_snapshot"]["revision_token"] == "restored-token"
    assert workspace.backend_metadata["live_workspace_snapshot"]["files"]["src/App.tsx"].endswith("restored</div>; }")


@pytest.mark.asyncio
async def test_heartbeat_restores_live_snapshot_with_shared_builder_file_policy(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    async def _snapshot_files(**kwargs):
        _ = kwargs
        return {
            "files": {
                "src/App.tsx": "export default function App() { return <div>restored</div>; }",
                "README": "no extension should be dropped",
                "node_modules/pkg/index.js": "ignored artifact",
                "src/routes.tsx": "export const routes = ['/chat'];",
            },
            "revision_token": "restored-token-2",
        }

    fake_client.snapshot_files = _snapshot_files

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Heartbeat Snapshot Policy App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200
    session_id = UUID(str(ensure_resp.json()["session_id"]))

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    session.backend_metadata = {
        key: value for key, value in dict(session.backend_metadata or {}).items() if key != "live_workspace_snapshot"
    }
    workspace.backend_metadata = {
        key: value for key, value in dict(workspace.backend_metadata or {}).items() if key != "live_workspace_snapshot"
    }
    await db_session.commit()

    heartbeat_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/heartbeat", headers=headers)
    assert heartbeat_resp.status_code == 200
    payload = heartbeat_resp.json()["live_workspace_snapshot"]

    assert sorted(payload["files"].keys()) == ["src/App.tsx", "src/routes.tsx"]
    assert payload["entry_file"] == "src/App.tsx"
    assert payload["revision_token"] == "restored-token-2"

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert sorted(session.backend_metadata["live_workspace_snapshot"]["files"].keys()) == ["src/App.tsx", "src/routes.tsx"]
    assert workspace.backend_metadata["live_workspace_snapshot"]["entry_file"] == "src/App.tsx"


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
