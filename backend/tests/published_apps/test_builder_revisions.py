from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.routers.published_apps_admin import BUILDER_MAX_FILE_BYTES
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedAppDraftDevSession, PublishedAppDraftDevSessionStatus
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService

from ._helpers import admin_headers, seed_admin_tenant_and_agent, start_publish_and_wait


@pytest.mark.asyncio
async def test_builder_state_and_revision_workflow(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Builder App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_payload = create_resp.json()
    app_id = app_payload["id"]
    assert app_payload["slug"]
    assert app_payload["template_key"] == "chat-classic"

    templates_resp = await client.get("/admin/apps/templates", headers=headers)
    assert templates_resp.status_code == 200
    templates_payload = templates_resp.json()
    assert len(templates_payload) >= 6
    premium_template = next((template for template in templates_payload if template["key"] == "chat-grid"), None)
    assert premium_template is not None
    assert premium_template["name"] == "Layout Shell Premium"
    fresh_template = next((template for template in templates_payload if template["key"] == "fresh-start"), None)
    assert fresh_template is not None
    assert fresh_template["entry_file"] == "src/main.tsx"

    builder_state = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert builder_state.status_code == 200
    state_payload = builder_state.json()
    assert state_payload["app"]["id"] == app_id
    assert state_payload["current_draft_revision"]["id"]
    assert state_payload["preview_token"]
    assert ".opencode/package.json" in state_payload["current_draft_revision"]["files"]
    assert (
        ".opencode/tools/read_agent_context.ts"
        in state_payload["current_draft_revision"]["files"]
    )
    assert "runtime-sdk/package.json" in state_payload["current_draft_revision"]["files"]
    assert "runtime-sdk/src/index.ts" in state_payload["current_draft_revision"]["files"]
    assert "src/runtime-config.json" in state_payload["current_draft_revision"]["files"]
    seeded_package_json = state_payload["current_draft_revision"]["files"]["package.json"]
    assert "\"@talmudpedia/runtime-sdk\": \"file:runtime-sdk\"" in seeded_package_json
    draft_revision_id = state_payload["current_draft_revision"]["id"]

    conflict_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": "00000000-0000-0000-0000-000000000001",
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export function App() { return <div>Conflict</div>; }",
                }
            ],
        },
    )
    assert conflict_resp.status_code == 409
    conflict_payload = conflict_resp.json()["detail"]
    assert conflict_payload["code"] == "REVISION_CONFLICT"
    assert conflict_payload["latest_revision_id"] == draft_revision_id

    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export function App() { return <div>Updated</div>; }",
                }
            ],
        },
    )
    assert revision_resp.status_code == 200
    revision_payload = revision_resp.json()
    assert revision_payload["source_revision_id"] == draft_revision_id
    assert "Updated" in revision_payload["files"]["src/App.tsx"]

    reset_resp = await client.post(
        f"/admin/apps/{app_id}/builder/template-reset",
        headers=headers,
        json={"template_key": "chat-grid"},
    )
    assert reset_resp.status_code == 200
    reset_payload = reset_resp.json()
    assert reset_payload["template_key"] == "chat-grid"
    assert reset_payload["entry_file"] in reset_payload["files"]
    assert "src/components/layout/LayoutShell.tsx" in reset_payload["files"]
    assert "src/components/layout/ChatPane.tsx" in reset_payload["files"]
    assert "src/components/layout/SourceListPane.tsx" in reset_payload["files"]
    assert "src/components/layout/SourceViewerPane.tsx" in reset_payload["files"]

    fresh_reset_resp = await client.post(
        f"/admin/apps/{app_id}/builder/template-reset",
        headers=headers,
        json={"template_key": "fresh-start"},
    )
    assert fresh_reset_resp.status_code == 200
    fresh_reset_payload = fresh_reset_resp.json()
    assert fresh_reset_payload["template_key"] == "fresh-start"
    assert "src/main.tsx" in fresh_reset_payload["files"]
    assert "src/runtime-sdk.ts" in fresh_reset_payload["files"]
    assert "src/runtime-config.json" in fresh_reset_payload["files"]
    assert "runtime-sdk/package.json" in fresh_reset_payload["files"]
    assert ".opencode/package.json" in fresh_reset_payload["files"]

    _, publish_status = await start_publish_and_wait(client, app_id=app_id, headers=headers)
    assert publish_status["status"] == "succeeded"
    assert publish_status["published_revision_id"]

    app_resp = await client.get(f"/admin/apps/{app_id}", headers=headers)
    assert app_resp.status_code == 200
    published = app_resp.json()
    assert published["status"] == "published"
    assert published["current_published_revision_id"]

    runtime_resp = await client.get(f"/public/apps/{published['slug']}/runtime")
    assert runtime_resp.status_code == 200
    runtime_payload = runtime_resp.json()
    assert runtime_payload["revision_id"] == published["current_published_revision_id"]
    assert runtime_payload["runtime_mode"] == "vite_static"


@pytest.mark.asyncio
async def test_draft_dev_session_preview_url_includes_runtime_context(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Draft Dev Runtime Context App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    async def fake_ensure_session(self, *, app, revision, user_id, files=None, entry_file=None):
        _ = (self, files, entry_file)
        return PublishedAppDraftDevSession(
            id=uuid4(),
            published_app_id=UUID(app_id),
            user_id=user.id,
            revision_id=UUID(draft_revision_id),
            status=PublishedAppDraftDevSessionStatus.running,
            sandbox_id="sandbox-test-1",
            preview_url="https://preview.local/sandbox/sandbox-test-1/?draft_dev_token=draft-dev-token",
            idle_timeout_seconds=180,
            last_activity_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            last_error=None,
        )

    monkeypatch.setattr(PublishedAppDraftDevRuntimeService, "ensure_session", fake_ensure_session)

    ensure_resp = await client.post(
        f"/admin/apps/{app_id}/builder/draft-dev/session/ensure",
        headers=headers,
        json={},
    )
    assert ensure_resp.status_code == 200
    payload = ensure_resp.json()
    preview_url = payload["preview_url"]
    parsed = urlparse(preview_url)
    query = parse_qs(parsed.query)
    assert query["runtime_mode"] == ["builder-preview"]
    runtime_base_path = query["runtime_base_path"][0]
    assert runtime_base_path.endswith(f"/public/apps/preview/revisions/{draft_revision_id}")
    assert "preview_token" not in query
    assert "runtime_preview_token" not in query
    assert payload["preview_auth_token"]
    assert payload["preview_auth_expires_at"]


@pytest.mark.asyncio
async def test_draft_dev_ensure_session_recovers_from_concurrent_scope_insert(db_session, monkeypatch):
    service = PublishedAppDraftDevRuntimeService(db_session)
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    app_id = uuid4()
    revision_id = uuid4()
    files_payload = {"src/main.tsx": "export default function App() { return null; }"}
    dependency_hash = service._dependency_hash(files_payload)

    app = SimpleNamespace(
        id=app_id,
        slug="race-app",
        tenant_id=uuid4(),
        agent_id=uuid4(),
    )
    revision = SimpleNamespace(
        id=revision_id,
        files=files_payload,
        entry_file="src/main.tsx",
    )

    existing_session = PublishedAppDraftDevSession(
        id=uuid4(),
        published_app_id=app_id,
        user_id=user_id,
        revision_id=revision_id,
        status=PublishedAppDraftDevSessionStatus.running,
        sandbox_id="sandbox-existing",
        preview_url="https://preview.local/sandbox/sandbox-existing/",
        idle_timeout_seconds=180,
        last_activity_at=now,
        expires_at=now + timedelta(minutes=3),
        dependency_hash=dependency_hash,
        last_error=None,
    )

    get_session_calls = {"count": 0}

    async def fake_get_session(*, app_id, user_id):
        _ = (app_id, user_id)
        get_session_calls["count"] += 1
        if get_session_calls["count"] == 1:
            return None
        return existing_session

    class _Nested:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    async def fake_expire_idle_sessions(*, app_id=None, user_id=None):
        _ = (app_id, user_id)
        return 0

    async def fake_flush():
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    async def fake_sync_session(**kwargs):
        _ = kwargs
        return None

    monkeypatch.setattr(service, "get_session", fake_get_session)
    monkeypatch.setattr(service, "expire_idle_sessions", fake_expire_idle_sessions)
    monkeypatch.setattr(service.db, "begin_nested", lambda: _Nested())
    monkeypatch.setattr(service.db, "flush", fake_flush)
    monkeypatch.setattr(service.client, "sync_session", fake_sync_session)

    session = await service.ensure_session(
        app=app,
        revision=revision,
        user_id=user_id,
        files=files_payload,
        entry_file="src/main.tsx",
    )

    assert session is existing_session
    assert get_session_calls["count"] >= 2
    assert session.status == PublishedAppDraftDevSessionStatus.running
    assert session.sandbox_id == "sandbox-existing"


@pytest.mark.asyncio
async def test_draft_dev_sync_rejects_when_coding_run_active(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Draft Dev Sync Lock App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    state_payload = state_resp.json()
    current_draft = state_payload["current_draft_revision"]

    ensure_resp = await client.post(
        f"/admin/apps/{app_id}/builder/draft-dev/session/ensure",
        headers=headers,
        json={},
    )
    assert ensure_resp.status_code == 200

    session_result = await db_session.execute(
        select(PublishedAppDraftDevSession).where(
            PublishedAppDraftDevSession.published_app_id == UUID(app_id),
            PublishedAppDraftDevSession.user_id == user.id,
        )
    )
    session = session_result.scalar_one_or_none()
    assert session is not None

    active_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        surface="published_app_coding_agent",
        published_app_id=UUID(app_id),
        base_revision_id=UUID(current_draft["id"]),
        input_params={"context": {"chat_session_id": "session-lock-test"}},
        execution_engine="opencode",
    )
    db_session.add(active_run)
    await db_session.commit()

    sync_resp = await client.patch(
        f"/admin/apps/{app_id}/builder/draft-dev/session/sync",
        headers=headers,
        json={
            "files": current_draft["files"],
            "entry_file": current_draft["entry_file"],
            "revision_id": current_draft["id"],
        },
    )
    assert sync_resp.status_code == 409
    detail = sync_resp.json()["detail"]
    assert detail["code"] == "CODING_AGENT_RUN_ACTIVE"
    assert detail["active_coding_run_count"] >= 1


@pytest.mark.asyncio
async def test_builder_revision_rejects_path_traversal(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Traversal Guard App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "../secrets.ts",
                    "content": "export const leaked = true;",
                }
            ],
        },
    )
    assert revision_resp.status_code == 400
    detail = revision_resp.json()["detail"]
    assert detail["code"] == "BUILDER_PATCH_POLICY_VIOLATION"


@pytest.mark.asyncio
async def test_builder_revision_allows_unrestricted_package_imports(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Import Guard App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/BadImport.tsx",
                    "content": "import axios from \"axios\";\nexport const x = axios;\n",
                }
            ],
        },
    )
    assert revision_resp.status_code == 200
    payload = revision_resp.json()
    assert "src/BadImport.tsx" in payload["files"]


@pytest.mark.asyncio
async def test_builder_validate_endpoint_returns_compile_diagnostics(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Validate API App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    ok_resp = await client.post(
        f"/admin/apps/{app_id}/builder/validate",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/Note.ts",
                    "content": "export const note = \"ok\";",
                }
            ],
        },
    )
    assert ok_resp.status_code == 200
    ok_payload = ok_resp.json()
    assert ok_payload["ok"] is True
    assert ok_payload["file_count"] >= 1

    bad_resp = await client.post(
        f"/admin/apps/{app_id}/builder/validate",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/Broken.ts",
                    "content": "import x from \"https://evil.example.com/x.js\";\nexport default x;\n",
                }
            ],
        },
    )
    assert bad_resp.status_code == 422
    bad_payload = bad_resp.json()["detail"]
    assert bad_payload["code"] == "BUILDER_COMPILE_FAILED"
    assert any("Network import is not allowed" in item["message"] for item in bad_payload["diagnostics"])


@pytest.mark.asyncio
async def test_builder_validate_accepts_vite_root_lock_and_test_config_files(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Vite Root Files App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    validate_resp = await client.post(
        f"/admin/apps/{app_id}/builder/validate",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "pnpm-lock.yaml",
                    "content": "lockfileVersion: '9.0'\n",
                },
                {
                    "op": "upsert_file",
                    "path": "yarn.lock",
                    "content": "# yarn lockfile v1\n",
                },
                {
                    "op": "upsert_file",
                    "path": "vite.config.mts",
                    "content": "export default { base: './' };\n",
                },
                {
                    "op": "upsert_file",
                    "path": "vitest.config.ts",
                    "content": "export default { test: { environment: 'jsdom' } };\n",
                },
                {
                    "op": "upsert_file",
                    "path": "eslint.config.js",
                    "content": "export default [];\n",
                },
                {
                    "op": "upsert_file",
                    "path": "prettier.config.cjs",
                    "content": "module.exports = {};\n",
                },
                {
                    "op": "upsert_file",
                    "path": ".eslintrc.cjs",
                    "content": "module.exports = {};\n",
                },
                {
                    "op": "upsert_file",
                    "path": "playwright.config.ts",
                    "content": "export default {};\n",
                },
            ],
        },
    )
    assert validate_resp.status_code == 200
    payload = validate_resp.json()
    assert payload["ok"] is True
    assert payload["file_count"] >= 8


@pytest.mark.asyncio
async def test_builder_validate_accepts_non_src_public_project_paths(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Broader Paths App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    validate_resp = await client.post(
        f"/admin/apps/{app_id}/builder/validate",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "tests/smoke.spec.ts",
                    "content": "export const smoke = true;\n",
                },
                {
                    "op": "upsert_file",
                    "path": "scripts/helpers.ts",
                    "content": "export const helper = () => 'ok';\n",
                },
            ],
        },
    )
    assert validate_resp.status_code == 200
    payload = validate_resp.json()
    assert payload["ok"] is True
    assert payload["file_count"] >= 2


@pytest.mark.asyncio
async def test_builder_revision_rejects_blocked_generated_paths(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Blocked Paths App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "node_modules/pkg/index.js",
                    "content": "module.exports = {};",
                }
            ],
        },
    )
    assert revision_resp.status_code == 400
    detail = revision_resp.json()["detail"]
    assert detail["code"] == "BUILDER_PATCH_POLICY_VIOLATION"
    assert "blocked by policy" in detail["message"]


@pytest.mark.asyncio
async def test_builder_revision_rejects_oversized_payload(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Oversized Payload App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    too_large = "x" * (BUILDER_MAX_FILE_BYTES + 1)
    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/HugeNote.txt",
                    "content": too_large,
                }
            ],
        },
    )
    assert revision_resp.status_code == 400
    detail = revision_resp.json()["detail"]
    assert detail["code"] == "BUILDER_PATCH_POLICY_VIOLATION"
    assert "File exceeds size limit" in detail["message"]


@pytest.mark.asyncio
async def test_builder_revision_rejects_invalid_rename_source(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Rename Guard App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]

    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": draft_revision_id,
            "operations": [
                {
                    "op": "rename_file",
                    "from_path": "src/DoesNotExist.tsx",
                    "to_path": "src/NewName.tsx",
                }
            ],
        },
    )
    assert revision_resp.status_code == 400
    detail = revision_resp.json()["detail"]
    assert detail["code"] == "BUILDER_PATCH_POLICY_VIOLATION"
    assert "source does not exist" in detail["message"]
