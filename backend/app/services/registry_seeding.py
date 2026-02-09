
import os
import json
from datetime import datetime
import uuid
from sqlalchemy import select, or_, text
from sqlalchemy.exc import ProgrammingError
from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderBinding,
    ModelCapabilityType,
    ModelProviderType,
    ToolRegistry,
    ToolDefinitionScope,
    ToolStatus,
    ToolImplementationType,
)
from app.db.postgres.models.identity import Tenant
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.orchestration import (
    OrchestratorPolicy,
    OrchestratorTargetAllowlist,
)


ARCHITECT_ORCHESTRATION_SCOPE_SUBSET = [
    "pipelines.catalog.read",
    "pipelines.write",
    "agents.write",
    "tools.write",
    "artifacts.write",
    "agents.execute",
    "agents.run_tests",
]

async def seed_global_models(db):
    """
    Seeds global models from a JSON file.
    Expects an AsyncSession.
    """
    # Use relative path from this file
    base_dir = os.path.dirname(os.path.dirname(__file__)) # back to app/
    json_path = os.path.join(base_dir, "db", "postgres", "seeds", "models.json")
    
    if not os.path.exists(json_path):
        print(f"Seed file not found at {json_path}")
        return

    with open(json_path, "r") as f:
        models_data = json.load(f)

    print(f"Syncing {len(models_data)} Global Model Definitions...")
    
    for m_def in models_data:
        # Check if model exists (Global)
        stmt = select(ModelRegistry).where(
            ModelRegistry.slug == m_def["slug"],
            ModelRegistry.tenant_id == None
        )
        res = await db.execute(stmt)
        model = res.scalars().first()
        
        # Map string to Enum
        try:
            capability = ModelCapabilityType[m_def["capability_type"].upper()]
        except KeyError:
            print(f"Unknown capability type: {m_def['capability_type']}")
            continue

        if not model:
            print(f"Creating model: {m_def['name']}...")
            model = ModelRegistry(
                tenant_id=None, # Global
                name=m_def["name"],
                slug=m_def["slug"],
                capability_type=capability,
                description=m_def["description"],
                metadata_=m_def.get("metadata", {}),
                is_active=True
            )
            db.add(model)
            await db.flush() # Get ID
        else:
            # Sync existing global model
            model.name = m_def["name"]
            model.description = m_def["description"]
            model.metadata_ = m_def.get("metadata", {})
        
        # Upsert global bindings
        for p_def in m_def.get("providers", []):
            try:
                provider_type = ModelProviderType[p_def["provider"].upper()]
            except KeyError:
                print(f"Unknown provider type: {p_def['provider']}")
                continue

            # Check for existing global binding
            b_stmt = select(ModelProviderBinding).where(
                ModelProviderBinding.model_id == model.id,
                ModelProviderBinding.provider == provider_type,
                ModelProviderBinding.provider_model_id == p_def["provider_model_id"],
                ModelProviderBinding.tenant_id == None
            )
            b_res = await db.execute(b_stmt)
            binding = b_res.scalars().first()
            
            config = {}
            if "variant" in p_def:
                config["provider_variant"] = p_def["variant"]

            if not binding:
                binding = ModelProviderBinding(
                    model_id=model.id,
                    tenant_id=None,
                    provider=provider_type,
                    provider_model_id=p_def["provider_model_id"],
                    priority=p_def.get("priority", 0),
                    config=config,
                    is_enabled=True
                )
                db.add(binding)
            else:
                binding.priority = p_def.get("priority", 0)
                binding.config = config

    await db.commit()
    print("Model Registry Sync Complete.")


async def _normalize_tool_status_values(db):
    """
    Align any lowercase tool status values with the uppercase ENUM literals
    used by the database. Safe for Postgres and SQLite.
    """
    mappings = {
        "draft": "DRAFT",
        "published": "PUBLISHED",
        "deprecated": "DEPRECATED",
        "disabled": "DISABLED",
    }
    for old, new in mappings.items():
        await db.execute(
            text("UPDATE tool_registry SET status=:new WHERE lower(status::text)=:old"),
            {"new": new, "old": old},
        )
    await db.commit()


async def _normalize_tool_impl_values(db):
    """
    Align lowercase implementation_type values with uppercase ENUM literals.
    """
    mappings = {
        "internal": "INTERNAL",
        "http": "HTTP",
        "rag_retrieval": "RAG_RETRIEVAL",
        "function": "FUNCTION",
        "custom": "CUSTOM",
        "artifact": "ARTIFACT",
        "mcp": "MCP",
    }
    for old, new in mappings.items():
        await db.execute(
            text("UPDATE tool_registry SET implementation_type=:new WHERE lower(implementation_type::text)=:old"),
            {"new": new, "old": old},
        )
    await db.commit()


async def seed_platform_sdk_tool(db):
    """
    Seeds the Platform SDK tool (artifact-backed, system tool).
    """
    # Ensure legacy lowercase statuses don't break enum deserialization
    await _normalize_tool_status_values(db)
    await _normalize_tool_impl_values(db)

    slug = "platform-sdk"
    tool = None
    tool_columns = await _get_table_columns(db, "tool_registry")
    if not tool_columns:
        print("Unable to inspect tool_registry columns; skipping Platform SDK tool seed.")
        return None
    required_cols = {
        "id",
        "tenant_id",
        "name",
        "slug",
        "description",
        "scope",
        "schema",
        "config_schema",
        "status",
        "version",
        "implementation_type",
        "published_at",
        "artifact_id",
        "artifact_version",
        "is_active",
        "is_system",
        "created_at",
        "updated_at",
    }
    use_orm = required_cols.issubset(tool_columns)
    enum_labels = await _get_enum_labels(db, "tooldefinitionscope")
    scope_value = _resolve_enum_value(enum_labels, "global")
    if enum_labels and scope_value not in {"global", "GLOBAL"}:
        scope_value = enum_labels[0]
    if enum_labels and "global" not in enum_labels:
        use_orm = False

    if use_orm:
        try:
            result = await db.execute(
                select(ToolRegistry).where(
                    ToolRegistry.slug == slug,
                    ToolRegistry.tenant_id == None,
                )
            )
            tool = result.scalar_one_or_none()
        except ProgrammingError:
            await db.rollback()
            use_orm = False

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "fetch_catalog",
                    "validate_plan",
                    "execute_plan",
                    "create_artifact_draft",
                    "promote_artifact",
                    "create_tool",
                    "run_agent",
                    "run_tests",
                    "respond",
                ],
            },
            "steps": {"type": "array", "items": {"type": "object"}},
            "tests": {"type": "array", "items": {"type": "object"}},
            "dry_run": {"type": "boolean"},
            "payload": {"type": "object"},
        },
        "required": ["action"],
        "additionalProperties": True,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "object"},
            "errors": {"type": "array", "items": {"type": "object"}},
        },
        "required": [],
        "additionalProperties": True,
    }
    schema = {"input": input_schema, "output": output_schema}

    config_schema = {
        "implementation": {
            "type": "artifact",
            "artifact_id": "builtin/platform_sdk",
            "artifact_version": "1.0.0",
        }
    }

    if use_orm:
        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name="Platform SDK",
                slug=slug,
                description="SDK-powered tool to fetch catalogs, create draft assets, and run multi-case tests.",
                scope=ToolDefinitionScope.GLOBAL,
                schema=schema,
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=ToolImplementationType.ARTIFACT,
                artifact_id="builtin/platform_sdk",
                artifact_version="1.0.0",
                is_active=True,
                is_system=True,
                published_at=datetime.utcnow(),
            )
            db.add(tool)
        else:
            tool.name = "Platform SDK"
            tool.description = "SDK-powered tool to fetch catalogs, create draft assets, and run multi-case tests."
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = schema
            tool.config_schema = config_schema
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = ToolImplementationType.ARTIFACT
            tool.artifact_id = "builtin/platform_sdk"
            tool.artifact_version = "1.0.0"
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.utcnow()

        await db.flush()
        await db.commit()
        return tool

    await db.rollback()
    return await _seed_platform_sdk_tool_legacy(db, schema, config_schema, tool_columns, scope_value)


async def seed_platform_architect_agent(db):
    """
    Seeds a tenant-scoped Platform Architect orchestrator and sub-agents (multi-agent flow).
    """
    # Prevent enum mismatches when loading tool references
    await _normalize_tool_status_values(db)
    await _normalize_tool_impl_values(db)

    tenant_result = await db.execute(select(Tenant).limit(1))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        print("No tenant found; skipping Platform Architect agent seed.")
        return None

    tool_id = await _get_platform_sdk_tool_id(db)
    if not tool_id:
        print("Platform SDK tool missing; skipping Platform Architect agent seed.")
        return None

    model_id = await _resolve_default_chat_model_id(db, tenant.id)
    if not model_id:
        print("No chat model available; skipping Platform Architect agent seed.")
        return None

    subagent_slugs = {
        "catalog": "architect-catalog",
        "planner": "architect-planner",
        "builder": "architect-builder",
        "coder": "architect-coder",
        "tester": "architect-tester",
    }

    graph_definition = _build_architect_graph_definition(tool_id, model_id, subagent_slugs)

    agent_columns = await _get_table_columns(db, "agents")
    minimal_agent_cols = {"id", "tenant_id", "name", "slug", "description", "graph_definition"}
    if not minimal_agent_cols.issubset(agent_columns):
        print("Agents table missing required columns; skipping Platform Architect agent seed.")
        return None

    full_agent_cols = {
        "id",
        "tenant_id",
        "name",
        "slug",
        "description",
        "graph_definition",
        "model_provider",
        "model_name",
        "temperature",
        "system_prompt",
        "tools",
        "referenced_model_ids",
        "referenced_tool_ids",
        "memory_config",
        "execution_constraints",
        "version",
        "status",
        "is_active",
        "is_public",
        "created_at",
        "updated_at",
        "published_at",
        "created_by",
    }

    use_orm = full_agent_cols.issubset(agent_columns)
    agent = None
    if use_orm:
        try:
            agent_result = await db.execute(
                select(Agent).where(
                    Agent.slug == "platform-architect",
                    Agent.tenant_id == tenant.id,
                )
            )
            agent = agent_result.scalar_one_or_none()
        except ProgrammingError:
            await db.rollback()
            use_orm = False

    if use_orm:
        subagents = await _seed_architect_subagents(db, tenant.id, model_id, tool_id, subagent_slugs)
        if agent is None:
            agent = Agent(
                tenant_id=tenant.id,
                name="Platform Architect",
                slug="platform-architect",
                description="GraphSpec v2 multi-agent orchestrator for platform architecture and draft execution.",
                graph_definition=graph_definition,
                tools=[],
                referenced_tool_ids=[],
                status=AgentStatus.published,
                is_active=True,
                is_public=False,
            )
            db.add(agent)
        else:
            agent.name = "Platform Architect"
            agent.description = "GraphSpec v2 multi-agent orchestrator for platform architecture and draft execution."
            agent.graph_definition = graph_definition
            agent.tools = []
            agent.referenced_tool_ids = []
            agent.status = AgentStatus.published
            agent.is_active = True
            agent.is_public = False

        await db.flush()
        await _seed_architect_orchestration_policy(
            db=db,
            tenant_id=tenant.id,
            orchestrator=agent,
            subagents=subagents,
            scope_subset=ARCHITECT_ORCHESTRATION_SCOPE_SUBSET,
        )
        await db.commit()
        return agent

    await db.rollback()
    return await _seed_platform_architect_agent_legacy(db, tenant.id, graph_definition, tool_id, agent_columns)


async def _resolve_default_chat_model_id(db, tenant_id):
    default_stmt = select(ModelRegistry).where(
        ModelRegistry.tenant_id == tenant_id,
        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
        ModelRegistry.is_default == True,
        ModelRegistry.is_active == True,
    )
    res = await db.execute(default_stmt)
    model = res.scalar_one_or_none()
    if model:
        return str(model.id)

    global_default_stmt = select(ModelRegistry).where(
        ModelRegistry.tenant_id == None,
        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
        ModelRegistry.is_default == True,
        ModelRegistry.is_active == True,
    )
    res = await db.execute(global_default_stmt)
    model = res.scalar_one_or_none()
    if model:
        return str(model.id)

    fallback_stmt = select(ModelRegistry).where(
        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
        ModelRegistry.is_active == True,
        or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id == None),
    )
    res = await db.execute(fallback_stmt)
    model = res.scalars().first()
    return str(model.id) if model else None


def _build_architect_graph_definition(_tool_id: str, model_id: str, subagent_slugs: dict | None = None) -> dict:
    slugs = subagent_slugs or {
        "catalog": "architect-catalog",
        "planner": "architect-planner",
        "builder": "architect-builder",
        "coder": "architect-coder",
        "tester": "architect-tester",
    }

    instructions = (
        "You are the Platform Architect final reporter. "
        f"This run delegates sub-agents via GraphSpec v2 orchestration nodes. Sub-agent slugs: catalog={slugs['catalog']}, "
        f"planner={slugs['planner']}, builder={slugs['builder']}, coder={slugs['coder']}, tester={slugs['tester']}. "
        "Read orchestration outcomes from state._node_outputs and summarize run health, child activity, and next draft-safe actions. "
        "Never claim publish/promote occurred unless explicitly shown in node outputs. "
        "Return JSON only."
    )

    output_schema = {
        "type": "object",
        "properties": {
            "notes": {"type": "string"},
            "orchestration_summary": {"type": "object"},
            "child_run_summary": {"type": "object"},
            "draft_assets": {"type": "object"},
            "next_actions": {"type": "array", "items": {"type": "string"}},
            "errors": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["notes"],
        "additionalProperties": True,
    }

    scope_subset = list(ARCHITECT_ORCHESTRATION_SCOPE_SUBSET)

    return {
        "spec_version": "2.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "spawn_catalog",
                "type": "spawn_run",
                "position": {"x": 220, "y": -120},
                "config": {
                    "target_agent_slug": slugs["catalog"],
                    "scope_subset": scope_subset,
                    "idempotency_key": "platform-architect:catalog:v2",
                    "failure_policy": "best_effort",
                    "timeout_s": 90,
                    "start_background": True,
                    "mapped_input_payload": {
                        "messages": [
                            {"role": "user", "content": "Fetch and summarize platform catalog capabilities as JSON."}
                        ],
                        "context": {"orchestrator_stage": "catalog"},
                    },
                },
            },
            {
                "id": "spawn_core_group",
                "type": "spawn_group",
                "position": {"x": 430, "y": -120},
                "config": {
                    "targets": [
                        {
                            "target_agent_slug": slugs["planner"],
                            "mapped_input_payload": {
                                "messages": [
                                    {"role": "user", "content": "Produce strict plan JSON for draft-only execution."}
                                ],
                                "context": {"orchestrator_role": "planner"},
                            },
                        },
                        {
                            "target_agent_slug": slugs["builder"],
                            "mapped_input_payload": {
                                "messages": [
                                    {"role": "user", "content": "Produce deploy-ready payload JSON from the plan."}
                                ],
                                "context": {"orchestrator_role": "builder"},
                            },
                        },
                        {
                            "target_agent_slug": slugs["coder"],
                            "mapped_input_payload": {
                                "messages": [
                                    {"role": "user", "content": "Draft missing artifacts/tools as JSON only."}
                                ],
                                "context": {"orchestrator_role": "coder"},
                            },
                        },
                        {
                            "target_agent_slug": slugs["tester"],
                            "mapped_input_payload": {
                                "messages": [
                                    {"role": "user", "content": "Run provided multi-case tests and return test report JSON."}
                                ],
                                "context": {"orchestrator_role": "tester"},
                            },
                        },
                    ],
                    "scope_subset": scope_subset,
                    "join_mode": "best_effort",
                    "failure_policy": "best_effort",
                    "timeout_s": 180,
                    "start_background": True,
                    "idempotency_key_prefix": "platform-architect:core-group:v2",
                },
            },
            {
                "id": "join_core_group",
                "type": "join",
                "position": {"x": 640, "y": -120},
                "config": {
                    "mode": "best_effort",
                    "timeout_s": 180,
                },
            },
            {
                "id": "judge_core",
                "type": "judge",
                "position": {"x": 850, "y": -220},
                "config": {
                    "outcomes": ["pass", "fail"],
                },
            },
            {
                "id": "replan_core",
                "type": "replan",
                "position": {"x": 850, "y": 10},
                "config": {},
            },
            {
                "id": "route_replan",
                "type": "router",
                "position": {"x": 1060, "y": 10},
                "config": {
                    "route_key": "suggested_action",
                    "routes": [
                        {"name": "replan", "match": "replan"},
                        {"name": "continue", "match": "continue"},
                    ],
                },
            },
            {
                "id": "spawn_replanner",
                "type": "spawn_run",
                "position": {"x": 1270, "y": -70},
                "config": {
                    "target_agent_slug": slugs["planner"],
                    "scope_subset": scope_subset,
                    "idempotency_key": "platform-architect:replanner:v2",
                    "failure_policy": "best_effort",
                    "timeout_s": 90,
                    "start_background": True,
                    "mapped_input_payload": {
                        "messages": [
                            {"role": "user", "content": "Produce a revised plan JSON after orchestration failure."}
                        ],
                        "context": {"orchestrator_stage": "replan"},
                    },
                },
            },
            {
                "id": "cancel_subtree",
                "type": "cancel_subtree",
                "position": {"x": 1270, "y": 110},
                "config": {
                    "include_root": False,
                    "reason": "platform_architect_orchestration_cleanup",
                },
            },
            {
                "id": "final_report",
                "type": "agent",
                "position": {"x": 1480, "y": 0},
                "config": {
                    "name": "Platform Architect Final Report",
                    "model_id": model_id,
                    "instructions": instructions,
                    "include_chat_history": True,
                    "reasoning_effort": "medium",
                    "output_format": "json",
                    "output_schema": output_schema,
                    "write_output_to_context": True,
                },
            },
            {"id": "end", "type": "end", "position": {"x": 1700, "y": 0}, "config": {"output_variable": "context"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "spawn_catalog", "type": "control"},
            {"id": "e2", "source": "spawn_catalog", "target": "spawn_core_group", "type": "control"},
            {"id": "e3", "source": "spawn_core_group", "target": "join_core_group", "type": "control"},
            {"id": "e4", "source": "join_core_group", "target": "judge_core", "type": "control", "source_handle": "completed"},
            {"id": "e5", "source": "join_core_group", "target": "judge_core", "type": "control", "source_handle": "completed_with_errors"},
            {"id": "e6", "source": "join_core_group", "target": "replan_core", "type": "control", "source_handle": "failed"},
            {"id": "e7", "source": "join_core_group", "target": "cancel_subtree", "type": "control", "source_handle": "timed_out"},
            {"id": "e8", "source": "join_core_group", "target": "join_core_group", "type": "control", "source_handle": "pending"},
            {"id": "e9", "source": "judge_core", "target": "final_report", "type": "control", "source_handle": "pass"},
            {"id": "e10", "source": "judge_core", "target": "replan_core", "type": "control", "source_handle": "fail"},
            {"id": "e11", "source": "replan_core", "target": "route_replan", "type": "control", "source_handle": "replan"},
            {"id": "e12", "source": "replan_core", "target": "final_report", "type": "control", "source_handle": "continue"},
            {"id": "e13", "source": "route_replan", "target": "spawn_replanner", "type": "control", "source_handle": "replan"},
            {"id": "e14", "source": "route_replan", "target": "final_report", "type": "control", "source_handle": "continue"},
            {"id": "e15", "source": "route_replan", "target": "final_report", "type": "control", "source_handle": "default"},
            {"id": "e16", "source": "spawn_replanner", "target": "cancel_subtree", "type": "control"},
            {"id": "e17", "source": "cancel_subtree", "target": "final_report", "type": "control"},
            {"id": "e18", "source": "final_report", "target": "end", "type": "control"},
        ],
    }


def _build_architect_subagent_graph(
    model_id: str,
    instructions: str,
    output_schema: dict | None = None,
    tools: list | None = None,
) -> dict:
    config = {
        "name": "Architect Sub-Agent",
        "model_id": model_id,
        "instructions": instructions,
        "include_chat_history": True,
        "reasoning_effort": "medium",
        "output_format": "json",
        "write_output_to_context": True,
    }
    if output_schema:
        config["output_schema"] = output_schema
    if tools:
        config["tools"] = tools

    return {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "agent", "type": "agent", "position": {"x": 200, "y": 0}, "config": config},
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {"output_variable": "context"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "agent", "type": "control"},
            {"id": "e2", "source": "agent", "target": "end", "type": "control"},
        ],
    }


def _build_architect_subagent_specs(tool_id: str, model_id: str, slugs: dict) -> list[dict]:
    catalog_schema = {
        "type": "object",
        "properties": {"catalog": {"type": "object"}, "notes": {"type": "string"}},
        "required": ["catalog"],
        "additionalProperties": True,
    }
    planner_schema = {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "object"}},
            "tests": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["actions"],
        "additionalProperties": True,
    }
    builder_schema = {
        "type": "object",
        "properties": {
            "actions": {"type": "array", "items": {"type": "object"}},
            "notes": {"type": "string"},
        },
        "required": ["actions"],
        "additionalProperties": True,
    }
    coder_schema = {
        "type": "object",
        "properties": {
            "artifacts": {"type": "array", "items": {"type": "object"}},
            "tools": {"type": "array", "items": {"type": "object"}},
            "notes": {"type": "string"},
        },
        "additionalProperties": True,
    }
    tester_schema = {
        "type": "object",
        "properties": {
            "tests": {"type": "array", "items": {"type": "object"}},
            "summary": {"type": "object"},
        },
        "additionalProperties": True,
    }

    return [
        {
            "slug": slugs["catalog"],
            "name": "Architect Catalog",
            "description": "Catalog/Introspector sub-agent for the Platform Architect.",
            "tools": [tool_id],
            "graph_definition": _build_architect_subagent_graph(
                model_id=model_id,
                instructions=(
                    "You are the Catalog/Introspector. Use the Platform SDK tool to call action \"fetch_catalog\" "
                    "exactly once and summarize available RAG/Agent capabilities. Do not call fetch_catalog repeatedly. "
                    "If fetch fails once, return an error JSON and stop. Return JSON with key \"catalog\" and optional notes. "
                    "Output JSON only."
                ),
                output_schema=catalog_schema,
                tools=[tool_id],
            ),
        },
        {
            "slug": slugs["planner"],
            "name": "Architect Planner",
            "description": "Planner sub-agent producing Plan JSON for the Platform Architect.",
            "tools": [],
            "graph_definition": _build_architect_subagent_graph(
                model_id=model_id,
                instructions=(
                    "You are the Planner. Produce a strict Plan JSON with actions and tests. "
                    "Use action types: create_artifact_draft, promote_artifact, create_tool, deploy_agent, deploy_rag_pipeline, run_tests. "
                    "Output JSON only."
                ),
                output_schema=planner_schema,
            ),
        },
        {
            "slug": slugs["builder"],
            "name": "Architect Builder",
            "description": "Builder sub-agent producing deploy payloads for agents and pipelines.",
            "tools": [],
            "graph_definition": _build_architect_subagent_graph(
                model_id=model_id,
                instructions=(
                    "You are the Builder. Convert Plan actions into executable payloads for deploy_agent and deploy_rag_pipeline. "
                    "Return JSON with key \"actions\" containing ready-to-execute payloads. Output JSON only."
                ),
                output_schema=builder_schema,
            ),
        },
        {
            "slug": slugs["coder"],
            "name": "Architect Coder",
            "description": "Coder sub-agent drafting artifacts and tools for missing capabilities.",
            "tools": [],
            "graph_definition": _build_architect_subagent_graph(
                model_id=model_id,
                instructions=(
                    "You are the Coder. Draft artifact/tool definitions for missing capabilities. "
                    "Return JSON with keys \"artifacts\" and \"tools\". Output JSON only."
                ),
                output_schema=coder_schema,
            ),
        },
        {
            "slug": slugs["tester"],
            "name": "Architect Tester",
            "description": "Tester sub-agent executing multi-case tests via the Platform SDK tool.",
            "tools": [tool_id],
            "graph_definition": _build_architect_subagent_graph(
                model_id=model_id,
                instructions=(
                    "You are the Tester. Use the Platform SDK tool action \"run_tests\" to execute the provided test suite. "
                    "Return the test report JSON. Output JSON only."
                ),
                output_schema=tester_schema,
                tools=[tool_id],
            ),
        },
    ]


async def _seed_architect_subagents(db, tenant_id, model_id, tool_id, slugs: dict) -> dict[str, Agent]:
    specs = _build_architect_subagent_specs(tool_id, model_id, slugs)
    seeded: dict[str, Agent] = {}
    for spec in specs:
        slug = spec["slug"]
        tools = spec.get("tools") or []
        result = await db.execute(
            select(Agent).where(Agent.slug == slug, Agent.tenant_id == tenant_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            agent = Agent(
                tenant_id=tenant_id,
                name=spec["name"],
                slug=slug,
                description=spec["description"],
                graph_definition=spec["graph_definition"],
                tools=tools,
                referenced_tool_ids=tools,
                status=AgentStatus.published,
                is_active=True,
                is_public=False,
            )
            db.add(agent)
        else:
            agent.name = spec["name"]
            agent.description = spec["description"]
            agent.graph_definition = spec["graph_definition"]
            agent.tools = tools
            agent.referenced_tool_ids = tools
            agent.status = AgentStatus.published
            agent.is_active = True
            agent.is_public = False
        seeded[slug] = agent

    await db.flush()
    return seeded


async def _seed_architect_orchestration_policy(
    *,
    db,
    tenant_id,
    orchestrator: Agent,
    subagents: dict[str, Agent],
    scope_subset: list[str],
) -> None:
    policy_columns = await _get_table_columns(db, "orchestrator_policies")
    allowlist_columns = await _get_table_columns(db, "orchestrator_target_allowlists")
    if not policy_columns or not allowlist_columns:
        print("Orchestration policy tables are missing; skipping Platform Architect policy seed.")
        return

    policy_res = await db.execute(
        select(OrchestratorPolicy).where(
            OrchestratorPolicy.tenant_id == tenant_id,
            OrchestratorPolicy.orchestrator_agent_id == orchestrator.id,
        )
    )
    policy = policy_res.scalar_one_or_none()
    if policy is None:
        policy = OrchestratorPolicy(
            tenant_id=tenant_id,
            orchestrator_agent_id=orchestrator.id,
            is_active=True,
            enforce_published_only=True,
            default_failure_policy="best_effort",
            max_depth=3,
            max_fanout=8,
            max_children_total=32,
            join_timeout_s=180,
            allowed_scope_subset=list(scope_subset),
            capability_manifest_version=2,
        )
        db.add(policy)
    else:
        policy.is_active = True
        policy.enforce_published_only = True
        policy.default_failure_policy = "best_effort"
        policy.max_depth = 3
        policy.max_fanout = 8
        policy.max_children_total = 32
        policy.join_timeout_s = 180
        policy.allowed_scope_subset = list(scope_subset)
        policy.capability_manifest_version = 2

    await db.flush()

    expected_targets = {
        slug: agent
        for slug, agent in (subagents or {}).items()
        if agent is not None
    }
    for slug, target in expected_targets.items():
        entry_res = await db.execute(
            select(OrchestratorTargetAllowlist).where(
                OrchestratorTargetAllowlist.tenant_id == tenant_id,
                OrchestratorTargetAllowlist.orchestrator_agent_id == orchestrator.id,
                or_(
                    OrchestratorTargetAllowlist.target_agent_id == target.id,
                    OrchestratorTargetAllowlist.target_agent_slug == slug,
                ),
            )
        )
        entry = entry_res.scalar_one_or_none()
        if entry is None:
            entry = OrchestratorTargetAllowlist(
                tenant_id=tenant_id,
                orchestrator_agent_id=orchestrator.id,
                target_agent_id=target.id,
                target_agent_slug=slug,
                is_active=True,
            )
            db.add(entry)
        else:
            entry.target_agent_id = target.id
            entry.target_agent_slug = slug
            entry.is_active = True

    await db.flush()


async def _get_table_columns(db, table_name: str) -> set:
    try:
        result = await db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        cols = {row[0] for row in result.all()}
        if cols:
            return cols
    except Exception:
        cols = set()

    # SQLite fallback
    try:
        result = await db.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in result.all()}
    except Exception:
        return set()


async def _seed_platform_sdk_tool_legacy(db, schema: dict, config_schema: dict, columns: set, scope_value: str):
    if not columns:
        print("No tool_registry columns available; skipping legacy Platform SDK seed.")
        return None
    slug = "platform-sdk"
    name = "Platform SDK"
    description = "SDK-powered tool to fetch catalogs, create draft assets, and run multi-case tests."
    now = datetime.utcnow()
    tool_status_labels = await _get_enum_labels(db, "toolstatus")
    impl_labels = await _get_enum_labels(db, "toolimplementationtype")
    status_value = _resolve_enum_value(tool_status_labels, "published")
    impl_value = _resolve_enum_value(impl_labels, "artifact")

    where_clause = "slug = :slug"
    if "tenant_id" in columns:
        where_clause += " AND tenant_id IS NULL"

    select_sql = f"SELECT id FROM tool_registry WHERE {where_clause} LIMIT 1"
    result = await db.execute(text(select_sql), {"slug": slug})
    row = result.first()

    values = {
        "id": uuid.uuid4(),
        "tenant_id": None,
        "name": name,
        "slug": slug,
        "description": description,
        "scope": scope_value,
        "schema": schema,
        "config_schema": config_schema,
        "status": status_value,
        "version": "1.0.0",
        "implementation_type": impl_value,
        "published_at": now,
        "artifact_id": "builtin/platform_sdk",
        "artifact_version": "1.0.0",
        "is_active": True,
        "is_system": True,
        "created_at": now,
        "updated_at": now,
    }

    filtered = {k: v for k, v in values.items() if k in columns}
    filtered = _coerce_json_columns(filtered)
    if not filtered:
        print("No compatible tool_registry columns found; skipping legacy Platform SDK seed.")
        return None

    if row:
        tool_id = row[0]
        updates = []
        for key in filtered.keys():
            if key in {"id", "slug", "tenant_id", "created_at"}:
                continue
            updates.append(f"{key} = :{key}")
        if updates:
            update_sql = f"UPDATE tool_registry SET {', '.join(updates)} WHERE id = :id"
            params = {**filtered, "id": tool_id}
            await db.execute(text(update_sql), params)
        await db.commit()
        return {"id": tool_id}

    columns_list = list(filtered.keys())
    placeholders = [f":{col}" for col in columns_list]
    insert_sql = f"INSERT INTO tool_registry ({', '.join(columns_list)}) VALUES ({', '.join(placeholders)})"
    await db.execute(text(insert_sql), filtered)
    await db.commit()
    return {"id": filtered.get("id")}


async def _get_platform_sdk_tool_id(db) -> str | None:
    tool_columns = await _get_table_columns(db, "tool_registry")
    where_clause = "slug = :slug"
    if "tenant_id" in tool_columns:
        where_clause += " AND tenant_id IS NULL"

    try:
        if {"id", "slug"}.issubset(tool_columns):
            result = await db.execute(text(f"SELECT id FROM tool_registry WHERE {where_clause} LIMIT 1"), {"slug": "platform-sdk"})
            row = result.first()
            return str(row[0]) if row else None
    except Exception:
        return None

    return None


async def _seed_platform_architect_agent_legacy(
    db,
    tenant_id,
    graph_definition: dict,
    tool_id: str,
    columns: set,
):
    slug = "platform-architect"
    name = "Platform Architect"
    description = "Meta-agent that designs and deploys pipelines and agents."
    now = datetime.utcnow()

    where_clause = "slug = :slug"
    if "tenant_id" in columns:
        where_clause += " AND tenant_id = :tenant_id"

    select_sql = f"SELECT id FROM agents WHERE {where_clause} LIMIT 1"
    params = {"slug": slug}
    if "tenant_id" in columns:
        params["tenant_id"] = tenant_id
    result = await db.execute(text(select_sql), params)
    row = result.first()

    values = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "name": name,
        "slug": slug,
        "description": description,
        "graph_definition": graph_definition,
        "tools": [],
        "referenced_tool_ids": [],
        "status": "published",
        "is_active": True,
        "is_public": False,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "published_at": now,
        "memory_config": {},
        "execution_constraints": {},
        "referenced_model_ids": [],
    }

    filtered = {k: v for k, v in values.items() if k in columns}
    filtered = _coerce_json_columns(filtered)
    if not filtered:
        print("No compatible agents columns found; skipping legacy Platform Architect seed.")
        return None

    if row:
        agent_id = row[0]
        updates = []
        for key in filtered.keys():
            if key in {"id", "slug", "tenant_id", "created_at"}:
                continue
            updates.append(f"{key} = :{key}")
        if updates:
            update_sql = f"UPDATE agents SET {', '.join(updates)} WHERE id = :id"
            params = {**filtered, "id": agent_id}
            await db.execute(text(update_sql), params)
        await db.commit()
        return {"id": agent_id}

    columns_list = list(filtered.keys())
    placeholders = [f":{col}" for col in columns_list]
    insert_sql = f"INSERT INTO agents ({', '.join(columns_list)}) VALUES ({', '.join(placeholders)})"
    await db.execute(text(insert_sql), filtered)
    await db.commit()
    return {"id": filtered.get("id")}


def _coerce_json_columns(values: dict) -> dict:
    json_columns = {
        "schema",
        "config_schema",
        "graph_definition",
        "tools",
        "referenced_tool_ids",
        "referenced_model_ids",
        "memory_config",
        "execution_constraints",
    }
    coerced = {}
    for key, value in values.items():
        if key in json_columns and isinstance(value, (dict, list)):
            coerced[key] = json.dumps(value)
        else:
            coerced[key] = value
    return coerced


async def _get_enum_labels(db, enum_name: str) -> list:
    try:
        result = await db.execute(
            text(
                """
                SELECT e.enumlabel
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = :enum_name
                ORDER BY e.enumsortorder
                """
            ),
            {"enum_name": enum_name},
        )
        return [row[0] for row in result.all()]
    except Exception:
        return []


def _resolve_enum_value(labels: list, preferred: str) -> str:
    if not labels:
        return preferred
    if preferred in labels:
        return preferred
    upper = preferred.upper()
    if upper in labels:
        return upper
    lower = preferred.lower()
    if lower in labels:
        return lower
    return labels[0]
