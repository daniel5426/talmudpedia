import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.artifact_runtime import ArtifactRun, ArtifactRunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.artifact_runtime.cloudflare_dispatch_client import CloudflareDispatchHTTPError
from app.services.artifact_runtime.policy_service import ArtifactConcurrencyLimitExceeded
from app.services.security_bootstrap_service import SecurityBootstrapService
from main import app


ARTIFACT_CODE = """def execute(inputs, config, context):
    payload = inputs
    return {
        "received": payload,
        "config": config,
        "count": len(payload or []),
    }
"""


async def _seed_tenant_context(db_session):
    tenant = Organization(id=uuid.uuid4(), name="Artifact Organization", slug=f"artifact-tenant-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"artifact-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="Artifact Org",
        slug=f"artifact-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=tenant.id,
        user_id=user.id,
        assigned_by=user.id,
    )
    await db_session.commit()
    return tenant, user


def _override_principal(organization_id, user):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "organization_id": str(organization_id),
            "scopes": ["artifacts.write"],
            "auth_token": "test-token",
        }

    return _inner


async def _seed_artifact_revision(db_session, *, organization_id, created_by):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        organization_id=organization_id,
        created_by=created_by,
        display_name="Runtime Fixture Artifact",
        description="fixture artifact revision",
        kind="rag_operator",
        source_files=[{"path": "main.py", "content": ARTIFACT_CODE}],
        entry_module_path="main.py",
        language="python",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={},
        config_schema={},
        rag_contract={
            "operator_category": "transform",
            "pipeline_role": "processor",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "execution_mode": "background",
        },
    )
    await db_session.commit()
    return artifact.latest_draft_revision_id


def _mock_dispatch_result(payload):
    value = payload.get("inputs")
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

    async def fake_ensure_deployment(self, *, revision, namespace, organization_id=None):
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

    async def fake_ensure_deployment(self, *, revision, namespace, organization_id=None):
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
                "input_data": ["hello"],
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
async def test_unsaved_artifact_test_run_returns_clean_execute_contract_error(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        run_response = await client.post(
            "/admin/artifacts/test-runs",
            json={
                "source_files": [{"path": "main.js", "content": "async function execute(inputs, config, context) { return { ok: true }; }\n"}],
                "entry_module_path": "main.js",
                "input_data": {"hello": "world"},
                "config": {},
                "dependencies": [],
                "language": "javascript",
                "kind": "tool_impl",
                "runtime_target": "cloudflare_workers",
                "config_schema": {},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            },
        )
        assert run_response.status_code == 422, run_response.text
        assert run_response.json()["detail"] == {
            "code": "VALIDATION_ERROR",
            "message": "Artifact entry module main.js must export execute(inputs, config, context)",
            "http_status": 422,
            "retryable": False,
        }
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_test_run_can_be_cancelled_while_queued(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "0")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_enqueue_run(self, run_id):
        return None

    monkeypatch.setattr(
        "app.services.artifact_runtime.execution_service.ArtifactExecutionService.enqueue_run",
        fake_enqueue_run,
    )

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
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


@pytest.mark.asyncio
async def test_artifact_runtime_status_endpoint_reports_active_count_and_limit(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        revision_id = await _seed_artifact_revision(db_session, organization_id=tenant.id, created_by=user.id)
        stale_safe_started_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        run = ArtifactRun(
            organization_id=tenant.id,
            revision_id=revision_id,
            domain="test",
            status=ArtifactRunStatus.RUNNING,
            queue_class="artifact_test",
            started_at=stale_safe_started_at,
            created_at=stale_safe_started_at,
            runtime_metadata={},
        )
        db_session.add(run)
        await db_session.commit()

        response = await client.get(f"/admin/artifact-runs/runtime-status?tenant_slug={tenant.slug}")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload == {
            "queue_class": "artifact_test",
            "active_count": 1,
            "concurrency_limit": 10,
        }
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_unsaved_artifact_test_run_returns_429_when_capacity_is_exhausted(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def deny_capacity(self, *, organization_id, queue_class):
        raise ArtifactConcurrencyLimitExceeded(
            queue_class=queue_class,
            active_count=10,
            concurrency_limit=10,
        )

    monkeypatch.setattr(
        "app.services.artifact_runtime.policy_service.ArtifactRuntimePolicyService.assert_capacity",
        deny_capacity,
    )

    try:
        response = await client.post(
            "/admin/artifacts/test-runs",
            json={
                "source_files": [{"path": "main.py", "content": ARTIFACT_CODE}],
                "entry_module_path": "main.py",
                "input_data": ["hello"],
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
        assert response.status_code == 429, response.text
        assert response.json()["detail"] == {
            "code": "RATE_LIMITED",
            "message": "Organization concurrency limit reached for artifact_test: 10/10",
            "http_status": 429,
            "retryable": False,
        }
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_unsaved_artifact_test_run_returns_failed_run_payload_when_eager_dispatch_crashes(client, db_session, monkeypatch):
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_ensure_deployment(self, *, revision, namespace, organization_id=None):
        return type(
            "_Deployment",
            (),
            {
                "worker_name": "staging-worker",
                "deployment_id": "dep-500",
                "version_id": "ver-500",
                "build_hash": revision.build_hash,
            },
        )()

    async def fake_execute(self, payload):
        raise CloudflareDispatchHTTPError(
            status_code=500,
            message="Dispatch worker returned HTTP 500 for https://artifact-test-runtime.example/execute: worker crashed",
            response_text='{"detail":{"code":"WORKER_CRASH","message":"worker crashed","traceback":"boom"}}',
            response_json={"detail": {"code": "WORKER_CRASH", "message": "worker crashed", "traceback": "boom"}},
            url="https://artifact-test-runtime.example/execute",
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    try:
        response = await client.post(
            "/admin/artifacts/test-runs",
            json={
                "source_files": [{"path": "main.py", "content": ARTIFACT_CODE}],
                "entry_module_path": "main.py",
                "input_data": ["hello"],
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
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]

        status_response = await client.get(f"/admin/artifact-runs/{run_id}")
        assert status_response.status_code == 200, status_response.text
        run_payload = status_response.json()
        assert run_payload["status"] == "failed"
        assert run_payload["error_payload"]["code"] == "CLOUDFLARE_DISPATCH_HTTP_ERROR"
        assert run_payload["error_payload"]["dispatch_detail"]["code"] == "WORKER_CRASH"

        events_response = await client.get(f"/admin/artifact-runs/{run_id}/events")
        assert events_response.status_code == 200, events_response.text
        event_types = [event["event_type"] for event in events_response.json()["events"]]
        assert "dispatch_finished" in event_types
        assert "dispatch_request_debug" in event_types
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
