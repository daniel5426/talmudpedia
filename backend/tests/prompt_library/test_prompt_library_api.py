from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_principal
from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.prompts import PromptLibrary
from app.db.postgres.models.registry import ToolDefinitionScope, ToolImplementationType, ToolRegistry, ToolStatus
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactKind, ArtifactOwnerType, ArtifactRevision, ArtifactStatus
from app.db.postgres.models.workspace import Project
from app.services.prompt_reference_resolver import PromptReferenceResolver
from main import app


async def _seed_tenant_context(db_session):
    tenant = Organization(id=uuid.uuid4(), name="Prompt Organization", slug=f"prompt-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"prompt-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    project = Project(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="Prompt Project",
        slug=f"prompt-project-{uuid.uuid4().hex[:8]}",
    )
    db_session.add_all([tenant, user, project])
    await db_session.commit()
    return tenant, user, project


def _override_principal(organization_id, project_id, user, scopes: list[str]):
    user_id = str(user.id)
    tenant_id_text = str(organization_id)
    project_id_text = str(project_id)
    role = str(getattr(user, "role", "admin") or "admin")

    async def _inner():
        return {
            "type": "user",
            "user": None,
            "user_id": user_id,
            "organization_id": tenant_id_text,
            "project_id": project_id_text,
            "scopes": scopes,
            "role": role,
        }

    return _inner


@pytest.mark.asyncio
async def test_prompt_library_crud_and_resolve_preview(client, db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        project.id,
        user,
        ["agents.read", "agents.write"],
    )
    try:
        child_resp = await client.post(
            "/prompts",
            json={"name": "Greeting", "content": "Hello world"},
        )
        assert child_resp.status_code == 200, child_resp.text
        child = child_resp.json()

        parent_resp = await client.post(
            "/prompts",
            json={"name": "Wrapper", "content": f"Before [[prompt:{child['id']}]] After"},
        )
        assert parent_resp.status_code == 200, parent_resp.text
        parent = parent_resp.json()

        search_resp = await client.get("/prompts/mentions/search?q=wrap")
        assert search_resp.status_code == 200, search_resp.text
        assert [item["id"] for item in search_resp.json()] == [parent["id"]]

        preview_resp = await client.post(
            "/prompts/resolve-preview",
            json={"text": f"Start [[prompt:{parent['id']}]] End"},
        )
        assert preview_resp.status_code == 200, preview_resp.text
        payload = preview_resp.json()
        assert payload["text"] == "Start Before Hello world After End"
        assert [binding["prompt_id"] for binding in payload["bindings"]] == [parent["id"], child["id"]]

        rename_resp = await client.patch(
            f"/prompts/{child['id']}",
            json={"name": "Greeting Updated", "content": "Hello world"},
        )
        assert rename_resp.status_code == 200, rename_resp.text
        renamed = rename_resp.json()
        assert renamed["name"] == "Greeting Updated"
        assert renamed["version"] == 2

        renamed_search = await client.get("/prompts/mentions/search?q=updated")
        assert renamed_search.status_code == 200
        assert renamed_search.json()[0]["id"] == child["id"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_prompt_delete_is_blocked_when_agent_references_it(client, db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(
        tenant.id,
        project.id,
        user,
        ["agents.read", "agents.write"],
    )
    try:
        prompt_resp = await client.post("/prompts", json={"name": "Shared", "content": "Shared instructions"})
        assert prompt_resp.status_code == 200, prompt_resp.text
        prompt = prompt_resp.json()

        agent = Agent(
            id=uuid.uuid4(),
            organization_id=tenant.id,
            project_id=project.id,
            name="Prompt Agent",
            slug=f"prompt-agent-{uuid.uuid4().hex[:6]}",
            graph_definition={
                "nodes": [
                    {"id": "n1", "type": "agent", "config": {"model_id": "m1", "instructions": f"[[prompt:{prompt['id']}]]"}},
                ],
                "edges": [],
            },
            referenced_model_ids=[],
            referenced_tool_ids=[],
        )
        db_session.add(agent)
        await db_session.commit()

        delete_resp = await client.delete(f"/prompts/{prompt['id']}")
        assert delete_resp.status_code == 409, delete_resp.text

        usage_resp = await client.get(f"/prompts/{prompt['id']}/usage")
        assert usage_resp.status_code == 200, usage_resp.text
        usage = usage_resp.json()
        assert usage[0]["resource_type"] == "agent"
        assert usage[0]["surface"] == "agent.instructions"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_paused_run_status_includes_resolved_interaction_prompt(db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    prompt = PromptLibrary(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=project.id,
        name="Approval Prompt",
        content="Approve {{ticket}}?",
        scope="tenant",
        status="active",
        ownership="manual",
        managed_by="prompts",
        allowed_surfaces=["user_approval.message"],
        tags=[],
        version=1,
    )
    agent = Agent(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=project.id,
        name="Paused Agent",
        slug=f"paused-agent-{uuid.uuid4().hex[:6]}",
        graph_definition={
            "nodes": [
                {
                    "id": "approval-node",
                    "type": "user_approval",
                    "config": {"name": "Approval", "message": f"[[prompt:{prompt.id}]]", "require_comment": True},
                }
            ],
            "edges": [],
        },
        referenced_model_ids=[],
        referenced_tool_ids=[],
    )
    db_session.add_all([prompt, agent])
    await db_session.commit()

    resolved_graph = await PromptReferenceResolver(db_session, tenant.id, project.id).resolve_graph_definition(agent.graph_definition)
    paused_node = AgentExecutorService._build_paused_node_payload(
        node=resolved_graph["nodes"][0],
        state={"ticket": "ABC-123"},
    )
    assert paused_node["interaction"]["message"] == "Approve ABC-123?"
    assert paused_node["interaction"]["require_comment"] is True


@pytest.mark.asyncio
async def test_usage_scanner_covers_tools_and_artifacts(db_session):
    tenant, _user, project = await _seed_tenant_context(db_session)
    prompt = PromptLibrary(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=project.id,
        name="Schema Prompt",
        content="Used in schemas",
        scope="tenant",
        status="active",
        ownership="manual",
        managed_by="prompts",
        allowed_surfaces=[],
        tags=[],
        version=1,
    )
    tool = ToolRegistry(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=project.id,
        name="Prompt Tool",
        slug=f"prompt-tool-{uuid.uuid4().hex[:6]}",
        description=f"[[prompt:{prompt.id}]]",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {"type": "object", "properties": {"text": {"type": "string", "description": f"[[prompt:{prompt.id}]]"}}},
            "output": {"type": "object", "properties": {}},
        },
        config_schema={},
        implementation_type=ToolImplementationType.CUSTOM,
        status=ToolStatus.DRAFT,
        version="1.0.0",
        is_active=True,
        is_system=False,
    )
    artifact = Artifact(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        project_id=project.id,
        display_name="Prompt Artifact",
        kind=ArtifactKind.TOOL_IMPL,
        owner_type=ArtifactOwnerType.TENANT,
        status=ArtifactStatus.DRAFT,
    )
    revision = ArtifactRevision(
        id=uuid.uuid4(),
        artifact_id=artifact.id,
        organization_id=tenant.id,
        revision_number=1,
        version_label="draft",
        is_published=False,
        is_ephemeral=False,
        display_name="Prompt Artifact",
        kind=ArtifactKind.TOOL_IMPL,
        source_files=[],
        entry_module_path="main.py",
        manifest_json={},
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={},
        config_schema={},
        tool_contract={
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": f"[[prompt:{prompt.id}]]"}},
            },
            "output_schema": {"type": "object", "properties": {}},
        },
        build_hash="hash",
        dependency_hash="hash",
        bundle_hash="hash",
    )
    artifact.latest_draft_revision_id = revision.id
    artifact.latest_draft_revision = revision
    db_session.add_all([prompt, tool, artifact, revision])
    await db_session.commit()

    usage = await PromptReferenceResolver(db_session, tenant.id, project.id).scan_usage(prompt_id=prompt.id)
    surfaces = {(item["resource_type"], item["surface"]) for item in usage}
    assert ("tool", "tool.description") in surfaces
    assert ("tool", "tool.schema.description") in surfaces
    assert ("artifact", "artifact.tool_contract.description") in surfaces

    prompt_ids = PromptReferenceResolver.parse_prompt_token_ids(f"[[prompt:{prompt.id}]] and [[prompt:{prompt.id}]]")
    assert prompt_ids == [prompt.id, prompt.id]
