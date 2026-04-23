from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlparse
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, User
from app.db.postgres.models.published_apps import PublishedAppDraftDevSession, PublishedAppDraftWorkspace
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClient
from app.services.security_bootstrap_service import SecurityBootstrapService
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


def _sprite_api_token() -> str:
    token = (
        (os.getenv("APPS_SPRITE_API_TOKEN") or "").strip()
        or (os.getenv("SPRITES_TOKEN") or "").strip()
        or (os.getenv("SPRITE_API_TOKEN") or "").strip()
    )
    assert token, "Sprite live tests require APPS_SPRITE_API_TOKEN (or SPRITES_TOKEN)."
    return token


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
    assert create_resp.status_code == 200, create_resp.text
    return str(create_resp.json()["id"])


async def _seed_second_owner(db_session, *, organization_id, org_unit_id) -> User:
    user = User(
        email=f"sprite-owner-{uuid4().hex[:8]}@example.com",
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


async def _poll_preview(client, preview_url: str, preview_auth_token: str, *, attempts: int = 12):
    last_response = None
    for _ in range(attempts):
        response = await client.get(
            preview_url,
            params={"runtime_token": preview_auth_token},
            follow_redirects=True,
            timeout=10.0,
        )
        last_response = response
        if response.status_code == 200 and response.text.strip():
            return response
    assert last_response is not None
    return last_response


def _preview_auth_token_from_url(preview_url: str) -> str:
    parsed = urlparse(str(preview_url or ""))
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    token = str(params.get("runtime_token") or "").strip()
    assert token, preview_url
    return token


async def _sprite_request(method: str, sprite_name: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method,
            f"{(os.getenv('APPS_SPRITE_API_BASE_URL') or 'https://api.sprites.dev').rstrip('/')}/v1/sprites/{sprite_name}",
            headers={"Authorization": f"Bearer {_sprite_api_token()}"},
        )
    return response


@pytest.mark.asyncio
async def test_sprite_live_builder_preview_and_recovery(client, db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "sprite")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "0")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "0")
    _sprite_api_token()

    tenant, user_a, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    user_b = await _seed_second_owner(db_session, organization_id=tenant.id, org_unit_id=org_unit.id)
    headers_a = admin_headers(str(user_a.id), str(tenant.id), str(org_unit.id))
    headers_b = admin_headers(str(user_b.id), str(tenant.id), str(org_unit.id))

    app_id = await _create_builder_app(client, headers_a, str(agent.id), name=f"Live Sprite Smoke {uuid4().hex[:6]}")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_a)
    assert ensure_resp.status_code == 200, ensure_resp.text
    payload = ensure_resp.json()
    assert payload["status"] == "serving", payload
    assert payload["runtime_backend"] == "sprite"
    assert payload.get("preview_url")
    preview_auth_token = _preview_auth_token_from_url(str(payload["preview_url"]))

    first_session = await db_session.get(PublishedAppDraftDevSession, UUID(payload["session_id"]))
    assert first_session is not None
    sprite_name = str(first_session.sandbox_id or "").strip()
    assert sprite_name

    preview_resp = await _poll_preview(client, str(payload["preview_url"]), preview_auth_token)
    assert preview_resp.status_code == 200
    assert "<!doctype html" in preview_resp.text.lower() or "<html" in preview_resp.text.lower()
    assert f"/public/apps-builder/draft-dev/sessions/{payload['session_id']}/preview/@vite/client" in preview_resp.text
    assert f"/public/apps-builder/draft-dev/sessions/{payload['session_id']}/preview/src/main.tsx" in preview_resp.text

    vite_client_resp = await client.get(
        f"{payload['preview_url']}@vite/client",
        params={"runtime_token": preview_auth_token},
        follow_redirects=True,
        timeout=20.0,
    )
    assert vite_client_resp.status_code == 200
    assert "import" in vite_client_resp.text

    ensure_b_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_b)
    assert ensure_b_resp.status_code == 200, ensure_b_resp.text
    payload_b = ensure_b_resp.json()
    assert payload_b["status"] == "serving"

    second_session = await db_session.get(PublishedAppDraftDevSession, UUID(payload_b["session_id"]))
    assert second_session is not None
    assert str(second_session.sandbox_id) == sprite_name

    runtime_client = PublishedAppDraftDevRuntimeClient.from_env()
    marker_path = f"src/sprite-live-marker-{uuid4().hex[:6]}.txt"
    marker_content = datetime.now(timezone.utc).isoformat()
    write_result = await runtime_client.write_file(
        sandbox_id=sprite_name,
        path=marker_path,
        content=marker_content,
    )
    assert write_result["path"] == marker_path
    marker_result = await runtime_client.read_file(sandbox_id=sprite_name, path=marker_path)
    assert marker_result["content"] == marker_content

    stop_a_resp = await client.delete(f"/admin/apps/{app_id}/builder/draft-dev/session", headers=headers_a)
    assert stop_a_resp.status_code == 200, stop_a_resp.text
    assert stop_a_resp.json()["status"] == "stopped"

    reattach_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_a)
    assert reattach_resp.status_code == 200, reattach_resp.text
    reattach_payload = reattach_resp.json()
    assert reattach_payload["status"] == "serving"
    assert reattach_payload["runtime_backend"] == "sprite"

    refreshed_session = await db_session.get(PublishedAppDraftDevSession, UUID(reattach_payload["session_id"]))
    assert refreshed_session is not None
    assert str(refreshed_session.sandbox_id) == sprite_name

    delete_provider_resp = await _sprite_request("DELETE", sprite_name)
    assert delete_provider_resp.status_code in {200, 204, 404}

    recovered_payload = None
    for attempt in range(4):
        recovered_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_a)
        assert recovered_resp.status_code == 200, recovered_resp.text
        recovered_payload = recovered_resp.json()
        if recovered_payload["status"] == "serving":
            break
        if attempt < 3:
            await asyncio.sleep(1.0)
    assert recovered_payload is not None
    if recovered_payload["status"] != "serving":
        recovered_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers_a)
        assert recovered_resp.status_code == 200, recovered_resp.text
        recovered_payload = recovered_resp.json()
    assert recovered_payload["status"] == "serving", recovered_payload

    recovered_session = await db_session.get(PublishedAppDraftDevSession, UUID(recovered_payload["session_id"]))
    assert recovered_session is not None
    assert str(recovered_session.sandbox_id) == sprite_name

    recovered_preview_resp = await _poll_preview(
        client,
        str(recovered_payload["preview_url"]),
        _preview_auth_token_from_url(str(recovered_payload["preview_url"])),
    )
    assert recovered_preview_resp.status_code == 200

    workspace = await db_session.scalar(
        select(PublishedAppDraftWorkspace).where(PublishedAppDraftWorkspace.published_app_id == UUID(app_id))
    )
    assert workspace is not None
    assert str(workspace.sandbox_id) == sprite_name

    delete_app_resp = await client.delete(f"/admin/apps/{app_id}", headers=headers_a)
    assert delete_app_resp.status_code == 200, delete_app_resp.text

    exists_after_delete = await _sprite_request("GET", sprite_name)
    assert exists_after_delete.status_code == 404
