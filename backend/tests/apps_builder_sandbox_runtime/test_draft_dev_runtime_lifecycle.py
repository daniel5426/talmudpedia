from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routers import published_apps_admin_files as builder_files_module
from app.api.routers import published_apps_admin_routes_builder as builder_routes_module
from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, User
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppDraftWorkspace,
    PublishedAppDraftWorkspaceStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppStatus,
    PublishedAppVisibility,
    PublishedAppWorkspaceBuild,
    PublishedAppWorkspaceBuildStatus,
)
from app.services import published_app_draft_dev_runtime as runtime_module
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError
from app.services.published_app_draft_revision_materializer import PublishedAppDraftRevisionMaterializerService
from app.services.published_app_live_preview import build_live_preview_overlay_workspace_fingerprint
from app.services.published_app_templates import TemplateRuntimeContext
from app.services.published_app_versioning import create_app_version
from app.services.security_bootstrap_service import SecurityBootstrapService
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


def test_builder_project_validation_requires_root_index_html():
    with pytest.raises(HTTPException) as exc_info:
        builder_files_module._validate_builder_project_or_raise(
            {
                "src/main.tsx": "import './App';",
                "src/App.tsx": "export default function App() { return <div />; }",
            },
            "src/main.tsx",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "BUILDER_COMPILE_FAILED"
    assert exc_info.value.detail["diagnostics"] == [
        {"path": "index.html", "message": "Required root file is missing"}
    ]


async def _noop_scope_lock(self, *, app_id, user_id):
    _ = self, app_id, user_id
    return None


async def _create_builder_app(
    db_session,
    *,
    organization_id,
    user_id,
    agent_id,
    name: str,
) -> str:
    app, _revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=organization_id,
        agent_id=UUID(str(agent_id)),
        user_id=user_id,
        name=name,
    )
    return str(app.id)


async def _seed_builder_app_and_revision(
    db_session,
    *,
    organization_id,
    agent_id,
    user_id,
    name: str,
):
    app = PublishedApp(
        organization_id=organization_id,
        agent_id=agent_id,
        name=name,
        public_id=f"app-{uuid4().hex[:10]}",
        template_key="classic-chat",
        auth_enabled=True,
        auth_providers=["password"],
        auth_template_key="auth-classic",
        visibility=PublishedAppVisibility.private,
        status=PublishedAppStatus.draft,
        created_by=user_id,
    )
    db_session.add(app)
    await db_session.flush()
    revision = await create_app_version(
        db_session,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file="src/main.tsx",
        files={
            "index.html": "<!doctype html><html><body><div id='root'></div><script type='module' src='/src/main.tsx'></script></body></html>",
            "src/main.tsx": "console.log('hi')\n",
        },
        created_by=user_id,
        source_revision_id=None,
        origin_kind="test",
    )
    app.current_draft_revision_id = revision.id
    await db_session.commit()
    await db_session.refresh(app)
    await db_session.refresh(revision)
    return app, revision


async def _seed_second_owner(db_session, *, organization_id, org_unit_id) -> User:
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        OrgMembership(
            organization_id=organization_id,
            user_id=user.id,
            org_unit_id=org_unit_id,
            status=MembershipStatus.active,
        )
    )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(organization_id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=organization_id,
        user_id=user.id,
        assigned_by=user.id,
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
    user_b = await _seed_second_owner(db_session, organization_id=tenant.id, org_unit_id=org_unit.id)
    headers_a = admin_headers(str(user_a.id), str(tenant.id), str(org_unit.id))
    headers_b = admin_headers(str(user_b.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user_a.id,
        agent_id=agent.id,
        name="Shared Sprite App",
    )

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
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app, revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Heartbeat Refresh App",
    )
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    session = await runtime_service.ensure_session(
        app=app,
        revision=revision,
        user_id=user.id,
        files=dict(revision.files or {}),
        entry_file=revision.entry_file,
    )
    await db_session.commit()
    session_id = UUID(str(session.id))
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

    async def _fake_resolve_ctx(request, principal, db):
        _ = request, principal, db
        return {"organization_id": tenant.id, "user": user}

    async def _fake_get_app_for_tenant(db, organization_id, app_id):
        _ = db, organization_id, app_id
        return app

    async def _fake_get_session_for_scope(db, app_id, user_id):
        _ = db, app_id, user_id
        return session

    async def _fake_no_publish_job(db, app_id):
        _ = db, app_id
        return None

    monkeypatch.setattr(builder_routes_module, "_resolve_tenant_admin_context", _fake_resolve_ctx)
    monkeypatch.setattr(builder_routes_module, "_assert_can_manage_apps", lambda ctx: None)
    monkeypatch.setattr(builder_routes_module, "_get_app_for_tenant", _fake_get_app_for_tenant)
    monkeypatch.setattr(builder_routes_module, "_get_draft_dev_session_for_scope", _fake_get_session_for_scope)
    monkeypatch.setattr(builder_routes_module, "_get_active_publish_job_for_app", _fake_no_publish_job)

    heartbeat_resp = await builder_routes_module.heartbeat_builder_draft_dev_session(
        app_id=app.id,
        request=SimpleNamespace(
            base_url="http://testserver/",
            scope={"root_path": ""},
            headers={},
            url=SimpleNamespace(path=f"/admin/apps/{app.id}/builder/draft-dev/session/heartbeat"),
        ),
        _={},
        principal={},
        db=db_session,
    )
    assert heartbeat_resp.status == "serving"

    await db_session.refresh(workspace)
    await db_session.refresh(session)
    assert workspace.backend_metadata["preview"]["upstream_base_url"].startswith("https://sprite-")
    assert session.backend_metadata["preview"]["upstream_base_url"] == workspace.backend_metadata["preview"]["upstream_base_url"]
    assert workspace.backend_metadata["preview"]["base_path"] == str(session.preview_url)


@pytest.mark.asyncio
async def test_builder_state_heartbeats_stale_degraded_session_before_serializing(
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

    app, revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Builder State Heartbeat App",
    )
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    session = await runtime_service.ensure_session(
        app=app,
        revision=revision,
        user_id=user.id,
        files=dict(revision.files or {}),
        entry_file=revision.entry_file,
    )
    await db_session.commit()
    session_id = UUID(str(session.id))
    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None

    session.status = PublishedAppDraftDevSessionStatus.degraded
    session.last_error = "stale transient error"
    workspace.status = PublishedAppDraftWorkspaceStatus.degraded
    workspace.last_error = "stale transient error"
    await db_session.commit()

    async def _fake_resolve_ctx(request, principal, db):
        _ = request, principal, db
        return {"organization_id": tenant.id, "user": user}

    async def _fake_get_app_for_tenant(db, organization_id, app_id):
        _ = db, organization_id, app_id
        return app

    async def _fake_get_revision(db, revision_id):
        _ = db
        if revision_id == app.current_draft_revision_id:
            return revision
        return None

    async def _fake_get_session_for_scope(db, app_id, user_id):
        _ = db, app_id, user_id
        return session

    monkeypatch.setattr(builder_routes_module, "_resolve_tenant_admin_context", _fake_resolve_ctx)
    monkeypatch.setattr(builder_routes_module, "_assert_can_manage_apps", lambda ctx: None)
    monkeypatch.setattr(builder_routes_module, "_get_app_for_tenant", _fake_get_app_for_tenant)
    monkeypatch.setattr(builder_routes_module, "_get_revision", _fake_get_revision)
    monkeypatch.setattr(builder_routes_module, "_get_draft_dev_session_for_scope", _fake_get_session_for_scope)

    state_resp = await builder_routes_module.get_builder_state(
        app_id=app.id,
        request=SimpleNamespace(
            base_url="http://testserver/",
            scope={"root_path": ""},
            headers={},
            url=SimpleNamespace(path=f"/admin/apps/{app.id}/builder/state"),
        ),
        _={},
        principal={},
        db=db_session,
    )
    assert state_resp.draft_dev is not None
    assert state_resp.draft_dev.status == "serving"

    await db_session.refresh(session)
    await db_session.refresh(workspace)
    assert session.status == PublishedAppDraftDevSessionStatus.serving
    assert workspace.status == PublishedAppDraftWorkspaceStatus.serving


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

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        name="Prefer Live Workspace App",
    )
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
async def test_heartbeat_reattaches_detached_session_to_existing_workspace():
    workspace_id = uuid4()
    sandbox_id = "sprite-reattach-1"
    workspace = SimpleNamespace(
        id=workspace_id,
        published_app_id=uuid4(),
        sandbox_id=sandbox_id,
        runtime_backend="sprite",
        backend_metadata={"preview": {"upstream_base_url": "https://sprite.example"}},
        preview_url="/public/apps-builder/draft-dev/sessions/current/preview/",
        last_activity_at=None,
        detached_at=datetime.now(timezone.utc),
    )
    revision = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    db.get.return_value = revision
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    runtime_service.client = SimpleNamespace(
        backend_name="sprite",
        build_preview_proxy_path=lambda session_id: f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/",
        heartbeat_session=AsyncMock(
            return_value={
                "sandbox_id": sandbox_id,
                "backend_metadata": {"preview": {"upstream_base_url": "https://sprite.example"}},
            }
        ),
    )
    runtime_service.get_workspace = AsyncMock(return_value=workspace)
    runtime_service._restore_live_workspace_snapshot_from_runtime = AsyncMock(return_value=None)
    session = SimpleNamespace(
        id=uuid4(),
        published_app_id=workspace.published_app_id,
        user_id=uuid4(),
        revision_id=revision.id,
        draft_workspace_id=None,
        sandbox_id=None,
        runtime_generation=0,
        runtime_backend=None,
        backend_metadata={},
        preview_url=None,
        status=PublishedAppDraftDevSessionStatus.starting,
        last_error=None,
    )

    result = await runtime_service.heartbeat_session(session=session)

    assert result.draft_workspace_id == workspace_id
    assert result.sandbox_id == sandbox_id
    assert result.status == PublishedAppDraftDevSessionStatus.serving
    assert result.last_error is None
    runtime_service.client.heartbeat_session.assert_awaited_once_with(
        sandbox_id=sandbox_id,
        idle_timeout_seconds=runtime_service.settings.idle_timeout_seconds,
    )


@pytest.mark.asyncio
async def test_ensure_session_failure_keeps_session_attached_to_workspace():
    app = SimpleNamespace(id=uuid4(), organization_id=uuid4(), public_id="app", agent_id=uuid4())
    revision = SimpleNamespace(id=uuid4(), files={"src/App.tsx": "export default 1;"}, entry_file="src/App.tsx")
    workspace = SimpleNamespace(
        id=uuid4(),
        sandbox_id=None,
        backend_metadata={},
        status=PublishedAppDraftWorkspaceStatus.starting,
        last_error=None,
        runtime_backend="sprite",
        dependency_hash=None,
    )
    session = SimpleNamespace(
        id=uuid4(),
        revision_id=None,
        draft_workspace_id=None,
        idle_timeout_seconds=None,
        last_activity_at=None,
        expires_at=None,
        preview_url=None,
        sandbox_id=None,
        runtime_generation=0,
        runtime_backend=None,
        backend_metadata={},
        dependency_hash=None,
        last_error=None,
        status=PublishedAppDraftDevSessionStatus.starting,
    )
    db = AsyncMock()
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    runtime_service.client = SimpleNamespace(
        backend_name="sprite",
        build_preview_proxy_path=lambda session_id: f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/",
    )
    runtime_service._acquire_scope_lock = AsyncMock(return_value=None)
    runtime_service.expire_idle_sessions = AsyncMock(return_value=None)
    runtime_service.sweep_dormant_workspaces = AsyncMock(return_value=None)
    runtime_service._sweep_remote_workspaces_best_effort = AsyncMock(return_value=None)
    runtime_service._get_or_create_workspace = AsyncMock(return_value=workspace)
    runtime_service._get_or_create_session = AsyncMock(return_value=session)
    runtime_service._start_or_sync_workspace = AsyncMock(
        side_effect=PublishedAppDraftDevRuntimeClientError("ConnectTimeout")
    )

    result = await runtime_service.ensure_session(
        app=app,
        revision=revision,
        user_id=uuid4(),
    )

    assert result.draft_workspace_id == workspace.id
    assert result.status == PublishedAppDraftDevSessionStatus.degraded
    assert result.last_error == "ConnectTimeout"
    assert workspace.status == PublishedAppDraftWorkspaceStatus.degraded
    assert workspace.last_error == "ConnectTimeout"


@pytest.mark.asyncio
async def test_ensure_endpoint_reuses_live_session_without_calling_legacy_ensure_session(
    monkeypatch: pytest.MonkeyPatch,
):
    organization_id = uuid4()
    user_id = uuid4()
    app_id = uuid4()
    revision_id = uuid4()
    session_id = uuid4()
    ctx = {"organization_id": organization_id, "user": SimpleNamespace(id=user_id)}
    app = SimpleNamespace(id=app_id, organization_id=organization_id, public_id="delete-sync-app", agent_id=uuid4())
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
async def test_sync_route_batches_operations_into_single_workspace_sync(
    monkeypatch: pytest.MonkeyPatch,
):
    organization_id = uuid4()
    user_id = uuid4()
    app_id = uuid4()
    revision_id = uuid4()
    session_id = uuid4()
    sandbox_id = "sprite-sandbox-1"
    ctx = {"organization_id": organization_id, "user": SimpleNamespace(id=user_id)}
    app = SimpleNamespace(id=app_id, organization_id=organization_id, public_id="delete-sync-app", agent_id=uuid4())
    revision = SimpleNamespace(
        id=revision_id,
        files={
            "index.html": "<html></html>",
            "package.json": "{\"name\":\"app\",\"dependencies\":{}}",
            "src/App.tsx": "app",
        },
        entry_file="src/App.tsx",
    )
    session = SimpleNamespace(
        id=session_id,
        sandbox_id=sandbox_id,
        revision_id=revision_id,
        backend_metadata={
            "workspace": {
                "live_workspace_path": "/home/sprite/app",
            },
            "live_workspace_snapshot": {
                "entry_file": "src/App.tsx",
                "files": {
                    "index.html": "<html></html>",
                    "package.json": "{\"name\":\"app\",\"dependencies\":{}}",
                    "src/App.tsx": "app",
                    "src/deleted.tsx": "stale",
                },
            }
        },
    )
    db = AsyncMock()
    request = SimpleNamespace()
    fake_client = SimpleNamespace(
        sync_workspace_files=AsyncMock(
            return_value={
                "revision_token": "sync-1",
            }
        ),
        resolve_local_workspace_path=AsyncMock(return_value="/home/sprite/app"),
    )
    fake_runtime_service = SimpleNamespace(
        client=fake_client,
        record_workspace_live_snapshot=AsyncMock(return_value=None),
        record_live_workspace_revision_token=AsyncMock(return_value=session),
        record_live_workspace_materialization_request=AsyncMock(return_value=None),
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
    fake_client.sync_workspace_files.assert_awaited_once_with(
        sandbox_id=sandbox_id,
        workspace_path="/home/sprite/app",
        files={
            "index.html": "<html></html>",
            "package.json": "{\"name\":\"app\",\"dependencies\":{}}",
            "src/App.tsx": "app",
        },
    )
    fake_client.resolve_local_workspace_path.assert_not_awaited()
    fake_runtime_service.record_workspace_live_snapshot.assert_awaited_once()
    fake_runtime_service.record_live_workspace_revision_token.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_route_validates_operations_before_mutating_runtime(
    monkeypatch: pytest.MonkeyPatch,
):
    organization_id = uuid4()
    user_id = uuid4()
    app_id = uuid4()
    revision_id = uuid4()
    session_id = uuid4()
    sandbox_id = "sprite-sandbox-1"
    ctx = {"organization_id": organization_id, "user": SimpleNamespace(id=user_id)}
    app = SimpleNamespace(id=app_id, organization_id=organization_id, public_id="validate-sync-app", agent_id=uuid4())
    revision = SimpleNamespace(
        id=revision_id,
        files={
            "index.html": "<html></html>",
            "package.json": "{\"name\":\"app\",\"dependencies\":{}}",
            "src/main.tsx": "import './App';",
            "src/App.tsx": "export default function App() { return <div />; }",
        },
        entry_file="src/main.tsx",
    )
    session = SimpleNamespace(
        id=session_id,
        sandbox_id=sandbox_id,
        revision_id=revision_id,
        backend_metadata={
            "live_workspace_snapshot": {
                "entry_file": "src/main.tsx",
                "files": dict(revision.files),
            }
        },
    )
    db = AsyncMock()
    request = SimpleNamespace()
    fake_client = SimpleNamespace(
        sync_workspace_files=AsyncMock(),
        resolve_local_workspace_path=AsyncMock(return_value="/home/sprite/app"),
    )
    fake_runtime_service = SimpleNamespace(
        client=fake_client,
        record_workspace_live_snapshot=AsyncMock(return_value=None),
        record_live_workspace_revision_token=AsyncMock(return_value=session),
        record_live_workspace_materialization_request=AsyncMock(return_value=None),
    )

    monkeypatch.setattr(builder_routes_module, "_resolve_tenant_admin_context", AsyncMock(return_value=ctx))
    monkeypatch.setattr(builder_routes_module, "_assert_can_manage_apps", lambda resolved_ctx: None)
    monkeypatch.setattr(builder_routes_module, "_assert_no_active_coding_run_for_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(builder_routes_module, "_get_app_for_tenant", AsyncMock(return_value=app))
    monkeypatch.setattr(builder_routes_module, "_ensure_current_draft_revision", AsyncMock(return_value=revision))
    monkeypatch.setattr(builder_routes_module, "_get_draft_dev_session_for_scope", AsyncMock(return_value=session))
    monkeypatch.setattr(builder_routes_module, "PublishedAppDraftDevRuntimeService", lambda db: fake_runtime_service)

    with pytest.raises(HTTPException) as exc_info:
        await builder_routes_module.sync_builder_draft_dev_session(
            app_id=app_id,
            payload=builder_routes_module.DraftDevSyncRequest(
                operations=[{"op": "delete_file", "path": "index.html"}],
            ),
            request=request,
            _={},
            principal={},
            db=db,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["diagnostics"] == [
        {"path": "index.html", "message": "Required root file is missing"}
    ]
    fake_client.sync_workspace_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_route_records_saved_workspace_fingerprint_and_pending_materialization(
    monkeypatch: pytest.MonkeyPatch,
):
    organization_id = uuid4()
    user_id = uuid4()
    app_id = uuid4()
    agent_id = uuid4()
    revision_id = uuid4()
    session_id = uuid4()
    ctx = {"organization_id": organization_id, "user": SimpleNamespace(id=user_id)}
    app = SimpleNamespace(id=app_id, organization_id=organization_id, public_id="saved-workspace-app", agent_id=agent_id)
    revision = SimpleNamespace(
        id=revision_id,
        files={
            "index.html": "<html></html>",
            "package.json": "{\"name\":\"app\",\"dependencies\":{}}",
            "src/main.tsx": "import './App';",
            "src/App.tsx": "export default function App() { return <div>draft</div>; }",
        },
        entry_file="src/main.tsx",
    )
    session = SimpleNamespace(
        id=session_id,
        sandbox_id="sprite-sandbox-1",
        revision_id=revision_id,
        backend_metadata={
            "preview_runtime": {"workspace_revision_token": "rev-token-2"},
        },
    )
    db = AsyncMock()
    request = SimpleNamespace()
    synced_files = {
        **revision.files,
        "src/App.tsx": "export default function App() { return <div>saved</div>; }",
    }
    expected_fingerprint = build_live_preview_overlay_workspace_fingerprint(
        entry_file=revision.entry_file,
        files=synced_files,
        runtime_context=TemplateRuntimeContext(
            app_id=str(app_id),
            app_public_id="saved-workspace-app",
            agent_id=str(agent_id),
        ),
    )
    fake_runtime_service = SimpleNamespace(
        sync_session=AsyncMock(return_value=session),
        record_workspace_live_snapshot=AsyncMock(return_value=None),
        record_live_workspace_materialization_request=AsyncMock(return_value=None),
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
            files=synced_files,
            entry_file=revision.entry_file,
            revision_id=revision_id,
        ),
        request=request,
        _={},
        principal={},
        db=db,
    )

    assert result == {"session_id": str(session_id)}
    fake_runtime_service.record_workspace_live_snapshot.assert_awaited_once_with(
        app_id=app_id,
        revision_id=revision_id,
        entry_file=revision.entry_file,
        files=synced_files,
        revision_token="rev-token-2",
        workspace_fingerprint=expected_fingerprint,
    )
    fake_runtime_service.record_live_workspace_materialization_request.assert_awaited_once_with(
        app_id=app_id,
        origin_kind="manual_save",
        source_revision_id=revision_id,
        created_by=user_id,
    )
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

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        name="Heartbeat Base Path Preserve App",
    )

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

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        name="Heartbeat Snapshot Preserve App",
    )

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
async def test_heartbeat_materializes_saved_workspace_when_live_preview_ready(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app, current_revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Heartbeat Materialize App",
    )
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    session = await runtime_service.ensure_session(
        app=app,
        revision=current_revision,
        user_id=user.id,
        files=dict(current_revision.files or {}),
        entry_file=current_revision.entry_file,
    )
    await db_session.commit()
    session_id = session.id

    saved_files = {
        **dict(current_revision.files or {}),
        "src/App.tsx": "export default function App() { return <main>saved-workspace</main>; }",
    }
    expected_fingerprint = build_live_preview_overlay_workspace_fingerprint(
        entry_file=current_revision.entry_file,
        files=saved_files,
        runtime_context=TemplateRuntimeContext(
            app_id=str(app.id),
            app_public_id=str(app.public_id or ""),
            agent_id=str(app.agent_id or ""),
        ),
    )

    await runtime_service.record_workspace_live_snapshot(
        app_id=app.id,
        revision_id=current_revision.id,
        entry_file=current_revision.entry_file,
        files=saved_files,
        revision_token="saved-rev-token",
        workspace_fingerprint=expected_fingerprint,
    )
    await runtime_service.record_live_workspace_materialization_request(
        app_id=app.id,
        origin_kind="manual_save",
        source_revision_id=current_revision.id,
        created_by=user.id,
    )

    materialized_revision = await create_app_version(
        db_session,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=current_revision.entry_file,
        files=saved_files,
        created_by=user.id,
        source_revision_id=current_revision.id,
        origin_kind="manual_save",
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        dist_storage_prefix=f"published-apps/test/{uuid4()}/dist",
        dist_manifest={"source_fingerprint": expected_fingerprint},
        template_runtime="vite_static",
    )
    await db_session.commit()

    async def _heartbeat_with_ready_preview(**kwargs):
        payload = await _FakeSpriteRuntimeClient.heartbeat_session(fake_client, **kwargs)
        backend_metadata = dict(payload.get("backend_metadata") or {})
        backend_metadata["live_preview"] = {
            "status": "ready",
            "workspace_fingerprint": expected_fingerprint,
            "last_successful_build_id": "build-2",
            "dist_path": "/home/sprite/.talmudpedia/live-preview/current",
        }
        payload["backend_metadata"] = backend_metadata
        return payload

    fake_client.heartbeat_session = _heartbeat_with_ready_preview

    async def _materialize_stub(self, *, app, **kwargs):
        _ = self, kwargs
        app.current_draft_revision_id = materialized_revision.id
        return SimpleNamespace(
            revision=materialized_revision,
            reused=False,
            source_fingerprint=expected_fingerprint,
            workspace_revision_token="saved-rev-token",
        )

    monkeypatch.setattr(
        "app.services.published_app_draft_revision_materializer.PublishedAppDraftRevisionMaterializerService.materialize_live_workspace",
        _materialize_stub,
    )

    session = await runtime_service.heartbeat_session(session=session)
    await db_session.commit()
    assert session.revision_id == materialized_revision.id

    await db_session.refresh(app)
    assert app.current_draft_revision_id == materialized_revision.id

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert session.revision_id == materialized_revision.id
    assert "live_workspace_materialization" not in dict(session.backend_metadata or {})
    assert "live_workspace_materialization" not in dict(workspace.backend_metadata or {})


@pytest.mark.asyncio
async def test_heartbeat_materializes_live_preview_without_explicit_request(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app, current_revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Heartbeat Auto Materialize App",
    )
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    session = await runtime_service.ensure_session(
        app=app,
        revision=current_revision,
        user_id=user.id,
        files=dict(current_revision.files or {}),
        entry_file=current_revision.entry_file,
    )
    await db_session.commit()
    session_id = session.id

    edited_files = {
        **dict(current_revision.files or {}),
        "src/App.tsx": "export default function App() { return <main>auto-materialized</main>; }",
    }
    expected_fingerprint = build_live_preview_overlay_workspace_fingerprint(
        entry_file=current_revision.entry_file,
        files=edited_files,
        runtime_context=TemplateRuntimeContext(
            app_id=str(app.id),
            app_public_id=str(app.public_id or ""),
            agent_id=str(app.agent_id or ""),
        ),
    )

    await runtime_service.record_workspace_live_snapshot(
        app_id=app.id,
        revision_id=current_revision.id,
        entry_file=current_revision.entry_file,
        files=edited_files,
        revision_token="auto-rev-token",
        workspace_fingerprint=expected_fingerprint,
    )

    materialized_revision = await create_app_version(
        db_session,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=current_revision.entry_file,
        files=edited_files,
        created_by=user.id,
        source_revision_id=current_revision.id,
        origin_kind="live_preview",
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        dist_storage_prefix=f"published-apps/test/{uuid4()}/dist",
        dist_manifest={"source_fingerprint": expected_fingerprint},
        template_runtime="vite_static",
    )
    await db_session.commit()

    async def _heartbeat_with_ready_preview(**kwargs):
        payload = await _FakeSpriteRuntimeClient.heartbeat_session(fake_client, **kwargs)
        backend_metadata = dict(payload.get("backend_metadata") or {})
        backend_metadata["live_preview"] = {
            "status": "ready",
            "workspace_fingerprint": expected_fingerprint,
            "debug_last_trigger_revision_token": "auto-rev-token",
            "last_successful_build_id": "build-auto",
            "dist_path": "/home/sprite/.talmudpedia/live-preview/current",
        }
        payload["backend_metadata"] = backend_metadata
        return payload

    fake_client.heartbeat_session = _heartbeat_with_ready_preview

    async def _materialize_stub(self, *, app, **kwargs):
        _ = self, kwargs
        app.current_draft_revision_id = materialized_revision.id
        return SimpleNamespace(
            revision=materialized_revision,
            reused=False,
            source_fingerprint=expected_fingerprint,
            workspace_revision_token="auto-rev-token",
        )

    monkeypatch.setattr(
        "app.services.published_app_draft_revision_materializer.PublishedAppDraftRevisionMaterializerService.materialize_live_workspace",
        _materialize_stub,
    )

    session = await runtime_service.heartbeat_session(session=session)
    await db_session.commit()
    assert session.revision_id == materialized_revision.id

    await db_session.refresh(app)
    assert app.current_draft_revision_id == materialized_revision.id

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert "live_workspace_materialization" not in dict(session.backend_metadata or {})
    assert "live_workspace_materialization" not in dict(workspace.backend_metadata or {})


@pytest.mark.asyncio
async def test_materializer_reuses_current_revision_when_workspace_build_is_unchanged(
    db_session,
):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app, _ = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Materializer Reuse App",
    )
    workspace_fingerprint = "same-build-fingerprint"
    workspace_build = PublishedAppWorkspaceBuild(
        published_app_id=app.id,
        workspace_fingerprint=workspace_fingerprint,
        status=PublishedAppWorkspaceBuildStatus.ready,
        entry_file="src/main.tsx",
        source_snapshot={"src/main.tsx": "console.log('same')\n"},
        origin_kind="app_init",
        created_by=user.id,
        build_started_at=datetime.now(timezone.utc),
        build_finished_at=datetime.now(timezone.utc),
        dist_storage_prefix=f"published-apps/test/{uuid4()}/dist",
        dist_manifest={"source_fingerprint": workspace_fingerprint},
        template_runtime="vite_static",
    )
    db_session.add(workspace_build)
    await db_session.flush()

    current_revision = await create_app_version(
        db_session,
        workspace_build_id=workspace_build.id,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file="src/main.tsx",
        files={
            "index.html": "<!doctype html><html><body><div id='root'></div><script type='module' src='/src/main.tsx'></script></body></html>",
            "src/main.tsx": "console.log('same')\n",
        },
        created_by=user.id,
        source_revision_id=None,
        origin_kind="app_init",
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        dist_storage_prefix=workspace_build.dist_storage_prefix,
        dist_manifest={"source_fingerprint": workspace_fingerprint},
        template_runtime="vite_static",
    )
    app.current_draft_revision_id = current_revision.id
    await db_session.commit()
    before_revision_ids = list(
        (
            await db_session.execute(
                select(PublishedAppRevision.id).where(PublishedAppRevision.published_app_id == app.id)
            )
        ).scalars()
    )

    materializer = PublishedAppDraftRevisionMaterializerService(db_session)
    result = await materializer._create_or_reuse_revision_from_build(  # noqa: SLF001
        app=app,
        build_result=SimpleNamespace(
            build=workspace_build,
            reused=True,
            source_fingerprint=workspace_fingerprint,
            workspace_revision_token="rev-token-1",
        ),
        source_revision_id=current_revision.id,
        created_by=user.id,
        origin_kind="live_preview",
        origin_run_id=None,
    )
    await db_session.commit()

    revision_ids = list(
        (
            await db_session.execute(
                select(PublishedAppRevision.id).where(PublishedAppRevision.published_app_id == app.id)
            )
        ).scalars()
    )
    assert result.revision.id == current_revision.id
    assert result.reused is True
    assert revision_ids == before_revision_ids


@pytest.mark.asyncio
async def test_heartbeat_restores_missing_live_workspace_snapshot_from_runtime(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
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
    app, current_revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Heartbeat Snapshot Restore App",
    )
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    session = await runtime_service.ensure_session(
        app=app,
        revision=current_revision,
        user_id=user.id,
        files=dict(current_revision.files or {}),
        entry_file=current_revision.entry_file,
    )
    await db_session.commit()
    session_id = session.id
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    session.backend_metadata = {
        key: value for key, value in dict(session.backend_metadata or {}).items() if key != "live_workspace_snapshot"
    }
    workspace.backend_metadata = {
        key: value for key, value in dict(workspace.backend_metadata or {}).items() if key != "live_workspace_snapshot"
    }
    await db_session.commit()

    session = await runtime_service.heartbeat_session(session=session)
    await db_session.commit()
    assert session.backend_metadata["live_workspace_snapshot"]["files"]["src/App.tsx"].endswith("restored</div>; }")

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert session.backend_metadata["live_workspace_snapshot"]["revision_token"] == "restored-token"
    assert workspace.backend_metadata["live_workspace_snapshot"]["files"]["src/App.tsx"].endswith("restored</div>; }")


@pytest.mark.asyncio
async def test_heartbeat_refreshes_stale_live_workspace_snapshot_when_preview_differs(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    tenant, user, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    fake_client = _FakeSpriteRuntimeClient()

    refreshed_files = {
        "src/App.tsx": "export default function App() { return <div>refreshed</div>; }",
        "index.html": "<html></html>",
    }

    async def _snapshot_files(**kwargs):
        _ = kwargs
        return {
            "files": refreshed_files,
            "revision_token": "refresh-token",
        }

    async def _heartbeat_with_ready_preview(**kwargs):
        payload = await _FakeSpriteRuntimeClient.heartbeat_session(fake_client, **kwargs)
        backend_metadata = dict(payload.get("backend_metadata") or {})
        backend_metadata["live_preview"] = {
            "status": "ready",
            "workspace_fingerprint": "refresh-fingerprint",
            "debug_last_trigger_revision_token": "refresh-token",
            "last_successful_build_id": "build-refresh",
            "dist_path": "/home/sprite/.talmudpedia/live-preview/current",
        }
        payload["backend_metadata"] = backend_metadata
        return payload

    fake_client.snapshot_files = _snapshot_files
    fake_client.heartbeat_session = _heartbeat_with_ready_preview

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )
    app, current_revision = await _seed_builder_app_and_revision(
        db_session,
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        name="Heartbeat Snapshot Refresh App",
    )
    runtime_service = PublishedAppDraftDevRuntimeService(db_session)
    session = await runtime_service.ensure_session(
        app=app,
        revision=current_revision,
        user_id=user.id,
        files=dict(current_revision.files or {}),
        entry_file=current_revision.entry_file,
    )
    await db_session.commit()
    session_id = session.id
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None

    stale_snapshot = {
        "revision_id": str(session.revision_id),
        "entry_file": "src/App.tsx",
        "files": {"src/App.tsx": "export default function App() { return <div>stale</div>; }"},
        "revision_token": "stale-token",
        "workspace_fingerprint": "stale-fingerprint",
        "updated_at": "2026-04-17T00:00:00+00:00",
    }
    session.backend_metadata = {**dict(session.backend_metadata or {}), "live_workspace_snapshot": stale_snapshot}
    workspace.backend_metadata = {**dict(workspace.backend_metadata or {}), "live_workspace_snapshot": stale_snapshot}
    await db_session.commit()

    session = await runtime_service.heartbeat_session(session=session)
    await db_session.commit()
    payload = session.backend_metadata["live_workspace_snapshot"]

    assert payload["revision_token"] == "refresh-token"
    assert payload["workspace_fingerprint"] == "refresh-fingerprint"
    assert payload["files"]["src/App.tsx"].endswith("refreshed</div>; }")

    session = await db_session.get(PublishedAppDraftDevSession, session_id)
    assert session is not None
    workspace = await db_session.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
    assert workspace is not None
    assert session.backend_metadata["live_workspace_snapshot"]["revision_token"] == "refresh-token"
    assert workspace.backend_metadata["live_workspace_snapshot"]["workspace_fingerprint"] == "refresh-fingerprint"


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

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        name="Heartbeat Snapshot Policy App",
    )

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
    user_b = await _seed_second_owner(db_session, organization_id=tenant.id, org_unit_id=org_unit.id)
    headers_a = admin_headers(str(user_a.id), str(tenant.id), str(org_unit.id))
    headers_b = admin_headers(str(user_b.id), str(tenant.id), str(org_unit.id))
    fake_client = _FakeSpriteRuntimeClient()

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: fake_client),
    )

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user_a.id,
        agent_id=agent.id,
        name="Dormant Sprite App",
    )

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

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        name="Restart Sprite App",
    )

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

    app_id = await _create_builder_app(
        db_session,
        organization_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        name="Delete Sprite App",
    )

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200

    delete_resp = await client.delete(f"/admin/apps/{app_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert fake_client.stop_calls

    workspace = await db_session.scalar(
        select(PublishedAppDraftWorkspace).where(PublishedAppDraftWorkspace.published_app_id == UUID(app_id))
    )
    assert workspace is None
