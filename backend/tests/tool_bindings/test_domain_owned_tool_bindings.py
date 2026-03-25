from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_principal
from app.db.postgres.models.artifact_runtime import Artifact
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.rag import VisualPipeline
from app.db.postgres.models.registry import ToolImplementationType, ToolRegistry, ToolStatus
from main import app


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Bindings Tenant", slug=f"bindings-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"bindings-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Bindings Org",
        slug=f"bindings-org-{uuid.uuid4().hex[:6]}",
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


def _override_principal(tenant_id, user, scopes: list[str]):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "scopes": scopes,
        }

    return _inner


async def _get_tool_for_artifact(db_session, artifact_id: str) -> ToolRegistry | None:
    return (
        await db_session.execute(select(ToolRegistry).where(ToolRegistry.artifact_id == artifact_id))
    ).scalar_one_or_none()


async def _get_tool_for_pipeline(db_session, pipeline_id: str) -> ToolRegistry | None:
    return (
        await db_session.execute(select(ToolRegistry).where(ToolRegistry.visual_pipeline_id == uuid.UUID(pipeline_id)))
    ).scalar_one_or_none()


def _retrieval_pipeline_payload(name: str) -> dict:
    return {
        "name": name,
        "description": "Retrieval pipeline for tool bindings",
        "pipeline_type": "retrieval",
        "nodes": [
            {
                "id": "input",
                "category": "input",
                "operator": "query_input",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "embed",
                "category": "embedding",
                "operator": "model_embedder",
                "position": {"x": 120, "y": 0},
                "config": {},
            },
            {
                "id": "search",
                "category": "retrieval",
                "operator": "vector_search",
                "position": {"x": 240, "y": 0},
                "config": {},
            },
            {
                "id": "output",
                "category": "output",
                "operator": "retrieval_result",
                "position": {"x": 360, "y": 0},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "embed"},
            {"id": "e2", "source": "embed", "target": "search"},
            {"id": "e3", "source": "search", "target": "output"},
        ],
    }


def _ingestion_pipeline_payload(name: str) -> dict:
    return {
        "name": name,
        "description": "Ingestion pipeline for tool bindings",
        "pipeline_type": "ingestion",
        "nodes": [
            {
                "id": "source",
                "category": "source",
                "operator": "local_loader",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "normalize",
                "category": "normalization",
                "operator": "format_normalizer",
                "position": {"x": 120, "y": 0},
                "config": {},
            },
            {
                "id": "enrich",
                "category": "enrichment",
                "operator": "metadata_extractor",
                "position": {"x": 240, "y": 0},
                "config": {},
            },
            {
                "id": "chunk",
                "category": "chunking",
                "operator": "token_based_chunker",
                "position": {"x": 360, "y": 0},
                "config": {},
            },
            {
                "id": "embed",
                "category": "embedding",
                "operator": "model_embedder",
                "position": {"x": 480, "y": 0},
                "config": {},
            },
            {
                "id": "store",
                "category": "storage",
                "operator": "knowledge_store_sink",
                "position": {"x": 600, "y": 0},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e1", "source": "source", "target": "normalize"},
            {"id": "e2", "source": "normalize", "target": "enrich"},
            {"id": "e3", "source": "enrich", "target": "chunk"},
            {"id": "e4", "source": "chunk", "target": "embed"},
            {"id": "e5", "source": "embed", "target": "store"},
        ],
    }


@pytest.mark.asyncio
async def test_tool_impl_artifact_routes_own_bound_tool_lifecycle(client, db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        user,
        ["artifacts.read", "artifacts.write"],
    )

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="prod-worker",
            deployment_id="dep-1",
            version_id="ver-1",
            build_hash=revision.build_hash,
        )

    monkeypatch.setattr(
        "app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment",
        fake_ensure_deployment,
    )

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Tool",
                "description": "Artifact-owned tool",
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "capabilities": {},
                "config_schema": {"timeout_s": 15},
                "tool_contract": {
                    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
                    "output_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        tool = await _get_tool_for_artifact(db_session, artifact["id"])
        assert tool is not None
        assert tool.implementation_type == ToolImplementationType.ARTIFACT
        assert tool.status == ToolStatus.DRAFT
        assert tool.slug.startswith("artifact-tool-")
        assert tool.schema["input"]["properties"]["text"]["type"] == "string"
        assert tool.ownership == "artifact_bound"
        assert tool.managed_by == "artifacts"
        assert tool.source_object_type == "artifact"
        assert tool.source_object_id == artifact["id"]

        tool_response = await client.get(f"/tools/{tool.id}")
        assert tool_response.status_code == 200, tool_response.text
        tool_payload = tool_response.json()
        assert tool_payload["ownership"] == "artifact_bound"
        assert tool_payload["managed_by"] == "artifacts"
        assert tool_payload["source_object_type"] == "artifact"
        assert tool_payload["source_object_id"] == artifact["id"]
        assert tool_payload["can_edit_in_registry"] is False
        assert tool_payload["can_publish_in_registry"] is False
        assert tool_payload["can_delete_in_registry"] is False

        update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Tool Updated",
                "description": "Updated artifact-owned tool",
                "config_schema": {"timeout_s": 42},
                "tool_contract": {
                    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            },
        )
        assert update_response.status_code == 200, update_response.text

        tool = await _get_tool_for_artifact(db_session, artifact["id"])
        assert tool is not None
        assert tool.name == "Artifact Tool Updated"
        assert tool.schema["input"]["properties"]["query"]["type"] == "string"
        assert tool.config_schema["timeout_s"] == 42
        assert tool.status == ToolStatus.DRAFT
        assert tool.artifact_revision_id is None
        assert tool.ownership == "artifact_bound"
        assert tool.source_object_id == artifact["id"]

        publish_response = await client.post(f"/admin/artifacts/{artifact['id']}/publish?tenant_slug={tenant.slug}")
        assert publish_response.status_code == 200, publish_response.text

        tool = await _get_tool_for_artifact(db_session, artifact["id"])
        assert tool is not None
        assert tool.status == ToolStatus.PUBLISHED
        assert tool.artifact_revision_id is not None
        published_revision_id = tool.artifact_revision_id
        published_name = tool.name
        published_input_schema = dict(tool.schema["input"])

        draft_update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Tool Draft v3",
                "description": "Draft change after publish",
                "config_schema": {"timeout_s": 99},
                "tool_contract": {
                    "input_schema": {"type": "object", "properties": {"draft_only": {"type": "string"}}},
                    "output_schema": {"type": "object", "properties": {"draft_answer": {"type": "string"}}},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            },
        )
        assert draft_update_response.status_code == 200, draft_update_response.text

        tool = await _get_tool_for_artifact(db_session, artifact["id"])
        assert tool is not None
        assert tool.status == ToolStatus.PUBLISHED
        assert tool.artifact_revision_id == published_revision_id
        assert tool.name == published_name
        assert tool.schema["input"] == published_input_schema

        delete_response = await client.delete(f"/admin/artifacts/{artifact['id']}?tenant_slug={tenant.slug}")
        assert delete_response.status_code == 200, delete_response.text

        assert await _get_tool_for_artifact(db_session, artifact["id"]) is None
        deleted_artifact = await db_session.get(Artifact, uuid.UUID(artifact["id"]))
        assert deleted_artifact is None
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_pipeline_owned_tool_binding_enable_publish_disable_and_demote(client, db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        user,
        ["pipelines.read", "pipelines.write"],
    )
    monkeypatch.setattr("app.api.routers.rag_pipelines.log_simple_action", AsyncMock())

    try:
        create_response = await client.post(
            f"/admin/pipelines/visual-pipelines?tenant_slug={tenant.slug}",
            json=_retrieval_pipeline_payload("Retrieval Tool Pipeline"),
        )
        assert create_response.status_code == 200, create_response.text
        pipeline_id = create_response.json()["id"]

        bind_response = await client.put(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/tool-binding?tenant_slug={tenant.slug}",
            json={
                "enabled": True,
                "tool_name": "Retrieval Assistant Tool",
                "description": "Use this when the agent needs normalized retrieval input.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Normalized retrieval query"},
                        "filters": {"type": "object", "description": "Optional metadata filters"},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        )
        assert bind_response.status_code == 200, bind_response.text

        tool = await _get_tool_for_pipeline(db_session, pipeline_id)
        assert tool is not None
        assert tool.implementation_type == ToolImplementationType.RAG_PIPELINE
        assert tool.status == ToolStatus.DRAFT
        assert tool.executable_pipeline_id is None
        assert tool.name == "Retrieval Assistant Tool"
        assert tool.ownership == "pipeline_bound"
        assert tool.managed_by == "pipelines"
        assert tool.source_object_type == "pipeline"
        assert tool.source_object_id == pipeline_id
        assert tool.schema["input"]["properties"]["text"]["description"] == "Normalized retrieval query"

        tool_response = await client.get(f"/tools/{tool.id}")
        assert tool_response.status_code == 200, tool_response.text
        tool_payload = tool_response.json()
        assert tool_payload["ownership"] == "pipeline_bound"
        assert tool_payload["managed_by"] == "pipelines"
        assert tool_payload["source_object_type"] == "pipeline"
        assert tool_payload["source_object_id"] == pipeline_id
        assert tool_payload["name"] == "Retrieval Assistant Tool"
        assert tool_payload["can_edit_in_registry"] is False
        assert tool_payload["can_publish_in_registry"] is False
        assert tool_payload["can_delete_in_registry"] is False

        compile_response = await client.post(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/compile?tenant_slug={tenant.slug}"
        )
        assert compile_response.status_code == 200, compile_response.text
        assert compile_response.json()["success"] is True

        tool = await _get_tool_for_pipeline(db_session, pipeline_id)
        assert tool is not None
        assert tool.status == ToolStatus.PUBLISHED
        assert tool.executable_pipeline_id is not None
        assert tool.name == "Retrieval Assistant Tool"
        assert tool.ownership == "pipeline_bound"
        assert tool.source_object_id == pipeline_id
        assert tool.schema["input"]["properties"]["text"]["description"] == "Normalized retrieval query"

        disable_response = await client.put(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/tool-binding?tenant_slug={tenant.slug}",
            json={
                "enabled": False,
                "description": "Use this when the agent needs normalized retrieval input.",
                "input_schema": tool.schema["input"],
            },
        )
        assert disable_response.status_code == 200, disable_response.text

        tool = await _get_tool_for_pipeline(db_session, pipeline_id)
        assert tool is not None
        assert tool.status == ToolStatus.DISABLED
        assert tool.is_active is False
        assert tool.schema["input"]["properties"]["text"]["description"] == "Normalized retrieval query"

        reenable_response = await client.put(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/tool-binding?tenant_slug={tenant.slug}",
            json={
                "enabled": True,
                "description": "Use this when the agent needs normalized retrieval input.",
                "input_schema": tool.schema["input"],
            },
        )
        assert reenable_response.status_code == 200, reenable_response.text

        tool = await _get_tool_for_pipeline(db_session, pipeline_id)
        assert tool is not None
        assert tool.status == ToolStatus.DRAFT
        assert tool.is_active is True

        update_response = await client.put(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}?tenant_slug={tenant.slug}",
            json={"description": "Updated pipeline description"},
        )
        assert update_response.status_code == 200, update_response.text

        pipeline = await db_session.get(VisualPipeline, uuid.UUID(pipeline_id))
        tool = await _get_tool_for_pipeline(db_session, pipeline_id)
        assert pipeline is not None
        assert pipeline.is_published is False
        assert tool is not None
        assert tool.status == ToolStatus.DRAFT
        assert tool.executable_pipeline_id is None
        assert tool.name == "Retrieval Assistant Tool"
        assert tool.ownership == "pipeline_bound"
        assert tool.source_object_id == pipeline_id
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_ingestion_pipeline_can_publish_as_tool(client, db_session, monkeypatch):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        user,
        ["pipelines.read", "pipelines.write"],
    )
    monkeypatch.setattr("app.api.routers.rag_pipelines.log_simple_action", AsyncMock())

    try:
        create_response = await client.post(
            f"/admin/pipelines/visual-pipelines?tenant_slug={tenant.slug}",
            json=_ingestion_pipeline_payload("Ingestion Tool Pipeline"),
        )
        assert create_response.status_code == 200, create_response.text
        pipeline_id = create_response.json()["id"]

        enable_response = await client.put(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/tool-binding?tenant_slug={tenant.slug}",
            json={"enabled": True, "description": "Ingest user-provided sources into the knowledge store."},
        )
        assert enable_response.status_code == 200, enable_response.text

        compile_response = await client.post(
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/compile?tenant_slug={tenant.slug}"
        )
        assert compile_response.status_code == 200, compile_response.text
        assert compile_response.json()["success"] is True

        tool = await _get_tool_for_pipeline(db_session, pipeline_id)
        assert tool is not None
        assert tool.status == ToolStatus.PUBLISHED
        assert tool.implementation_type == ToolImplementationType.RAG_PIPELINE
        assert tool.executable_pipeline_id is not None
        assert tool.ownership == "pipeline_bound"
        assert tool.source_object_id == pipeline_id
        assert "base_path" in tool.schema["input"]["properties"]
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
