import io
import json
import zipfile

import pytest

from app.db.postgres.models.published_apps import (
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppDraftWorkspace,
    PublishedAppDraftWorkspaceStatus,
)
from ._helpers import admin_headers, seed_admin_tenant_and_agent


def _read_zip_file(payload: bytes, path: str) -> str:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        return archive.read(path).decode("utf-8")


@pytest.mark.asyncio
async def test_admin_export_options_and_archive_use_draft_revision_source(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Exportable App",
            "slug": "exportable-app",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app = create_resp.json()

    options_resp = await client.get(f"/admin/apps/{app['id']}/export/options", headers=headers)
    assert options_resp.status_code == 200
    assert options_resp.json() == {
        "supported": True,
        "ready": True,
        "template_key": "classic-chat",
        "source_kind": "draft_revision",
        "default_archive_name": "exportable-app-standalone-export.zip",
        "reason": None,
    }

    archive_resp = await client.post(f"/admin/apps/{app['id']}/export/archive", headers=headers, json={})
    assert archive_resp.status_code == 200
    assert archive_resp.headers["content-type"] == "application/zip"
    assert archive_resp.headers["x-export-source-kind"] == "draft_revision"
    assert "exportable-app-standalone-export.zip" in archive_resp.headers["content-disposition"]

    package_payload = json.loads(_read_zip_file(archive_resp.content, "package.json"))
    assert package_payload["dependencies"]["@agents24/embed-sdk"] == "file:../packages/embed-sdk"
    assert "@talmudpedia/runtime-sdk" not in package_payload["dependencies"]
    assert package_payload["scripts"]["dev"] == 'concurrently -k "pnpm dev:api" "pnpm dev:client"'

    runtime_sdk = _read_zip_file(archive_resp.content, "src/runtime-sdk.ts")
    assert 'fetch("/api/agent/chat/stream"' in runtime_sdk

    readme = _read_zip_file(archive_resp.content, "README.md")
    assert "Last Updated: 2026-03-22" in readme


@pytest.mark.asyncio
async def test_admin_export_archive_prefers_live_workspace_snapshot(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Live Snapshot App",
            "slug": "live-snapshot-app",
            "agent_id": str(agent.id),
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app = create_resp.json()

    state_resp = await client.get(f"/admin/apps/{app['id']}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    revision_id = state_resp.json()["current_draft_revision"]["id"]

    workspace = PublishedAppDraftWorkspace(
        published_app_id=app["id"],
        revision_id=revision_id,
        status=PublishedAppDraftWorkspaceStatus.serving,
        sprite_name="export-test-sprite",
        backend_metadata={
            "live_workspace_snapshot": {
                "revision_id": revision_id,
                "entry_file": "src/main.tsx",
                "files": {
                    "src/export-marker.ts": 'export const EXPORT_MARKER = "live-workspace";\n',
                },
                "updated_at": "2026-03-22T12:00:00Z",
            }
        },
    )
    db_session.add(workspace)
    await db_session.flush()

    session = PublishedAppDraftDevSession(
        published_app_id=app["id"],
        user_id=user.id,
        revision_id=revision_id,
        draft_workspace_id=workspace.id,
        status=PublishedAppDraftDevSessionStatus.running,
    )
    db_session.add(session)
    await db_session.commit()

    options_resp = await client.get(f"/admin/apps/{app['id']}/export/options", headers=headers)
    assert options_resp.status_code == 200
    assert options_resp.json()["source_kind"] == "live_workspace_snapshot"

    archive_resp = await client.post(f"/admin/apps/{app['id']}/export/archive", headers=headers, json={})
    assert archive_resp.status_code == 200
    assert archive_resp.headers["x-export-source-kind"] == "live_workspace_snapshot"
    assert _read_zip_file(archive_resp.content, "src/export-marker.ts") == 'export const EXPORT_MARKER = "live-workspace";\n'
