from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.operators import CustomOperator, OperatorCategory
from app.db.postgres.models.rag import ExecutablePipeline, PipelineJob, PipelineJobStatus, PipelineType, VisualPipeline
from app.rag.pipeline.compiler import PipelineCompiler
from app.rag.pipeline.custom_operator_sync import sync_custom_operators
from app.rag.pipeline.executor import PipelineExecutor
from app.rag.pipeline.registry import OperatorRegistry
from app.services.artifact_runtime.revision_service import ArtifactRevisionService


async def _seed_tenant_context(db_session):
    tenant = Organization(id=uuid.uuid4(), name="RAG Mixed Organization", slug=f"rag-mixed-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"rag-mixed-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="RAG Mixed Org",
        slug=f"rag-mixed-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


async def _create_custom_operator(db_session, organization_id, created_by):
    operator = CustomOperator(
        id=uuid.uuid4(),
        organization_id=organization_id,
        name=f"tenant_mixed_custom_{uuid.uuid4().hex[:6]}",
        display_name="Organization Mixed Custom",
        category=OperatorCategory.CUSTOM,
        description="Mixed custom operator",
        python_code="def execute(inputs, config):\n    return {'items': [inputs], 'source': 'artifact'}\n",
        input_type="query",
        output_type="search_results",
        config_schema=[],
        scope="rag",
        version="1.0.0",
        is_active=True,
        created_by=created_by,
    )
    db_session.add(operator)
    await db_session.commit()
    return operator


async def _create_artifact_for_operator(db_session, organization_id, created_by, operator_id):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        organization_id=organization_id,
        created_by=created_by,
        display_name="Mixed RAG Artifact",
        description=None,
        kind="rag_operator",
        source_files=[
            {
                "path": "main.py",
                "content": (
                    "def execute(inputs, config, context):\n"
                    "    return {'items': [inputs], 'source': 'artifact', 'config': config}\n"
                ),
            }
        ],
        entry_module_path="main.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={},
        rag_contract={
            "operator_category": "custom",
            "pipeline_role": "retrieval",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "execution_mode": "background",
        },
    )
    artifact.legacy_custom_operator_id = operator_id
    await revisions.publish_latest_draft(artifact)
    await db_session.commit()
    return artifact


def _build_mixed_pipeline(organization_id, operator_name):
    return VisualPipeline(
        id=uuid.uuid4(),
        organization_id=organization_id,
        name="Mixed Retrieval Pipeline",
        description=None,
        pipeline_type=PipelineType.RETRIEVAL,
        version=1,
        is_published=False,
        nodes=[
            {
                "id": "input",
                "category": "input",
                "operator": "query_input",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "artifact_custom",
                "category": "custom",
                "operator": operator_name,
                "position": {"x": 1, "y": 0},
                "config": {"mode": "mixed"},
            },
            {
                "id": "output",
                "category": "output",
                "operator": "retrieval_result",
                "position": {"x": 2, "y": 0},
                "config": {},
            },
        ],
        edges=[
            {"id": "e1", "source": "input", "target": "artifact_custom"},
            {"id": "e2", "source": "artifact_custom", "target": "output"},
        ],
    )


@pytest.mark.asyncio
async def test_mixed_builtin_plus_artifact_pipeline_compile_pins_artifact_revision(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    operator = await _create_custom_operator(db_session, tenant.id, user.id)
    artifact = await _create_artifact_for_operator(db_session, tenant.id, user.id, operator.id)

    OperatorRegistry.reset_instance()
    await sync_custom_operators(db_session, tenant.id)
    result = PipelineCompiler().compile(
        _build_mixed_pipeline(tenant.id, operator.name),
        compiled_by=str(user.id),
        organization_id=str(tenant.id),
        require_published_artifacts=True,
    )

    assert result.success is True
    step_ids = [step.step_id for step in result.executable_pipeline.dag]
    assert step_ids == ["input", "artifact_custom", "output"]
    artifact_step = next(step for step in result.executable_pipeline.dag if step.step_id == "artifact_custom")
    assert artifact_step.artifact_id == str(artifact.id)
    assert artifact_step.artifact_revision_id == str(artifact.latest_published_revision_id)


@pytest.mark.asyncio
async def test_mixed_builtin_plus_artifact_pipeline_executes_with_background_queue(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    operator = await _create_custom_operator(db_session, tenant.id, user.id)
    artifact = await _create_artifact_for_operator(db_session, tenant.id, user.id, operator.id)
    visual = _build_mixed_pipeline(tenant.id, operator.name)
    db_session.add(visual)
    await db_session.commit()

    OperatorRegistry.reset_instance()
    await sync_custom_operators(db_session, tenant.id)
    compiled = PipelineCompiler().compile(
        visual,
        compiled_by=str(user.id),
        organization_id=str(tenant.id),
        require_published_artifacts=True,
    )
    executable = ExecutablePipeline(
        id=uuid.uuid4(),
        visual_pipeline_id=visual.id,
        organization_id=tenant.id,
        version=1,
        compiled_graph=compiled.executable_pipeline.model_dump(mode="json"),
        pipeline_type=PipelineType.RETRIEVAL,
        is_valid=True,
        compiled_by=user.id,
    )
    job = PipelineJob(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        executable_pipeline_id=executable.id,
        status=PipelineJobStatus.QUEUED,
        input_params={"text": "hello mixed artifact"},
        triggered_by=user.id,
    )
    db_session.add_all([executable, job])
    await db_session.commit()

    captured = {}

    async def fake_execute_live_run(self, **kwargs):
        captured["runtime"] = kwargs
        return SimpleNamespace(
            status="completed",
            result_payload={"data": [{"id": "doc-1", "text": "hello mixed artifact"}]},
            error_payload=None,
        )

    monkeypatch.setattr(
        "app.services.artifact_runtime.execution_service.ArtifactExecutionService.execute_live_run",
        fake_execute_live_run,
    )

    await PipelineExecutor(db_session).execute_job(job.id, artifact_queue_class="artifact_prod_background")
    await db_session.refresh(job)

    assert captured["runtime"]["queue_class"] == "artifact_prod_background"
    assert captured["runtime"]["revision_id"] == artifact.latest_published_revision_id
    assert job.status == PipelineJobStatus.COMPLETED
    assert job.output["final_output"] == [{"id": "doc-1", "text": "hello mixed artifact"}]
