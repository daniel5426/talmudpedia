import uuid

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from main import app


ARTIFACT_CODE = """def execute(inputs, config, context):
    payload = inputs.get("value")
    return {
        "received": payload,
        "config": config,
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


def _mock_dispatch_result(payload):
    value = payload.get("inputs", {}).get("value")
    return {
        "status": "completed",
        "result": {
            "received": value,
            "config": payload.get("config", {}),
            "count": len(value or []),
        },
        "error": None,
        "stdout_excerpt": "artifact stdout",
        "stderr_excerpt": "",
        "duration_ms": 5,
        "worker_id": "cf-worker",
        "dispatch_request_id": "dispatch-1",
        "events": [
            {"event_type": "user_worker_invoked", "payload": {"data": {"worker_name": payload.get("worker_name")}}},
        ],
        "runtime_metadata": {"provider": "cloudflare_workers"},
    }


@pytest.mark.asyncio
async def test_artifact_test_run_endpoints_execute_and_persist_events(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return type(
            "_Deployment",
            (),
            {
                "worker_name": "staging-worker",
                "deployment_id": "dep-1",
                "version_id": "ver-1",
                "build_hash": revision.build_hash,
            },
        )()

    async def fake_execute(self, payload):
        return type("_DispatchResult", (), _mock_dispatch_result(payload))()

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "slug": "runtime_test",
                "display_name": "Runtime Test",
                "description": "artifact runtime test",
                "kind": "rag_operator",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": ARTIFACT_CODE}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {},
                "rag_contract": {
                    "operator_category": "transform",
                    "pipeline_role": "processor",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "execution_mode": "background",
                },
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
            },
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]

        status_response = await client.get(f"/admin/artifact-runs/{run_id}?tenant_slug={tenant.slug}")
        assert status_response.status_code == 200, status_response.text
        run_payload = status_response.json()
        assert run_payload["status"] == "completed"
        assert run_payload["domain"] == "test"
        assert run_payload["queue_class"] == "artifact_test"
        assert run_payload["result_payload"]["count"] == 1
        assert run_payload["result_payload"]["config"] == {"mode": "demo"}
        assert run_payload["runtime_metadata"]["provider"] == "cloudflare_workers"

        events_response = await client.get(f"/admin/artifact-runs/{run_id}/events?tenant_slug={tenant.slug}")
        assert events_response.status_code == 200, events_response.text
        events = events_response.json()["events"]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        event_types = [event["event_type"] for event in events]
        assert "run_prepared" in event_types
        assert "deployment_resolved" in event_types
        assert "dispatch_started" in event_types
        assert "dispatch_finished" in event_types
        assert "user_worker_invoked" in event_types

    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_unsaved_artifact_test_run_uses_principal_tenant_context_without_tenant_slug(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return type(
            "_Deployment",
            (),
            {
                "worker_name": "staging-worker",
                "deployment_id": "dep-1",
                "version_id": "ver-1",
                "build_hash": revision.build_hash,
            },
        )()

    async def fake_execute(self, payload):
        return type("_DispatchResult", (), _mock_dispatch_result(payload))()

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    try:
        run_response = await client.post(
            "/admin/artifacts/test-runs",
            json={
                "source_files": [{"path": "main.py", "content": ARTIFACT_CODE}],
                "entry_module_path": "main.py",
                "input_data": {"value": ["hello"]},
                "config": {"mode": "demo"},
                "dependencies": [],
                "kind": "rag_operator",
                "runtime_target": "cloudflare_workers",
                "config_schema": {},
                "rag_contract": {
                    "operator_category": "transform",
                    "pipeline_role": "processor",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "execution_mode": "background",
                },
            },
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]

        status_response = await client.get(f"/admin/artifact-runs/{run_id}")
        assert status_response.status_code == 200, status_response.text
        run_payload = status_response.json()
        assert run_payload["status"] == "completed"
        assert run_payload["queue_class"] == "artifact_test"
        assert run_payload["result_payload"]["count"] == 1
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_test_run_can_be_cancelled_while_queued(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "0")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "slug": "queued_runtime_test",
                "display_name": "Queued Runtime Test",
                "description": "artifact runtime cancel test",
                "kind": "rag_operator",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": ARTIFACT_CODE}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {},
                "rag_contract": {
                    "operator_category": "transform",
                    "pipeline_role": "processor",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "execution_mode": "background",
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        run_response = await client.post(
            f"/admin/artifacts/{artifact['id']}/test-runs?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "input_data": [{"text": "queued"}],
                "config": {},
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
