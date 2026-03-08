from __future__ import annotations

from uuid import UUID

import pytest

from app.db.postgres.models.published_apps import PublishedAppDraftDevSession
from app.services import published_app_draft_dev_runtime as runtime_module
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
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    return str(create_resp.json()["id"])


@pytest.mark.asyncio
async def test_failed_start_does_not_persist_placeholder_sandbox_id(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    class _FakeRuntimeClient:
        backend_name = "e2b"

        async def start_session(self, **kwargs):
            _ = kwargs
            raise PublishedAppDraftDevRuntimeClientError("Failed to create E2B sandbox: boom")

        async def sync_session(self, **kwargs):
            _ = kwargs
            raise AssertionError("sync_session should not be called during initial failed start")

        async def heartbeat_session(self, **kwargs):
            _ = kwargs
            return {"status": "running", "sandbox_id": "unused", "runtime_backend": "e2b"}

        async def stop_session(self, **kwargs):
            _ = kwargs
            return {"status": "stopped", "sandbox_id": "unused", "runtime_backend": "e2b"}

        def build_preview_proxy_path(self, session_id: str) -> str:
            return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/"

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: _FakeRuntimeClient()),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Sandbox Failure App")

    ensure_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert ensure_resp.status_code == 200
    payload = ensure_resp.json()
    assert payload["status"] == "error"
    assert "Failed to create E2B sandbox" in str(payload.get("last_error") or "")

    session_row = await db_session.get(PublishedAppDraftDevSession, UUID(payload["session_id"]))
    assert session_row is not None
    assert session_row.sandbox_id in {None, ""}


@pytest.mark.asyncio
async def test_stale_sandbox_id_restarts_cleanly_on_ensure(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    start_calls: list[str] = []
    sync_calls: list[dict[str, object]] = []

    class _FakeRuntimeClient:
        backend_name = "e2b"

        async def start_session(self, **kwargs):
            start_calls.append(str(kwargs["session_id"]))
            sandbox_id = "sandbox-1" if len(start_calls) == 1 else "sandbox-2"
            return {
                "sandbox_id": sandbox_id,
                "status": "running",
                "runtime_backend": "e2b",
                "backend_metadata": {
                    "preview": {
                        "upstream_base_url": f"https://{sandbox_id}.example",
                        "base_path": kwargs["preview_base_path"],
                    }
                },
            }

        async def sync_session(self, **kwargs):
            sync_calls.append(dict(kwargs))
            raise PublishedAppDraftDevRuntimeClientError(
                "Failed to connect to E2B sandbox `2a660e79-8396-4d6d-b77f-59fc1c91a739`: 400: Invalid sandbox ID"
            )

        async def heartbeat_session(self, **kwargs):
            _ = kwargs
            return {"status": "running", "sandbox_id": "unused", "runtime_backend": "e2b"}

        async def stop_session(self, **kwargs):
            _ = kwargs
            return {"status": "stopped", "sandbox_id": "unused", "runtime_backend": "e2b"}

        def build_preview_proxy_path(self, session_id: str) -> str:
            return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/"

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: _FakeRuntimeClient()),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Sandbox Restart App")

    first_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    assert first_payload["status"] == "running"

    second_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["status"] == "running"

    session_row = await db_session.get(PublishedAppDraftDevSession, UUID(second_payload["session_id"]))
    assert session_row is not None
    assert session_row.sandbox_id == "sandbox-2"
    assert len(start_calls) == 2
    assert len(sync_calls) == 1
    assert sync_calls[0]["preview_base_path"] == session_row.preview_url


@pytest.mark.asyncio
async def test_stop_then_reenter_starts_new_runtime(client, db_session, monkeypatch: pytest.MonkeyPatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    start_sandbox_ids = ["sandbox-1", "sandbox-2"]
    stopped_sandbox_ids: list[str] = []

    class _FakeRuntimeClient:
        backend_name = "e2b"

        async def start_session(self, **kwargs):
            sandbox_id = start_sandbox_ids.pop(0)
            return {
                "sandbox_id": sandbox_id,
                "status": "running",
                "runtime_backend": "e2b",
                "backend_metadata": {
                    "preview": {
                        "upstream_base_url": f"https://{sandbox_id}.example",
                        "base_path": kwargs["preview_base_path"],
                    }
                },
            }

        async def sync_session(self, **kwargs):
            return {
                "sandbox_id": kwargs["sandbox_id"],
                "status": "running",
                "runtime_backend": "e2b",
                "backend_metadata": {},
            }

        async def heartbeat_session(self, **kwargs):
            return {
                "sandbox_id": kwargs["sandbox_id"],
                "status": "running",
                "runtime_backend": "e2b",
            }

        async def stop_session(self, **kwargs):
            stopped_sandbox_ids.append(str(kwargs["sandbox_id"]))
            return {"status": "stopped", "sandbox_id": kwargs["sandbox_id"], "runtime_backend": "e2b"}

        def build_preview_proxy_path(self, session_id: str) -> str:
            return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview/"

    monkeypatch.setattr(runtime_module.PublishedAppDraftDevRuntimeService, "_acquire_scope_lock", _noop_scope_lock)
    monkeypatch.setattr(
        runtime_module.PublishedAppDraftDevRuntimeClient,
        "from_env",
        classmethod(lambda cls: _FakeRuntimeClient()),
    )

    app_id = await _create_builder_app(client, headers, str(agent.id), name="Sandbox Reenter App")

    first_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    assert first_payload["status"] == "running"

    delete_resp = await client.delete(f"/admin/apps/{app_id}/builder/draft-dev/session", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "stopped"
    assert stopped_sandbox_ids == ["sandbox-1"]

    second_resp = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["status"] == "running"

    session_row = await db_session.get(PublishedAppDraftDevSession, UUID(second_payload["session_id"]))
    assert session_row is not None
    assert session_row.sandbox_id == "sandbox-2"
