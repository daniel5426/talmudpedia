from __future__ import annotations

import os
from uuid import UUID

import pytest

from app.db.postgres.models.published_apps import PublishedAppDraftDevSession
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent

pytestmark = pytest.mark.skipif(
    not (os.getenv("TEST_E2B_LIVE") == "1" and (os.getenv("E2B_API_KEY") or "").strip()),
    reason="TEST_E2B_LIVE=1 and E2B_API_KEY are required for live E2B smoke tests.",
)


async def _create_builder_app(client, headers: dict[str, str], agent_id: str, *, name: str) -> str:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": name,
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    return str(create_resp.json()["id"])


async def _poll_preview(client, preview_url: str, preview_auth_token: str, *, attempts: int = 30):
    last_response = None
    for _ in range(attempts):
        response = await client.get(
            preview_url,
            params={"runtime_token": preview_auth_token},
            follow_redirects=True,
        )
        last_response = response
        if response.status_code == 200 and response.text.strip():
            return response
    assert last_response is not None
    return last_response


@pytest.mark.asyncio
async def test_e2b_live_builder_preview_smoke(client, db_session, monkeypatch: pytest.MonkeyPatch):
    from e2b import AsyncSandbox
    from e2b.sandbox.sandbox_api import SandboxQuery

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Live E2B Smoke App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200, ensure_resp.text
    payload = ensure_resp.json()
    assert payload["status"] == "serving", payload
    assert payload["runtime_backend"] == "e2b"
    assert payload.get("preview_url")
    assert payload.get("preview_auth_token")

    session_row = await db_session.get(PublishedAppDraftDevSession, UUID(payload["session_id"]))
    assert session_row is not None
    sandbox_id = str(session_row.sandbox_id or "").strip()
    assert sandbox_id

    preview_resp = await _poll_preview(
        client,
        str(payload["preview_url"]),
        str(payload["preview_auth_token"]),
    )
    assert preview_resp.status_code == 200
    assert "<!doctype html" in preview_resp.text.lower() or "<html" in preview_resp.text.lower()

    vite_client_resp = await client.get(
        f"{payload['preview_url']}@vite/client",
        params={"runtime_token": str(payload["preview_auth_token"])},
        follow_redirects=True,
    )
    assert vite_client_resp.status_code == 200
    assert "import" in vite_client_resp.text

    sandbox = await AsyncSandbox.connect(sandbox_id=sandbox_id, timeout=60)
    await sandbox.kill()

    recovered_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert recovered_resp.status_code == 200, recovered_resp.text
    recovered = recovered_resp.json()
    assert recovered["status"] == "serving", recovered

    refreshed_row = await db_session.get(PublishedAppDraftDevSession, UUID(payload["session_id"]))
    assert refreshed_row is not None
    assert str(refreshed_row.sandbox_id or "").strip()
    assert str(refreshed_row.sandbox_id) != sandbox_id

    paginator = AsyncSandbox.list(
        query=SandboxQuery(metadata={"session_id": str(payload["session_id"])}),
        limit=20,
    )
    session_sandboxes = await paginator.next_items()
    live_sandbox_ids = [str(getattr(item, "sandbox_id", "") or "").strip() for item in session_sandboxes or [] if str(getattr(item, "sandbox_id", "") or "").strip()]
    assert live_sandbox_ids == [str(refreshed_row.sandbox_id)]

    recovered_preview_resp = await _poll_preview(
        client,
        str(recovered["preview_url"]),
        str(recovered["preview_auth_token"]),
    )
    assert recovered_preview_resp.status_code == 200

    stop_resp = await client.delete(f"/admin/apps/{app_id}/builder/draft-dev/session", headers=headers)
    assert stop_resp.status_code == 200, stop_resp.text
    assert stop_resp.json()["status"] == "stopped"

    paginator = AsyncSandbox.list(
        query=SandboxQuery(metadata={"session_id": str(payload["session_id"])}),
        limit=20,
    )
    remaining = await paginator.next_items()
    remaining_sandbox_ids = [str(getattr(item, "sandbox_id", "") or "").strip() for item in remaining or [] if str(getattr(item, "sandbox_id", "") or "").strip()]
    assert remaining_sandbox_ids == []
