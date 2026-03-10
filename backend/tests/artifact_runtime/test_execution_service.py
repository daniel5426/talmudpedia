import uuid
from types import SimpleNamespace

import pytest

from app.artifact_worker.runner import _invoke
from app.artifact_worker.schemas import ArtifactWorkerExecutionResponse
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
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


async def _create_artifact(db_session, tenant_id, created_by, *, publish: bool):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant_id,
        created_by=created_by,
        name=f"artifact_{uuid.uuid4().hex[:8]}",
        display_name="Runtime Artifact",
        description=None,
        category="custom",
        scope="rag",
        input_type="any",
        output_type="any",
        source_code="def execute(context):\n    return {'ok': True, 'input': context.input_data}\n",
        python_dependencies=[],
        config_schema=[],
        inputs=[],
        outputs=[],
        reads=[],
        writes=[],
    )
    if publish:
        await revisions.publish_latest_draft(artifact)
    await db_session.commit()
    return artifact


@pytest.mark.asyncio
async def test_execute_live_run_records_domain_queue_and_raw_inputs(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True)

    captured = {}

    async def fake_execute(self, request):
        captured["request"] = request
        return ArtifactWorkerExecutionResponse(
            status="completed",
            result={"echo": request.inputs},
            worker_id="worker-1",
            sandbox_session_id="sandbox-1",
            duration_ms=7,
        )

    monkeypatch.setattr(
        "app.services.artifact_runtime.execution_service.DifySandboxWorkerClient.execute",
        fake_execute,
    )

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
    assert captured["request"].inputs == ["raw", {"nested": True}]
    assert run.result_payload == {"echo": ["raw", {"nested": True}]}


@pytest.mark.asyncio
async def test_execute_live_run_background_routes_to_requested_queue(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True)
    captured = {}

    def fake_apply_async(*, args, queue):
        captured["args"] = args
        captured["queue"] = queue

    async def fake_wait(self, run_id, *, timeout_seconds=30.0):
        return await self._runs.get_run(run_id=run_id)

    monkeypatch.setattr(
        "app.workers.artifact_tasks.execute_artifact_run_task.apply_async",
        fake_apply_async,
    )
    monkeypatch.setattr(
        ArtifactExecutionService,
        "wait_for_terminal_state",
        fake_wait,
    )
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
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=False)

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
async def test_runner_legacy_context_preserves_raw_input_payload():
    async def execute(context):
        return {"input": context.input_data, "config": context.config}

    result = await _invoke(execute, ["a", {"b": 1}], {"mode": "legacy"}, {"domain": "rag"})
    assert result == {"input": ["a", {"b": 1}], "config": {"mode": "legacy"}}
