import pytest
from sqlalchemy import select

from app.services import registry_seeding
from app.db.postgres.models.artifact_runtime import Artifact
from app.db.postgres.models.registry import ToolImplementationType, ToolRegistry, ToolStatus
from app.services.platform_native_tools import PLATFORM_NATIVE_FUNCTIONS


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
    instructions = runtime_node["config"]["instructions"]
    assert "Never call architect.run" in instructions
    assert "architect-worker-spawn" in instructions
    assert "architect-worker-binding-prepare" in instructions
    assert "architect-worker-binding-persist-artifact" in instructions
    assert "architect-worker-await" in instructions
    assert "architect-worker-respond" in instructions
    assert "platform-governance does not expose raw orchestration.spawn_* actions" in instructions
    assert "answer with canonical action ids under each domain" in instructions
    assert "must not end the run after spawn/join alone" in instructions
    assert "Do not treat successful worker completion as task completion by itself" in instructions
    assert "Never burn tool iterations on repeated immediate architect-worker-get-run calls" in instructions
    assert "Do not invent nested fields like task.instructions" in instructions
    assert "agents.create_shell" in instructions
    assert "rag.create_pipeline_shell" in instructions
    assert "treat platform tools as canonical action ids" in instructions
    assert "If the user asks to list platform tools available right now" in instructions
    assert "prefer canonical shell/create_or_update actions over invented *.create aliases" in instructions
    assert "default the resource label field to payload.name" in instructions
    assert "Do not default to display_name" in instructions
    assert "use payload.name and optional payload.pipeline_type=retrieval only" in instructions
    assert "do not send kind, template, display_name, nodes, edges, or graph_definition on the shell action" in instructions
    assert "payload.name and payload.embedding_model_id are required" in instructions
    assert "choose an active embedding-capable model" in instructions
    assert "create_new_draft requires title_prompt plus draft_seed" in instructions
    assert "return canonical action ids grouped under each platform domain" in instructions
    assert "Do not invent help/list-schema actions against platform domains" in instructions
    assert "draft_seed.kind" in instructions
    assert "draft_seed.language" in instructions
    assert "Language selection belongs to create flow only" in instructions
    assert "Do not construct a full draft_snapshot for normal artifact creation" in instructions
    assert "top-level action and payload" in instructions
    assert "Never wrap a tool call inside query, text, value" in instructions
    assert "Artifact-coding delegated workers edit the shared draft only" in instructions
    assert "artifact_coding_list_credentials" in instructions
    assert "exact @{credential-id} string literals" in instructions
    assert "create or update a tool_impl artifact" in instructions
    assert "publish the tool so it pins artifact_revision_id" in instructions
    assert "use platform-assets with action prompts.list" in instructions
    assert "If the user says prompt assets, prompt templates, or prompt library entries" in instructions
    assert "Do not query artifacts.list for fake kinds like prompt or prompt_template" in instructions
    assert "Do not ask a worker to mutate runtime-owned fields like persistence_readiness" in instructions
    assert "agents.graph.add_tool_to_agent_node" in instructions
    assert "payload.tool_id must be the actual tool row UUID" in instructions
    assert "resolve the row first with tools.list or tools.get" in instructions
    assert "payload.node_id plus a concrete payload.model_id chosen from models.list" in instructions
    assert "the array field is payload.operations, not payload.patch" in instructions
    assert "use canonical agents.execute or agents.start_run" in instructions
    assert "poll agents.get_run until the target run reaches a terminal state" in instructions
    assert "Do not use architect-worker-await for ordinary agent run ids or pipeline job ids" in instructions
    assert "use rag.create_job with payload.executable_pipeline_id plus payload.input_params only" in instructions
    assert "do not use payload.pipeline_id, payload.id, payload.input" in instructions
    assert "call rag.get_executable_input_schema first and map payload.input_params to the returned step-id shape" in instructions
    assert "poll rag.get_job until the job reaches a terminal state" in instructions
    assert "rag.operators.catalog" in instructions
    assert "rag.operators.schema" in instructions
    assert "Draft-first is mandatory" in instructions
    assert "Never ask the user for organization_id" in instructions
    assert "machine-readable JSON report" not in instructions
    assert "output_format" not in runtime_node["config"]
    assert "output_schema" not in runtime_node["config"]


def test_platform_architect_domain_tool_specs_are_seeded():
    slugs = set(registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS.keys())
    assert slugs == {
        "platform-rag",
        "platform-agents",
        "platform-assets",
        "platform-governance",
    }
    assert "architect.run" not in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-agents"]["actions"]


def test_platform_architect_domain_tools_bind_to_native_platform_functions():
    for slug in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS:
        function_name = PLATFORM_NATIVE_FUNCTIONS[slug]
        assert function_name.startswith("platform_native_")


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


def test_platform_domain_schema_is_action_specific_one_of():
    agents_spec = registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-agents"]
    agents_schema = registry_seeding._build_platform_domain_tool_schema("platform-agents", agents_spec)
    input_schema = agents_schema["input"]
    variants = input_schema["oneOf"]
    by_action = {variant["properties"]["action"]["const"]: variant for variant in variants}

    assert "agents.create" in by_action
    assert "agents.create_shell" in by_action
    assert "agents.graph.add_tool_to_agent_node" in by_action
    assert "agents.nodes.catalog" in by_action
    assert "agents.nodes.schema" in by_action
    assert "agents.nodes.validate" in by_action
    assert "rag.operators.catalog" in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-rag"]["actions"]
    assert "rag.operators.schema" in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-rag"]["actions"]
    assert "rag.create_pipeline_shell" in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-rag"]["actions"]
    assert "rag.create_job" in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-rag"]["actions"]
    assert "agents.publish" in by_action
    assert "rag.graph.apply_patch" in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-rag"]["actions"]
    assert "architect.run" not in by_action
    assert "x-action-contract" in by_action["agents.create"]
    assert "idempotency_key" not in by_action["agents.create"]["required"]
    assert "request_metadata" not in by_action["agents.create"]["required"]
    assert "organization_id" not in by_action["agents.create"]["required"]
    assert "node_types" in by_action["agents.nodes.schema"]["properties"]["payload"]["required"]
    assert "idempotency_key" not in by_action["agents.nodes.catalog"]["required"]
    assert "idempotency_key" not in by_action["agents.get"]["required"]

    agents_list_payload = by_action["agents.list"]["properties"]["payload"]
    assert "compact" not in agents_list_payload["properties"]
    assert agents_list_payload["properties"]["view"]["enum"] == ["summary", "full"]
    assert agents_list_payload["properties"]["limit"]["maximum"] == 100

    assets_spec = registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-assets"]
    assets_schema = registry_seeding._build_platform_domain_tool_schema("platform-assets", assets_spec)
    assets_variants = assets_schema["input"]["oneOf"]
    assets_by_action = {variant["properties"]["action"]["const"]: variant for variant in assets_variants}

    models_list_payload = assets_by_action["models.list"]["properties"]["payload"]
    assert models_list_payload["properties"]["view"]["enum"] == ["summary", "full"]
    assert models_list_payload["properties"]["status"]["type"] == "string"
    assert models_list_payload["properties"]["limit"]["maximum"] == 100

    prompts_list_payload = assets_by_action["prompts.list"]["properties"]["payload"]
    assert prompts_list_payload["properties"]["view"]["enum"] == ["summary", "full"]
    assert prompts_list_payload["properties"]["status"]["enum"] == ["active", "archived"]
    assert prompts_list_payload["properties"]["limit"]["maximum"] == 100

    tools_list_payload = assets_by_action["tools.list"]["properties"]["payload"]
    assert tools_list_payload["properties"]["view"]["enum"] == ["summary", "full"]
    assert tools_list_payload["properties"]["name"]["type"] == "string"
    assert "status" in tools_list_payload["properties"]
    assert "implementation_type" in tools_list_payload["properties"]

    tools_get_payload = assets_by_action["tools.get"]["properties"]["payload"]
    assert set(tools_get_payload["properties"].keys()) == {"id", "tool_id"}

    rag_create_job_payload = registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-rag"]["actions"]["rag.create_job"]["payload_schema"]
    assert rag_create_job_payload["required"] == ["executable_pipeline_id"]
    assert "tenant_slug" not in rag_create_job_payload["required"]
    assert rag_create_job_payload["properties"]["input_params"]["type"] == "object"

    knowledge_stores_list_payload = assets_by_action["knowledge_stores.list"]["properties"]["payload"]
    assert knowledge_stores_list_payload["required"] == ["organization_id"]
    assert knowledge_stores_list_payload["properties"]["view"]["enum"] == ["summary", "full"]
