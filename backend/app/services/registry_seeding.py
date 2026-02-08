
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
        await _seed_architect_subagents(db, tenant.id, model_id, tool_id, subagent_slugs)
        if agent is None:
            agent = Agent(
                tenant_id=tenant.id,
                name="Platform Architect",
                slug="platform-architect",
                description="Meta-agent that designs and deploys pipelines and agents.",
                graph_definition=graph_definition,
                tools=[tool_id],
                referenced_tool_ids=[tool_id],
                status=AgentStatus.published,
                is_active=True,
                is_public=False,
            )
            db.add(agent)
        else:
            agent.name = "Platform Architect"
            agent.description = "Meta-agent that designs and deploys pipelines and agents."
            agent.graph_definition = graph_definition
            agent.tools = [tool_id]
            agent.referenced_tool_ids = [tool_id]
            agent.status = AgentStatus.published
            agent.is_active = True
            agent.is_public = False

        await db.flush()
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


def _build_architect_graph_definition(tool_id: str, model_id: str, subagent_slugs: dict | None = None) -> dict:
    slugs = subagent_slugs or {
        "catalog": "architect-catalog",
        "planner": "architect-planner",
        "builder": "architect-builder",
        "coder": "architect-coder",
        "tester": "architect-tester",
    }

    instructions = (
        "You are the Platform Architect Orchestrator. Coordinate sub-agents via the Platform SDK tool. "
        f"Sub-agent slugs: catalog={slugs['catalog']}, planner={slugs['planner']}, builder={slugs['builder']}, "
        f"coder={slugs['coder']}, tester={slugs['tester']}. "
        "Strict execution policy: "
        "(A) call fetch_catalog at most once per run, "
        "(B) never repeat the same tool call with identical arguments, "
        "(C) after any tool error, stop and return a final error JSON instead of retry loops, "
        "(D) never ask for requirements if the user already gave enough detail for a minimal agent. "
        "Workflow for build requests: "
        "(1) fetch_catalog once, "
        "(2) planner produces Plan JSON, "
        "(3) execute_plan for draft-only creation, "
        "(4) optional run_tests if tests were provided, "
        "(5) return final JSON and stop. "
        "Workflow for capability questions: "
        "fetch_catalog once, summarize capabilities, return final JSON and stop. "
        "Use tool calls with JSON arguments like: "
        "{\"action\": \"run_agent\", \"payload\": {\"agent_slug\": \"...\", \"input\": {\"text\": \"...\", \"context\": {...}}}}. "
        "All creations must stay in DRAFT status unless explicitly requested to publish/promote. "
        "Return JSON only. Do not output prose outside JSON."
    )

    output_schema = {
        "type": "object",
        "properties": {
            "notes": {"type": "string"},
            "capabilities": {"type": "object"},
            "draft_assets": {"type": "object"},
            "plan_validation": {"type": "object"},
            "test_report": {"type": "object"},
            "errors": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["notes"],
        "additionalProperties": True,
    }

    return {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "orchestrator",
                "type": "agent",
                "position": {"x": 200, "y": 0},
                "config": {
                    "name": "Platform Architect Orchestrator",
                    "model_id": model_id,
                    "instructions": instructions,
                    "include_chat_history": True,
                    "reasoning_effort": "medium",
                    "output_format": "json",
                    "output_schema": output_schema,
                    "write_output_to_context": True,
                    "tools": [tool_id],
                },
            },
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {"output_variable": "context"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "orchestrator", "type": "control"},
            {"id": "e2", "source": "orchestrator", "target": "end", "type": "control"},
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


async def _seed_architect_subagents(db, tenant_id, model_id, tool_id, slugs: dict) -> None:
    specs = _build_architect_subagent_specs(tool_id, model_id, slugs)
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

    await db.flush()
    await db.commit()


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
        "tools": [tool_id],
        "referenced_tool_ids": [tool_id],
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
