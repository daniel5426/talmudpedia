from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import Organization
from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelRegistry,
    ModelStatus,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)
from app.db.postgres.models.workspace import Project
from app.services import registry_seeding
from app.db.postgres.models.artifact_runtime import Artifact
from app.services.platform_native_tools import PLATFORM_ACTION_FUNCTIONS


def test_platform_architect_graph_is_single_agent_topology():
    graph = registry_seeding._build_architect_graph_definition(
        model_id="model-1",
        tool_ids=["tool-a", "tool-b", "tool-c", "tool-d"],
    )
    node_types = {node.get("type") for node in graph.get("nodes", [])}
    assert node_types == {"start", "agent", "end"}

    node_ids = {node.get("id") for node in graph.get("nodes", [])}
    assert "architect_runtime" in node_ids
    assert "spawn_catalog_stage" not in node_ids
    assert "join_catalog_stage" not in node_ids

    runtime_node = next(node for node in graph["nodes"] if node["id"] == "architect_runtime")
    assert runtime_node["config"]["tools"] == ["tool-a", "tool-b", "tool-c", "tool-d"]
    assert runtime_node["config"]["temperature"] == 1
    assert runtime_node["config"]["max_tool_iterations"] == 26
    assert "output_format" not in runtime_node["config"]
    assert "output_schema" not in runtime_node["config"]

    instructions = runtime_node["config"]["instructions"]
    assert "Visible agent tools: agents.list, agents.get, agents.create" in instructions
    assert "Visible RAG tools: rag.list_visual_pipelines, rag.operators.catalog" in instructions
    assert "Visible asset tools: tools.list, tools.get, tools.create_or_update" in instructions
    assert "Visible worker tools: architect-worker-binding-prepare, architect-worker-binding-persist-artifact, architect-worker-spawn, architect-worker-await, architect-worker-respond." in instructions
    assert "The legacy domain container tools platform-rag, platform-agents, platform-assets, and platform-governance are not available here." in instructions
    assert "Each visible platform tool already fixes the action id." in instructions
    assert "Do not send action, payload, query, text, or value wrappers." in instructions
    assert "Graph-first authoring is the default path." in instructions
    assert "Use agents.create for first agent creation and agents.update for graph updates." in instructions
    assert "Use rag.create_visual_pipeline for first pipeline creation and rag.update_visual_pipeline for graph updates." in instructions
    assert "For agents.create and agents.update, send graph_definition and then use agents.validate as the repair checkpoint." in instructions
    assert "For rag.create_visual_pipeline and rag.update_visual_pipeline, send nodes and edges at top level and use rag.compile_visual_pipeline as the repair checkpoint." in instructions
    assert "Spawn the artifact worker asynchronously with architect-worker-spawn using objective as a top-level field, then wait with architect-worker-await." in instructions
    assert "Use architect-worker-binding-persist-artifact for the persistence step when create or update is required." in instructions
    assert "If the requested output is an agent-callable tool, the normal lifecycle is: create or update a tool_impl artifact" in instructions
    assert "Never call architect.run" in instructions
    assert "agents.create_shell" not in instructions
    assert "rag.create_pipeline_shell" not in instructions
    assert "platform-governance" in instructions
    assert "prompts.list" not in instructions
    assert "architect-worker-binding-get-state" not in instructions
    assert "architect-worker-spawn-group" not in instructions
    assert "architect-worker-get-run" not in instructions
    assert "architect-worker-join" not in instructions
    assert "architect-worker-cancel" not in instructions


def test_platform_architect_canonical_surface_is_hard_cut():
    assert len(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS) == 36
    assert len(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_WORKER_TOOL_KEYS) == 5

    canonical_actions = set(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS)
    assert "agents.create" in canonical_actions
    assert "rag.create_visual_pipeline" in canonical_actions
    assert "tools.create_or_update" in canonical_actions
    assert "artifacts.create" in canonical_actions
    assert "knowledge_stores.create_or_update" in canonical_actions
    assert "agents.create_shell" not in canonical_actions
    assert "rag.create_pipeline_shell" not in canonical_actions
    assert "agents.graph.apply_patch" not in canonical_actions
    assert "rag.graph.apply_patch" not in canonical_actions
    assert "prompts.list" not in canonical_actions
    assert "orchestration.join" not in canonical_actions


def test_platform_action_schema_is_direct_field():
    agents_create_schema = registry_seeding._build_platform_action_tool_schema("agents.create")
    agents_input = agents_create_schema["input"]

    assert "action" not in agents_input["properties"]
    assert "payload" not in agents_input["properties"]
    assert "dry_run" in agents_input["properties"]
    assert "validate_only" in agents_input["properties"]
    assert "idempotency_key" in agents_input["properties"]
    assert "request_metadata" in agents_input["properties"]
    assert agents_input["x-action-contract"]["action"] == "agents.create"
    assert agents_input["additionalProperties"] is False

    agents_update_schema = registry_seeding._build_platform_action_tool_schema("agents.update")["input"]
    assert "patch" not in agents_update_schema["properties"]
    assert "graph_definition" in agents_update_schema["properties"]
    assert "show_in_playground" in agents_update_schema["properties"]
    assert agents_update_schema["additionalProperties"] is False
    assert len(agents_update_schema["allOf"]) == 2

    agents_validate_schema = registry_seeding._build_platform_action_tool_schema("agents.validate")["input"]
    assert "validation" not in agents_validate_schema["properties"]
    assert agents_validate_schema["anyOf"] == [{"required": ["agent_id"]}, {"required": ["id"]}]

    tools_list_schema = registry_seeding._build_platform_action_tool_schema("tools.list")["input"]
    assert tools_list_schema["properties"]["view"]["enum"] == ["summary", "full"]
    assert tools_list_schema["properties"]["limit"]["maximum"] == 100

    rag_create_schema = registry_seeding._build_platform_action_tool_schema("rag.create_visual_pipeline")["input"]
    assert "graph_definition" not in rag_create_schema["properties"]
    assert set(rag_create_schema["required"]) == {"name", "nodes", "edges"}
    assert rag_create_schema["additionalProperties"] is False

    rag_update_schema = registry_seeding._build_platform_action_tool_schema("rag.update_visual_pipeline")["input"]
    assert "patch" not in rag_update_schema["properties"]
    assert "nodes" in rag_update_schema["properties"]
    assert "edges" in rag_update_schema["properties"]
    assert rag_update_schema["dependentRequired"] == {"nodes": ["edges"], "edges": ["nodes"]}
    assert len(rag_update_schema["allOf"]) == 2

    rag_create_job_schema = registry_seeding._build_platform_action_tool_schema("rag.create_job")["input"]
    assert rag_create_job_schema["required"] == ["executable_pipeline_id"]
    assert "input_params" in rag_create_job_schema["properties"]
    assert rag_create_job_schema["properties"]["input_params"]["type"] == "object"

    knowledge_store_list_schema = registry_seeding._build_platform_action_tool_schema("knowledge_stores.list")["input"]
    assert knowledge_store_list_schema["required"] == ["organization_id"]
    assert knowledge_store_list_schema["properties"]["view"]["enum"] == ["summary", "full"]


def test_platform_action_tools_bind_to_generated_action_functions():
    assert PLATFORM_ACTION_FUNCTIONS["agents.create"] == "platform_action_agents_create"
    assert PLATFORM_ACTION_FUNCTIONS["rag.create_visual_pipeline"] == "platform_action_rag_create_visual_pipeline"
    assert PLATFORM_ACTION_FUNCTIONS["artifacts.create"] == "platform_action_artifacts_create"
    assert PLATFORM_ACTION_FUNCTIONS["tools.create_or_update"] == "platform_action_tools_create_or_update"


@pytest.mark.asyncio
async def test_seed_platform_sdk_tool_creates_published_system_artifact_binding(db_session):
    tool = await registry_seeding.seed_platform_sdk_tool(db_session)
    await registry_seeding.seed_platform_sdk_tool(db_session)

    artifact = (
        await db_session.execute(select(Artifact).where(Artifact.system_key == "platform_sdk"))
    ).scalar_one()
    tool_rows = (
        await db_session.execute(
            select(ToolRegistry).where(
                ToolRegistry.organization_id.is_(None),
                ToolRegistry.builtin_key == "platform_sdk",
            )
        )
    ).scalars().all()

    assert len(tool_rows) == 1
    assert tool.id == tool_rows[0].id
    assert tool.implementation_type == ToolImplementationType.ARTIFACT
    assert tool.status == ToolStatus.PUBLISHED
    assert tool.is_system is True
    assert tool.artifact_id == str(artifact.id)
    assert tool.artifact_revision_id == artifact.latest_published_revision_id
    assert tool.config_schema["artifact_binding"]["system_key"] == "platform_sdk"


@pytest.mark.asyncio
async def test_seed_platform_architect_action_tools_creates_canonical_tool_rows(db_session):
    seeded = await registry_seeding.seed_platform_architect_action_tools(db_session)

    rows = (
        await db_session.execute(
            select(ToolRegistry).where(
                ToolRegistry.organization_id.is_(None),
                ToolRegistry.builtin_key.in_(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS),
            )
        )
    ).scalars().all()
    by_builtin_key = {row.builtin_key: row for row in rows}

    assert set(seeded.keys()) == set(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS)
    assert set(by_builtin_key.keys()) == set(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS)
    assert all(row.config_schema["implementation"]["function_name"] == PLATFORM_ACTION_FUNCTIONS[row.builtin_key] for row in rows)

    tool = by_builtin_key["agents.create"]
    assert tool.schema["input"]["properties"].get("action") is None
    assert tool.schema["input"]["properties"].get("payload") is None
    assert tool.schema["input"]["x-action-contract"]["action"] == "agents.create"


@pytest.mark.asyncio
async def test_seeded_platform_architect_mounts_only_canonical_action_and_worker_tools(db_session):
    suffix = uuid4().hex[:8]
    organization = Organization(name=f"Architect Org {suffix}", slug=f"architect-org-{suffix}")
    db_session.add(organization)
    await db_session.flush()

    project = Project(
        organization_id=organization.id,
        name="Default Project",
        slug=f"project-{uuid4().hex[:12]}",
        is_default=True,
    )
    db_session.add(project)

    model = (
        await db_session.execute(
            select(ModelRegistry).where(
                ModelRegistry.organization_id.is_(None),
                ModelRegistry.system_key == "grok-4-1-fast-reasoning",
            )
        )
    ).scalar_one_or_none()
    if model is None:
        model = ModelRegistry(
            organization_id=None,
            name="Architect Chat Model",
            system_key="grok-4-1-fast-reasoning",
            capability_type=ModelCapabilityType.CHAT,
            status=ModelStatus.ACTIVE,
            is_active=True,
            is_default=True,
        )
        db_session.add(model)
    await db_session.commit()

    agent = await registry_seeding.ensure_platform_architect_agent(
        db_session,
        organization.id,
        project_id=project.id,
    )
    assert isinstance(agent, Agent)

    mounted_tool_rows = (
        await db_session.execute(select(ToolRegistry).where(ToolRegistry.id.in_(agent.tools)))
    ).scalars().all()
    mounted_builtin_keys = {row.builtin_key for row in mounted_tool_rows}

    expected = set(registry_seeding.PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS) | set(
        registry_seeding.PLATFORM_ARCHITECT_CANONICAL_WORKER_TOOL_KEYS
    )
    assert mounted_builtin_keys == expected
    assert "platform-rag" not in mounted_builtin_keys
    assert "platform-agents" not in mounted_builtin_keys
    assert "platform-assets" not in mounted_builtin_keys
    assert "platform-governance" not in mounted_builtin_keys
    assert "agents.create_shell" not in mounted_builtin_keys
    assert "rag.create_pipeline_shell" not in mounted_builtin_keys
    assert "architect-worker-binding-get-state" not in mounted_builtin_keys
    assert "architect-worker-spawn-group" not in mounted_builtin_keys
