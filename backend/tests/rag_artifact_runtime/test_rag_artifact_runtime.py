import uuid
from types import SimpleNamespace

import pytest

from app.agent.executors.retrieval_runtime import RetrievalPipelineRuntime
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.operators import CustomOperator, OperatorCategory
from app.db.postgres.models.rag import ExecutablePipeline, PipelineJob, PipelineJobStatus, PipelineType, VisualPipeline
from app.rag.pipeline.compiler import PipelineCompiler
from app.rag.pipeline.custom_operator_sync import sync_custom_operators
from app.rag.pipeline.executor import PipelineExecutor
from app.rag.pipeline.registry import OperatorRegistry
from app.services.artifact_runtime.revision_service import ArtifactRevisionService


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="RAG Tenant", slug=f"rag-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"rag-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="RAG Org",
        slug=f"rag-org-{uuid.uuid4().hex[:6]}",
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


async def _create_custom_operator(db_session, tenant_id, created_by):
    operator = CustomOperator(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=f"tenant_custom_{uuid.uuid4().hex[:6]}",
        display_name="Tenant Custom",
        category=OperatorCategory.CUSTOM,
        description="Custom operator",
        python_code="def execute(inputs, config):\n    return {'data': inputs, 'metadata': config}\n",
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


async def _create_artifact_for_operator(db_session, tenant_id, created_by, operator_id, *, publish: bool):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant_id,
        created_by=created_by,
        display_name="RAG Artifact",
        description=None,
        kind="rag_operator",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'data': inputs, 'metadata': {'source': 'artifact'}}\n"}],
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
    if publish:
        await revisions.publish_latest_draft(artifact)
    await db_session.commit()
    return artifact


def _build_pipeline(tenant_id, operator_name):
    return VisualPipeline(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Retrieval Pipeline",
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
                "id": "custom",
                "category": "custom",
                "operator": operator_name,
                "position": {"x": 1, "y": 0},
                "config": {},
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
            {"id": "e1", "source": "input", "target": "custom"},
            {"id": "e2", "source": "custom", "target": "output"},
        ],
    )


@pytest.mark.asyncio
async def test_sync_and_compile_pin_published_artifact_revision(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    operator = await _create_custom_operator(db_session, tenant.id, user.id)
    artifact = await _create_artifact_for_operator(db_session, tenant.id, user.id, operator.id, publish=True)

    OperatorRegistry.reset_instance()
    specs = await sync_custom_operators(db_session, tenant.id)
    spec = next(item for item in specs if item.operator_id == operator.name)
    assert spec.artifact_id == str(artifact.id)
    assert spec.artifact_revision_id == str(artifact.latest_published_revision_id)

    compiler = PipelineCompiler()
    result = compiler.compile(
        _build_pipeline(tenant.id, operator.name),
        compiled_by=str(user.id),
        tenant_id=str(tenant.id),
        require_published_artifacts=True,
    )

    assert result.success is True
    custom_step = next(step for step in result.executable_pipeline.dag if step.step_id == "custom")
    assert custom_step.artifact_id == str(artifact.id)
    assert custom_step.artifact_revision_id == str(artifact.latest_published_revision_id)


@pytest.mark.asyncio
async def test_pipeline_compile_requires_published_artifact_revision(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    operator = await _create_custom_operator(db_session, tenant.id, user.id)
    await _create_artifact_for_operator(db_session, tenant.id, user.id, operator.id, publish=False)

    OperatorRegistry.reset_instance()
    await sync_custom_operators(db_session, tenant.id)
    compiler = PipelineCompiler()

    with pytest.raises(ValueError, match="published artifact revision"):
        compiler.compile(
            _build_pipeline(tenant.id, operator.name),
            compiled_by=str(user.id),
            tenant_id=str(tenant.id),
            require_published_artifacts=True,
        )


@pytest.mark.asyncio
async def test_pipeline_executor_routes_artifact_steps_to_background_queue(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    operator = await _create_custom_operator(db_session, tenant.id, user.id)
    artifact = await _create_artifact_for_operator(db_session, tenant.id, user.id, operator.id, publish=True)

    OperatorRegistry.reset_instance()
    await sync_custom_operators(db_session, tenant.id)
    compiled = PipelineCompiler().compile(
        _build_pipeline(tenant.id, operator.name),
        compiled_by=str(user.id),
        tenant_id=str(tenant.id),
        require_published_artifacts=True,
    )
    visual_pipeline = _build_pipeline(tenant.id, operator.name)
    executable = ExecutablePipeline(
        id=uuid.uuid4(),
        visual_pipeline_id=visual_pipeline.id,
        tenant_id=tenant.id,
        version=1,
        compiled_graph=compiled.executable_pipeline.model_dump(mode="json"),
        pipeline_type=PipelineType.RETRIEVAL,
        is_valid=True,
        compiled_by=user.id,
    )
    job = PipelineJob(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        executable_pipeline_id=executable.id,
        status=PipelineJobStatus.QUEUED,
        input_params={"query": "hello", "text": "hello"},
        triggered_by=user.id,
    )
    db_session.add_all([visual_pipeline, executable, job])
    await db_session.commit()

    captured = {}

    async def fake_execute_live_run(self, **kwargs):
        captured["runtime"] = kwargs
        return SimpleNamespace(status="completed", result_payload={"data": [{"id": "doc-1"}], "metadata": {"source": "artifact"}}, error_payload=None)

    monkeypatch.setattr(
        "app.services.artifact_runtime.execution_service.ArtifactExecutionService.execute_live_run",
        fake_execute_live_run,
    )

    await PipelineExecutor(db_session).execute_job(job.id, artifact_queue_class="artifact_prod_background")
    await db_session.refresh(job)

    assert captured["runtime"]["queue_class"] == "artifact_prod_background"
    assert captured["runtime"]["domain"].value == "rag"
    assert captured["runtime"]["revision_id"] == artifact.latest_published_revision_id
    assert job.status == PipelineJobStatus.COMPLETED
    assert job.output["final_output"] == [{"id": "doc-1"}]
    assert job.output["results"] == [{"id": "doc-1"}]


@pytest.mark.asyncio
async def test_retrieval_runtime_uses_interactive_artifact_queue(db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    visual_pipeline = VisualPipeline(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Runtime Queue Pipeline",
        description=None,
        nodes=[],
        edges=[],
        pipeline_type=PipelineType.RETRIEVAL,
        version=1,
        is_published=False,
        created_by=user.id,
    )
    executable = ExecutablePipeline(
        id=uuid.uuid4(),
        visual_pipeline_id=visual_pipeline.id,
        tenant_id=tenant.id,
        version=1,
        compiled_graph={"dag": []},
        pipeline_type=PipelineType.RETRIEVAL,
        is_valid=True,
        compiled_by=user.id,
    )
    db_session.add_all([visual_pipeline, executable])
    await db_session.commit()

    captured = {}

    async def fake_execute_job(self, job_id, *, artifact_queue_class="artifact_prod_background"):
        captured["queue_class"] = artifact_queue_class
        job = await self.db.get(PipelineJob, job_id)
        job.status = PipelineJobStatus.COMPLETED
        job.output = {"results": [{"id": "doc-1"}]}
        await self.db.commit()

    monkeypatch.setattr(PipelineExecutor, "execute_job", fake_execute_job)

    results, job = await RetrievalPipelineRuntime(db_session, tenant.id).run_query(
        pipeline_id=executable.id,
        query="hello",
    )

    assert captured["queue_class"] == "artifact_prod_interactive"
    assert results == [{"id": "doc-1"}]
    assert job.status == PipelineJobStatus.COMPLETED
