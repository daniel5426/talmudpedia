from __future__ import annotations

import uuid

import pytest

from app.api.dependencies import get_current_principal
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.rag import ExecutablePipeline, KnowledgeStore, PipelineJob, PipelineJobStatus, RetrievalPolicy, StorageBackend, VisualPipeline
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType, ModelStatus
from app.db.postgres.models.workspace import Project
from main import app


async def _seed_context(db_session):
    tenant = Organization(id=uuid.uuid4(), name="RAG Campaign Organization", slug=f"rag-campaign-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"rag-campaign-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    project = Project(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="Default Project",
        slug=f"project-{uuid.uuid4().hex[:8]}",
        is_default=True,
        created_by=user.id,
    )
    db_session.add_all([tenant, user, project])
    await db_session.commit()
    return tenant, user, project


def _override_principal(organization_id, project_id, user, scopes: list[str]):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "organization_id": str(organization_id),
            "project_id": str(project_id),
            "scopes": scopes,
        }

    return _inner


def _override_current_user(user):
    async def _inner():
        return user

    return _inner


def _graph_payload(name: str, *, embed_model_id: str, knowledge_store_id: str) -> dict:
    return {
        "name": name,
        "description": "RAG campaign API pipeline",
        "pipeline_type": "retrieval",
        "nodes": [
            {"id": "input", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "embed", "category": "embedding", "operator": "model_embedder", "position": {"x": 120, "y": 0}, "config": {"model_id": embed_model_id}},
            {"id": "search", "category": "retrieval", "operator": "vector_search", "position": {"x": 240, "y": 0}, "config": {"knowledge_store_id": knowledge_store_id, "top_k": 3}},
            {"id": "output", "category": "output", "operator": "retrieval_result", "position": {"x": 360, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "embed"},
            {"id": "e2", "source": "embed", "target": "search"},
            {"id": "e3", "source": "search", "target": "output"},
        ],
    }


async def _seed_embed_model(db_session, organization_id) -> str:
    model = ModelRegistry(
        id=uuid.uuid4(),
        organization_id=organization_id,
        name="Campaign Embedding",
        system_key=f"campaign-embed-{uuid.uuid4().hex[:6]}",
        capability_type=ModelCapabilityType.EMBEDDING,
        status=ModelStatus.ACTIVE,
        default_resolution_policy={},
        metadata_={"dimensions": 4},
        is_active=True,
        is_default=False,
    )
    db_session.add(model)
    await db_session.commit()
    return str(model.id)


async def _seed_knowledge_store(db_session, organization_id, project_id, user_id) -> str:
    store = KnowledgeStore(
        id=uuid.uuid4(),
        organization_id=organization_id,
        project_id=project_id,
        name="Campaign Store",
        description="RAG campaign API store",
        embedding_model_id="manual-store-model",
        chunking_strategy={},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": f"campaign_api_{uuid.uuid4().hex[:6]}"},
        created_by=user_id,
    )
    db_session.add(store)
    await db_session.commit()
    return str(store.id)


@pytest.mark.asyncio
async def test_rag_admin_list_visual_pipelines_uses_active_project_context(client, db_session, monkeypatch):
    tenant, user, project = await _seed_context(db_session)
    other_project = Project(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="Other Project",
        slug=f"project-{uuid.uuid4().hex[:8]}",
        is_default=False,
        created_by=user.id,
    )
    db_session.add(other_project)
    await db_session.commit()

    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        project.id,
        user,
        ["pipelines.read", "pipelines.write"],
    )
    app.dependency_overrides[get_current_user] = _override_current_user(user)

    async def fake_log_simple_action(**kwargs):
        return None

    monkeypatch.setattr("app.api.routers.rag_pipelines.log_simple_action", fake_log_simple_action)

    active_pipeline = VisualPipeline(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=project.id,
        name="Active Project Pipeline",
        description="visible",
        pipeline_type="retrieval",
        nodes=[],
        edges=[],
        version=1,
        is_published=False,
        created_by=user.id,
    )
    other_pipeline = VisualPipeline(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=other_project.id,
        name="Other Project Pipeline",
        description="hidden",
        pipeline_type="retrieval",
        nodes=[],
        edges=[],
        version=1,
        is_published=False,
        created_by=user.id,
    )
    db_session.add_all([active_pipeline, other_pipeline])
    await db_session.commit()

    try:
        response = await client.get(
            f"/admin/pipelines/visual-pipelines?organization_id={tenant.id}&skip=0&limit=100&view=summary"
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [item["id"] for item in payload["items"]] == [str(active_pipeline.id)]
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_rag_admin_graph_apply_patch_persists_and_bumps_version(client, db_session, monkeypatch):
    tenant, user, project = await _seed_context(db_session)
    embed_model_id = await _seed_embed_model(db_session, tenant.id)
    knowledge_store_id = await _seed_knowledge_store(db_session, tenant.id, project.id, user.id)

    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        project.id,
        user,
        ["pipelines.read", "pipelines.write"],
    )
    app.dependency_overrides[get_current_user] = _override_current_user(user)
    async def fake_log_simple_action(**kwargs):
        return None

    monkeypatch.setattr("app.api.routers.rag_pipelines.log_simple_action", fake_log_simple_action)

    try:
        create_response = await client.post(
            f"/admin/pipelines/visual-pipelines?tenant_slug={tenant.slug}",
            json=_graph_payload("Campaign Graph", embed_model_id=embed_model_id, knowledge_store_id=knowledge_store_id),
        )
        assert create_response.status_code == 200, create_response.text
        pipeline_id = create_response.json()["id"]

        pipeline = await db_session.get(VisualPipeline, uuid.UUID(pipeline_id))
        pipeline.is_published = True
        pipeline.version = 3
        await db_session.commit()

        patch_response = await client.post(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/graph/apply-patch?tenant_slug={tenant.slug}",
            json={
                "operations": [
                    {"op": "set_node_config_value", "node_id": "search", "path": "top_k", "value": 8}
                ]
            },
        )
        assert patch_response.status_code == 200, patch_response.text
        payload = patch_response.json()
        assert payload["validation"]["valid"] is True

        await db_session.refresh(pipeline)
        search_node = next(node for node in pipeline.nodes if node["id"] == "search")
        assert search_node["config"]["top_k"] == 8
        assert pipeline.version == 4
        assert pipeline.is_published is False
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_rag_admin_compile_and_job_creation_persist_rows(client, db_session, monkeypatch):
    tenant, user, project = await _seed_context(db_session)
    embed_model_id = await _seed_embed_model(db_session, tenant.id)
    knowledge_store_id = await _seed_knowledge_store(db_session, tenant.id, project.id, user.id)

    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        project.id,
        user,
        ["pipelines.read", "pipelines.write"],
    )
    app.dependency_overrides[get_current_user] = _override_current_user(user)

    async def fake_log_simple_action(**kwargs):
        return None

    monkeypatch.setattr("app.api.routers.rag_pipelines.log_simple_action", fake_log_simple_action)

    async def fake_run_pipeline_job_background(job_id, artifact_queue_class="artifact_prod_background"):
        del artifact_queue_class
        job = await db_session.get(PipelineJob, job_id)
        job.status = PipelineJobStatus.COMPLETED
        job.output = {"results": [{"id": "doc-1", "text": "hello"}]}
        await db_session.commit()

    monkeypatch.setattr("app.api.routers.rag_pipelines.run_pipeline_job_background", fake_run_pipeline_job_background)

    try:
        create_response = await client.post(
            f"/admin/pipelines/visual-pipelines?organization_id={tenant.id}",
            json=_graph_payload("Campaign Compile", embed_model_id=embed_model_id, knowledge_store_id=knowledge_store_id),
        )
        assert create_response.status_code == 200, create_response.text
        pipeline_id = create_response.json()["id"]

        compile_response = await client.post(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/compile?organization_id={tenant.id}"
        )
        assert compile_response.status_code == 200, compile_response.text
        compile_payload = compile_response.json()
        assert compile_payload["success"] is True

        executable_id = compile_payload["executable_pipeline_id"]
        executable = await db_session.get(ExecutablePipeline, uuid.UUID(executable_id))
        assert executable is not None

        job_response = await client.post(
            f"/admin/pipelines/jobs?organization_id={tenant.id}",
            json={"executable_pipeline_id": executable_id, "input_params": {"text": "hello retrieval", "top_k": 2}},
        )
        assert job_response.status_code == 200, job_response.text
        job_payload = job_response.json()
        job = await db_session.get(PipelineJob, uuid.UUID(job_payload["job_id"]))
        assert job is not None
        assert job.status in {PipelineJobStatus.QUEUED, PipelineJobStatus.COMPLETED}
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.dependency_overrides.pop(get_current_user, None)
