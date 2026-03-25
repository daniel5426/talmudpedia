import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.postgres.models.artifact_runtime import ArtifactRun, ArtifactRunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.handler_runner import invoke_artifact_handler
from app.services.artifact_runtime.cloudflare_dispatch_client import CloudflareDispatchHTTPError
from app.services.artifact_runtime.policy_service import ArtifactConcurrencyLimitExceeded, ArtifactRuntimePolicyService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Runtime Tenant", slug=f"runtime-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"runtime-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Runtime Org",
        slug=f"runtime-org-{uuid.uuid4().hex[:6]}",
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


async def _create_artifact(db_session, tenant_id, created_by, *, publish: bool, kind: str):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant_id,
        created_by=created_by,
        display_name="Runtime Artifact",
        description=None,
        kind=kind,
        language="python",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True, 'input': inputs}\n"}],
        entry_module_path="main.py",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={},
        agent_contract={"state_reads": [], "state_writes": [], "input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "node_ui": {}} if kind == "agent_node" else None,
        rag_contract={"operator_category": "transform", "pipeline_role": "retrieval", "input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "execution_mode": "background"} if kind == "rag_operator" else None,
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}} if kind == "tool_impl" else None,
    )
    if publish:
        await revisions.publish_latest_draft(artifact)
    await db_session.commit()
    return artifact


@pytest.mark.asyncio
async def test_execute_live_run_records_domain_queue_and_raw_inputs(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="agent_node")

    captured = {}

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        captured["deployment"] = {"revision_id": revision.id, "namespace": namespace, "tenant_id": tenant_id}
        return SimpleNamespace(
            worker_name="cf-worker",
            deployment_id="dep-1",
            version_id="ver-1",
            build_hash=revision.build_hash,
        )

    async def fake_execute(self, payload):
        captured["request"] = payload
        return SimpleNamespace(
            status="completed",
            result={"echo": payload["inputs"]},
            error=None,
            stdout_excerpt="",
            stderr_excerpt="",
            duration_ms=7,
            worker_id="cf-worker",
            sandbox_session_id="dispatch-1",
            events=[{"event_type": "user_worker_invoked", "payload": {"data": {"worker": "cf-worker"}}}],
            runtime_metadata={"provider": "cloudflare_workers"},
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    service = ArtifactExecutionService(db_session)
    run = await service.execute_live_run(
        tenant_id=tenant.id,
        created_by=user.id,
        revision_id=artifact.latest_published_revision_id,
        domain="agent",
        queue_class="artifact_prod_interactive",
        input_payload=["raw", {"nested": True}],
        config_payload={"mode": "live"},
        context_payload={"source": "test"},
    )

    assert run is not None
    assert str(getattr(run.domain, "value", run.domain)) == "agent"
    assert run.queue_class == "artifact_prod_interactive"
    assert captured["deployment"]["namespace"] == "production"
    assert captured["deployment"]["tenant_id"] == tenant.id
    assert captured["request"]["inputs"] == ["raw", {"nested": True}]
    assert run.result_payload == {"echo": ["raw", {"nested": True}]}
    assert run.runtime_metadata["provider"] == "cloudflare_workers"


@pytest.mark.asyncio
async def test_execute_live_run_injects_context_credentials_and_uses_deployed_code(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="tool_impl")
    captured = {}

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="artifact-revision-inline",
            deployment_id="dep-inline",
            version_id="ver-inline",
            build_hash=revision.build_hash,
        )

    async def fake_execute(self, payload):
        captured["request"] = payload
        return SimpleNamespace(
            status="completed",
            result={"echo": payload["inputs"]},
            error=None,
            stdout_excerpt="",
            stderr_excerpt="",
            duration_ms=4,
            worker_id="artifact-revision-inline",
            sandbox_session_id="dispatch-inline",
            events=[],
            runtime_metadata={"provider": "cloudflare_workers"},
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    service = ArtifactExecutionService(db_session)
    run = await service.execute_live_run(
        tenant_id=tenant.id,
        created_by=user.id,
        revision_id=artifact.latest_published_revision_id,
        domain="tool",
        queue_class="artifact_prod_interactive",
        input_payload={"hello": "world"},
        config_payload={"mode": "test"},
        context_payload={},
    )

    assert run is not None
    assert "entry_module_path" not in captured["request"]
    assert "source_files" not in captured["request"]
    assert captured["request"]["context"]["credentials"] == {}


@pytest.mark.asyncio
async def test_execute_live_run_passes_execution_tenant_for_system_revision(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=None,
        created_by=None,
        display_name="System Runtime Artifact",
        description=None,
        kind="tool_impl",
        owner_type="system",
        system_key=f"system-runtime-{uuid.uuid4().hex[:6]}",
        language="python",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
        entry_module_path="main.py",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={},
        config_schema={},
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    )
    await revisions.publish_latest_draft(artifact)
    await db_session.commit()

    captured = {}

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        captured["tenant_id"] = tenant_id
        captured["revision_tenant_id"] = revision.tenant_id
        return SimpleNamespace(
            worker_name="cf-worker",
            deployment_id="dep-system",
            version_id="ver-system",
            build_hash=revision.build_hash,
        )

    async def fake_execute(self, payload):
        return SimpleNamespace(
            status="completed",
            result={"ok": True},
            error=None,
            stdout_excerpt="",
            stderr_excerpt="",
            duration_ms=3,
            worker_id="cf-worker",
            sandbox_session_id="dispatch-system",
            events=[],
            runtime_metadata={"provider": "cloudflare_workers"},
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    run = await ArtifactExecutionService(db_session).execute_live_run(
        tenant_id=tenant.id,
        created_by=user.id,
        revision_id=artifact.latest_published_revision_id,
        domain="tool",
        queue_class="artifact_prod_interactive",
        input_payload={"value": 1},
        config_payload={},
        context_payload={},
    )

    assert run is not None
    assert captured["revision_tenant_id"] is None
    assert captured["tenant_id"] == tenant.id


@pytest.mark.asyncio
async def test_execute_live_run_background_routes_to_requested_queue(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="rag_operator")
    captured = {}

    def fake_apply_async(*, args, queue):
        captured["args"] = args
        captured["queue"] = queue

    async def fake_wait(self, run_id, *, timeout_seconds=30.0):
        return await self._runs.get_run(run_id=run_id)

    monkeypatch.setattr("app.workers.artifact_tasks.execute_artifact_run_task.apply_async", fake_apply_async)
    monkeypatch.setattr(ArtifactExecutionService, "wait_for_terminal_state", fake_wait)
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "0")

    service = ArtifactExecutionService(db_session)
    run = await service.execute_live_run(
        tenant_id=tenant.id,
        created_by=user.id,
        revision_id=artifact.latest_published_revision_id,
        domain="rag",
        queue_class="artifact_prod_background",
        input_payload={"query": "test"},
        config_payload={},
        context_payload={},
    )

    assert run is not None
    assert str(getattr(run.domain, "value", run.domain)) == "rag"
    assert run.queue_class == "artifact_prod_background"
    assert captured["queue"] == "artifact_prod_background"
    assert captured["args"] == [str(run.id)]


@pytest.mark.asyncio
async def test_execute_live_run_rejects_unpublished_revision_for_live_domains(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=False, kind="tool_impl")

    service = ArtifactExecutionService(db_session)
    with pytest.raises(PermissionError):
        await service.execute_live_run(
            tenant_id=tenant.id,
            created_by=user.id,
            revision_id=artifact.latest_draft_revision_id,
            domain="tool",
            queue_class="artifact_prod_interactive",
            input_payload={"value": 1},
            config_payload={},
            context_payload={},
        )


@pytest.mark.asyncio
async def test_interactive_run_fails_fast_when_tenant_capacity_is_exhausted(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="agent_node")

    async def deny_capacity(self, *, tenant_id, queue_class):
        raise ArtifactConcurrencyLimitExceeded(
            queue_class=queue_class,
            active_count=5,
            concurrency_limit=5,
        )

    monkeypatch.setattr(
        "app.services.artifact_runtime.policy_service.ArtifactRuntimePolicyService.assert_capacity",
        deny_capacity,
    )

    service = ArtifactExecutionService(db_session)
    with pytest.raises(ArtifactConcurrencyLimitExceeded):
        await service.execute_live_run(
            tenant_id=tenant.id,
            created_by=user.id,
            revision_id=artifact.latest_published_revision_id,
            domain="agent",
            queue_class="artifact_prod_interactive",
            input_payload={"value": 1},
            config_payload={},
            context_payload={},
        )


@pytest.mark.asyncio
async def test_test_queue_defaults_to_concurrency_limit_10(db_session):
    tenant, _user = await _seed_tenant_context(db_session)

    snapshot = await ArtifactRuntimePolicyService(db_session).get_snapshot(
        tenant_id=tenant.id,
        queue_class="artifact_test",
    )

    assert snapshot.concurrency_limit == 10


@pytest.mark.asyncio
async def test_policy_service_reconciles_stale_artifact_test_runs(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="tool_impl")
    stale_started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale_run = ArtifactRun(
        tenant_id=tenant.id,
        artifact_id=artifact.id,
        revision_id=artifact.latest_published_revision_id,
        domain="test",
        status=ArtifactRunStatus.RUNNING,
        queue_class="artifact_test",
        started_at=stale_started_at,
        created_at=stale_started_at,
        runtime_metadata={},
    )
    db_session.add(stale_run)
    await db_session.commit()

    status = await ArtifactRuntimePolicyService(db_session).get_queue_status(
        tenant_id=tenant.id,
        queue_class="artifact_test",
    )
    await db_session.commit()

    refreshed_run = await db_session.get(ArtifactRun, stale_run.id)
    assert status.active_count == 0
    assert status.concurrency_limit == 10
    assert refreshed_run is not None
    assert refreshed_run.status == ArtifactRunStatus.FAILED
    assert refreshed_run.error_payload["code"] == "STALE_ARTIFACT_TEST_RUN_RECONCILED"
    assert refreshed_run.runtime_metadata["stale_reconciled"] is True


@pytest.mark.asyncio
async def test_execute_live_run_persists_worker_http_500_details(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="tool_impl")

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="artifact-free-plan-runtime",
            deployment_id="dep-500",
            version_id="ver-500",
            build_hash=revision.build_hash,
        )

    async def fake_execute(self, payload):
        raise CloudflareDispatchHTTPError(
            status_code=500,
            message="Dispatch worker returned HTTP 500 for https://artifact-free-plan-runtime.example/execute: worker crashed",
            response_text='{"detail":{"code":"WORKER_CRASH","message":"worker crashed","traceback":"boom"}}',
            response_json={"detail": {"code": "WORKER_CRASH", "message": "worker crashed", "traceback": "boom"}},
            url="https://artifact-free-plan-runtime.example/execute",
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    with pytest.raises(CloudflareDispatchHTTPError):
        await ArtifactExecutionService(db_session).execute_live_run(
            tenant_id=tenant.id,
            created_by=user.id,
            revision_id=artifact.latest_published_revision_id,
            domain="tool",
            queue_class="artifact_prod_interactive",
            input_payload={"hello": "world"},
            config_payload={},
            context_payload={},
        )

    result = await db_session.execute(
        select(ArtifactRun).where(ArtifactRun.tenant_id == tenant.id).order_by(ArtifactRun.created_at.desc())
    )
    failed_run = next(run for run in result.scalars().all() if str(getattr(run.status, "value", run.status)) == "failed")
    assert failed_run.error_payload["code"] == "CLOUDFLARE_DISPATCH_HTTP_ERROR"
    assert failed_run.error_payload["http_status"] == 500
    assert failed_run.error_payload["dispatch_detail"]["code"] == "WORKER_CRASH"
    assert "worker crashed" in failed_run.error_payload["message"]


def test_dispatch_http_error_promotes_nested_upstream_root_cause():
    error = CloudflareDispatchHTTPError(
        status_code=500,
        message="Dispatch worker returned HTTP 500 for https://artifact.example/execute: Dispatched worker returned an error response.",
        response_text=(
            '{"detail":{"code":"DISPATCH_UPSTREAM_ERROR","message":"Dispatched worker returned an error response.",'
            '"upstream_detail":{"code":"WORKER_MODULE_LOAD_FAILED","message":"No module named missing_package",'
            '"traceback":"Traceback..."}}}'
        ),
        response_json={
            "detail": {
                "code": "DISPATCH_UPSTREAM_ERROR",
                "message": "Dispatched worker returned an error response.",
                "upstream_detail": {
                    "code": "WORKER_MODULE_LOAD_FAILED",
                    "message": "No module named missing_package",
                    "traceback": "Traceback...",
                },
            }
        },
        url="https://artifact.example/execute",
    )

    payload = error.to_error_payload()

    assert payload["dispatch_detail"]["code"] == "DISPATCH_UPSTREAM_ERROR"
    assert payload["dispatch_root_cause"]["code"] == "WORKER_MODULE_LOAD_FAILED"
    assert payload["dispatch_root_cause"]["message"] == "No module named missing_package"


@pytest.mark.asyncio
async def test_handler_runner_requires_modern_three_argument_contract():
    async def execute(single_arg):
        return {"input": single_arg}

    with pytest.raises(TypeError, match="exactly \\(inputs, config, context\\)"):
        await invoke_artifact_handler(execute, ["a", {"b": 1}], {"mode": "strict"}, {"domain": "rag"})


@pytest.mark.asyncio
async def test_execute_live_run_rewrites_runtime_credentials_without_persisting_secrets(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    credential = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Runtime",
        credentials={"api_key": "super-secret-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.flush()

    artifact = await ArtifactRevisionService(db_session).create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        display_name="Bound Runtime Artifact",
        description=None,
        kind="tool_impl",
        source_files=[{"path": "main.py", "content": f'def execute(inputs, config, context):\n    client = OpenAI(api_key=\"@{{{credential.id}}}\")\n    return {{"ok": True}}\n'}],
        entry_module_path="main.py",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True, "allowed_hosts": []},
        config_schema={},
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    )
    await ArtifactRevisionService(db_session).publish_latest_draft(artifact)
    await db_session.commit()

    captured = {}

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="cf-worker",
            deployment_id="dep-bound",
            version_id="ver-bound",
            build_hash=revision.build_hash,
        )

    async def fake_execute(self, payload):
        captured["request"] = payload
        return SimpleNamespace(
            status="completed",
            result={"ok": True},
            error=None,
            stdout_excerpt="",
            stderr_excerpt="",
            duration_ms=5,
            worker_id="cf-worker",
            sandbox_session_id="dispatch-bound",
            events=[],
            runtime_metadata={"provider": "cloudflare_workers"},
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    run = await ArtifactExecutionService(db_session).execute_live_run(
        tenant_id=tenant.id,
        created_by=user.id,
        revision_id=artifact.latest_published_revision_id,
        domain="tool",
        queue_class="artifact_prod_interactive",
        input_payload={"value": 1},
        config_payload={"mode": "secure"},
        context_payload={},
    )

    assert run is not None
    assert captured["request"]["context"]["credentials"] == {str(credential.id): "super-secret-key"}
    assert "source_files" not in captured["request"]
    assert "allowed_hosts" not in captured["request"]
    assert "outbound_grant" not in captured["request"]
    assert "api_key" not in captured["request"]["config"]
    assert "api_key" not in captured["request"]["context"]
    result = await db_session.execute(
        select(ArtifactRun).where(ArtifactRun.id == run.id)
    )
    persisted_run = result.scalar_one()
    assert "super-secret-key" not in str(persisted_run.config_payload)
    assert "super-secret-key" not in str(persisted_run.context_payload)
    assert "super-secret-key" not in str(artifact.latest_published_revision.source_files)


@pytest.mark.asyncio
async def test_execute_live_run_rejects_disabled_credential_at_runtime(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    credential = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Runtime",
        credentials={"api_key": "super-secret-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.flush()

    artifact = await ArtifactRevisionService(db_session).create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        display_name="Disabled Runtime Artifact",
        description=None,
        kind="tool_impl",
        source_files=[{"path": "main.py", "content": f'def execute(inputs, config, context):\n    return {{"api_key": "@{{{credential.id}}}"}}\n'}],
        entry_module_path="main.py",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True, "allowed_hosts": []},
        config_schema={},
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    )
    await ArtifactRevisionService(db_session).publish_latest_draft(artifact)
    credential.is_enabled = False
    await db_session.commit()

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="cf-worker",
            deployment_id="dep-disabled",
            version_id="ver-disabled",
            build_hash=revision.build_hash,
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)

    with pytest.raises(RuntimeError, match="Credential disabled"):
        await ArtifactExecutionService(db_session).execute_live_run(
            tenant_id=tenant.id,
            created_by=user.id,
            revision_id=artifact.latest_published_revision_id,
            domain="tool",
            queue_class="artifact_prod_interactive",
            input_payload={"value": 1},
            config_payload={},
            context_payload={},
        )


@pytest.mark.asyncio
async def test_start_test_run_returns_failed_run_when_eager_dispatch_crashes(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="tool_impl")
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="artifact-test-worker",
            deployment_id="dep-test-500",
            version_id="ver-test-500",
            build_hash=revision.build_hash,
        )

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

    run = await ArtifactExecutionService(db_session).start_test_run(
        tenant_id=tenant.id,
        created_by=user.id,
        artifact_id=artifact.id,
        source_files=None,
        entry_module_path=None,
        input_data={"client_id": "32001"},
        config={},
        dependencies=None,
        language=None,
        kind=None,
        runtime_target=None,
        capabilities=None,
        config_schema=None,
        agent_contract=None,
        rag_contract=None,
        tool_contract=None,
    )

    assert str(getattr(run.status, "value", run.status)) == "failed"
    assert run.error_payload["code"] == "CLOUDFLARE_DISPATCH_HTTP_ERROR"
    assert run.error_payload["dispatch_detail"]["code"] == "WORKER_CRASH"
    assert "worker crashed" in run.error_payload["message"]


@pytest.mark.asyncio
async def test_start_test_run_passes_raw_input_payload_to_dispatch(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True, kind="tool_impl")
    monkeypatch.setenv("ARTIFACT_RUN_TASK_EAGER", "1")
    captured: dict[str, object] = {}

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="artifact-test-worker",
            deployment_id="dep-test-raw",
            version_id="ver-test-raw",
            build_hash=revision.build_hash,
        )

    async def fake_execute(self, payload):
        captured["inputs"] = payload["inputs"]
        return SimpleNamespace(
            status="completed",
            result={"ok": True},
            error=None,
            stdout_excerpt="",
            stderr_excerpt="",
            duration_ms=1,
            worker_id="artifact-test-worker",
            sandbox_session_id="dispatch-test-raw",
            events=[],
            runtime_metadata={},
        )

    monkeypatch.setattr("app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment", fake_ensure_deployment)
    monkeypatch.setattr("app.services.artifact_runtime.cloudflare_dispatch_client.CloudflareDispatchClient.execute", fake_execute)

    run = await ArtifactExecutionService(db_session).start_test_run(
        tenant_id=tenant.id,
        created_by=user.id,
        artifact_id=artifact.id,
        source_files=None,
        entry_module_path=None,
        input_data={"client_id": "32001"},
        config={},
        dependencies=None,
        language=None,
        kind=None,
        runtime_target=None,
        capabilities=None,
        config_schema=None,
        agent_contract=None,
        rag_contract=None,
        tool_contract=None,
    )

    assert str(getattr(run.status, "value", run.status)) == "completed"
    assert captured["inputs"] == {"client_id": "32001"}
