import uuid

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from main import app


ARTIFACT_CODE = """def execute(context):
    payload = context.input_data.get("value")
    return {
        "received": payload,
        "config": context.config,
        "count": len(payload or []),
    }
"""


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Artifact Tenant", slug=f"artifact-tenant-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"artifact-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Artifact Org",
        slug=f"artifact-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _override_principal(tenant_id, user):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "scopes": ["artifacts.write"],
            "auth_token": "test-token",
        }

    return _inner


@pytest.mark.asyncio
async def test_artifact_test_run_endpoints_execute_and_persist_events(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")
    monkeypatch.setenv("ARTIFACT_WORKER_CLIENT_MODE", "direct")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "name": "runtime_test",
                "display_name": "Runtime Test",
                "description": "artifact runtime test",
                "category": "custom",
                "scope": "rag",
                "input_type": "raw_documents",
                "output_type": "raw_documents",
                "python_code": ARTIFACT_CODE,
                "config_schema": [],
                "inputs": [],
                "outputs": [],
                "reads": [],
                "writes": [],
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        run_response = await client.post(
            f"/admin/artifacts/{artifact['id']}/test-runs?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "input_data": [{"text": "hello"}],
                "config": {"mode": "demo"},
                "input_type": "raw_documents",
                "output_type": "raw_documents",
            },
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]

        status_response = await client.get(f"/admin/artifact-runs/{run_id}?tenant_slug={tenant.slug}")
        assert status_response.status_code == 200, status_response.text
        run_payload = status_response.json()
        assert run_payload["status"] == "completed"
        assert run_payload["result_payload"]["count"] == 1
        assert run_payload["result_payload"]["config"] == {"mode": "demo"}

        events_response = await client.get(f"/admin/artifact-runs/{run_id}/events?tenant_slug={tenant.slug}")
        assert events_response.status_code == 200, events_response.text
        events = events_response.json()["events"]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        event_types = [event["event_type"] for event in events]
        assert "run_prepared" in event_types
        assert "worker_dispatch_started" in event_types
        assert "revision_loaded" in event_types
        assert "bundle_ready" in event_types
        assert "run_started" in event_types
        assert "run_completed" in event_types

        legacy_response = await client.post(
            f"/admin/artifacts/test?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "python_code": ARTIFACT_CODE,
                "input_data": [{"text": "legacy"}],
                "config": {"legacy": True},
                "input_type": "raw_documents",
                "output_type": "raw_documents",
            },
        )
        assert legacy_response.status_code == 200, legacy_response.text
        legacy_payload = legacy_response.json()
        assert legacy_payload["success"] is True
        assert legacy_payload["run_id"]
        assert legacy_payload["data"]["count"] == 1
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_test_run_can_be_cancelled_while_queued(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "0")
    monkeypatch.setenv("ARTIFACT_WORKER_CLIENT_MODE", "direct")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "name": "queued_runtime_test",
                "display_name": "Queued Runtime Test",
                "description": "artifact runtime cancel test",
                "category": "custom",
                "scope": "rag",
                "input_type": "raw_documents",
                "output_type": "raw_documents",
                "python_code": ARTIFACT_CODE,
                "config_schema": [],
                "inputs": [],
                "outputs": [],
                "reads": [],
                "writes": [],
            },
        )
        artifact = create_response.json()

        run_response = await client.post(
            f"/admin/artifacts/{artifact['id']}/test-runs?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "input_data": [{"text": "queued"}],
                "config": {},
                "input_type": "raw_documents",
                "output_type": "raw_documents",
            },
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]

        cancel_response = await client.post(f"/admin/artifact-runs/{run_id}/cancel?tenant_slug={tenant.slug}")
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["status"] == "cancelled"

        status_response = await client.get(f"/admin/artifact-runs/{run_id}?tenant_slug={tenant.slug}")
        assert status_response.status_code == 200, status_response.text
        assert status_response.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
