
import os
import json
from pathlib import Path
from datetime import datetime
import uuid
from sqlalchemy import select, or_, text
from sqlalchemy.exc import ProgrammingError
from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderBinding,
    ModelCapabilityType,
    ModelProviderType,
    set_tool_management_metadata,
    ToolRegistry,
    ToolDefinitionScope,
    ToolStatus,
    ToolImplementationType,
)
from app.db.postgres.models.artifact_runtime import ArtifactKind, ArtifactOwnerType
from app.db.postgres.models.identity import Tenant
from app.db.postgres.models.agents import Agent, AgentStatus
from app.services.builtin_tools import BUILTIN_TEMPLATE_SPECS, is_builtin_tools_v1_enabled
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.platform_architect_contracts import (
    PLATFORM_ARCHITECT_DOMAIN_TOOLS,
    build_architect_graph_definition,
    build_platform_domain_tool_schema,
)
from app.services.platform_architect_worker_tools import (
    ensure_platform_architect_worker_orchestration_policy,
    ensure_platform_architect_worker_tools,
)
from app.services.platform_native_tools import PLATFORM_NATIVE_FUNCTIONS
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile

# Backward-compatible exports for tests and internal callers.
_build_architect_graph_definition = build_architect_graph_definition
_build_platform_domain_tool_schema = build_platform_domain_tool_schema

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
    labels = await _get_enum_labels(db, "toolstatus")
    for old in ("draft", "published", "deprecated", "disabled"):
        new = _resolve_enum_value(labels, old)
        try:
            await db.execute(
                text("UPDATE tool_registry SET status=:new WHERE lower(status::text)=:old"),
                {"new": new, "old": old},
            )
        except Exception:
            await db.execute(
                text("UPDATE tool_registry SET status=:new WHERE lower(status)=:old"),
                {"new": new, "old": old},
            )
    await db.commit()


async def _normalize_tool_impl_values(db):
    """
    Align lowercase implementation_type values with uppercase ENUM literals.
    """
    labels = await _get_enum_labels(db, "toolimplementationtype")
    replacements = {
        "internal": "internal",
        "http": "http",
        "rag_retrieval": "rag_pipeline",
        "rag_pipeline": "rag_pipeline",
        "agent_call": "agent_call",
        "function": "function",
        "custom": "custom",
        "artifact": "artifact",
        "mcp": "mcp",
    }
    for old, preferred in replacements.items():
        new = _resolve_enum_value(labels, old)
        if old == "rag_retrieval":
            new = _resolve_enum_value(labels, preferred)
        try:
            await db.execute(
                text("UPDATE tool_registry SET implementation_type=:new WHERE lower(implementation_type::text)=:old"),
                {"new": new, "old": old},
            )
        except Exception:
            await db.execute(
                text("UPDATE tool_registry SET implementation_type=:new WHERE lower(implementation_type)=:old"),
                {"new": new, "old": old},
            )
    await db.commit()


async def seed_platform_sdk_tool(db):
    """Seed the Platform SDK system artifact and the global tool that binds to it."""
    await _normalize_tool_status_values(db)
    await _normalize_tool_impl_values(db)

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Canonical platform-sdk action id. The runtime validates the concrete action contract.",
                "examples": [
                    "artifacts.create",
                    "artifacts.update",
                    "artifacts.publish",
                    "tools.create_or_update",
                    "agents.execute",
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

    artifact = await _seed_platform_sdk_system_artifact(
        db,
        input_schema=input_schema,
        output_schema=output_schema,
    )

    result = await db.execute(
        select(ToolRegistry).where(
            ToolRegistry.slug == "platform-sdk",
            ToolRegistry.tenant_id == None,
        )
    )
    tool = result.scalars().first()

    config_schema = {
        "artifact_binding": {
            "artifact_id": str(artifact.id),
            "revision_id": str(artifact.latest_published_revision_id),
            "system_key": "platform_sdk",
        }
    }

    if tool is None:
        tool = ToolRegistry(
            tenant_id=None,
            name="Platform SDK",
            slug="platform-sdk",
            description="SDK-powered tool to fetch catalogs, create draft assets, and run multi-case tests.",
            scope=ToolDefinitionScope.GLOBAL,
            schema=schema,
            config_schema=config_schema,
            status=ToolStatus.PUBLISHED,
            version="1.0.0",
            implementation_type=ToolImplementationType.ARTIFACT,
            artifact_id=str(artifact.id),
            artifact_version=None,
            artifact_revision_id=artifact.latest_published_revision_id,
            builtin_key="platform_sdk",
            builtin_template_id=None,
            is_builtin_template=False,
            is_active=True,
            is_system=True,
            published_at=datetime.utcnow(),
        )
        set_tool_management_metadata(tool, ownership="system")
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
        tool.artifact_id = str(artifact.id)
        tool.artifact_version = None
        tool.artifact_revision_id = artifact.latest_published_revision_id
        tool.builtin_key = "platform_sdk"
        tool.builtin_template_id = None
        tool.is_builtin_template = False
        tool.is_active = True
        tool.is_system = True
        tool.published_at = tool.published_at or datetime.utcnow()
        set_tool_management_metadata(tool, ownership="system")

    await db.flush()
    await db.commit()
    return tool


async def _seed_platform_sdk_system_artifact(db, *, input_schema: dict, output_schema: dict):
    registry = ArtifactRegistryService(db)
    artifact = await registry.get_system_artifact(system_key="platform_sdk")
    source_files = _load_platform_sdk_source_files()
    revision_service = ArtifactRevisionService(db)

    if artifact is None:
        artifact = await revision_service.create_artifact(
            tenant_id=None,
            created_by=None,
            display_name="Platform SDK",
            description="SDK-powered tool to fetch catalogs, create draft assets, and run multi-case tests.",
            kind=ArtifactKind.TOOL_IMPL.value,
            owner_type=ArtifactOwnerType.SYSTEM.value,
            system_key="platform_sdk",
            source_files=source_files,
            entry_module_path="platform_sdk/handler.py",
            python_dependencies=[],
            runtime_target="cloudflare_workers",
            capabilities={"network_access": True, "side_effects": ["control_plane_mutation"]},
            config_schema={},
            tool_contract={
                "input_schema": input_schema,
                "output_schema": output_schema,
                "side_effects": ["control_plane_mutation"],
                "execution_mode": "interactive",
                "tool_ui": {"icon": "Wrench", "color": "#0ea5e9"},
            },
        )
        await revision_service.publish_latest_draft(artifact)
        await db.flush()
        return artifact

    current_revision = artifact.latest_draft_revision or artifact.latest_published_revision
    if current_revision is None:
        raise RuntimeError("Platform SDK system artifact is missing a revision")
    await revision_service.update_artifact(
        artifact,
        updated_by=None,
        display_name="Platform SDK",
        description="SDK-powered tool to fetch catalogs, create draft assets, and run multi-case tests.",
        source_files=source_files,
        entry_module_path="platform_sdk/handler.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True, "side_effects": ["control_plane_mutation"]},
        config_schema={},
        tool_contract={
            "input_schema": input_schema,
            "output_schema": output_schema,
            "side_effects": ["control_plane_mutation"],
            "execution_mode": "interactive",
            "tool_ui": {"icon": "Wrench", "color": "#0ea5e9"},
        },
    )
    artifact.latest_published_revision_id = None
    await revision_service.publish_latest_draft(artifact)
    await db.flush()
    return artifact


def _load_platform_sdk_source_files() -> list[dict[str, str]]:
    base_dir = Path(__file__).resolve().parents[1] / "system_artifacts" / "platform_sdk"
    source_files: list[dict[str, str]] = []
    for path in sorted(base_dir.rglob("*.py")):
        relative_path = path.relative_to(base_dir.parent).as_posix()
        source_files.append({"path": relative_path, "content": path.read_text()})
    return source_files


async def seed_builtin_tool_templates(db):
    """
    Seeds global built-in tool templates for Built-in Tools v1.
    """
    if not is_builtin_tools_v1_enabled():
        return []

    await _normalize_tool_status_values(db)
    await _normalize_tool_impl_values(db)

    tool_columns = await _get_table_columns(db, "tool_registry")
    required_cols = {
        "builtin_key",
        "builtin_template_id",
        "is_builtin_template",
        "artifact_id",
        "artifact_version",
    }
    if not required_cols.issubset(tool_columns):
        print("tool_registry missing builtin metadata columns; skipping built-in template seed.")
        return []

    seeded = []
    for spec in BUILTIN_TEMPLATE_SPECS:
        # Platform SDK is seeded by the dedicated seeder.
        if spec.key == "platform_sdk":
            continue

        result = await db.execute(
            select(ToolRegistry).where(
                ToolRegistry.tenant_id == None,
                ToolRegistry.builtin_key == spec.key,
            )
        )
        tool = result.scalars().first()

        schema = {
            "input": spec.input_schema,
            "output": spec.output_schema,
        }
        config_schema = {
            "implementation": dict(spec.implementation),
            "execution": dict(spec.execution),
        }

        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name=spec.name,
                slug=spec.slug,
                description=spec.description,
                scope=ToolDefinitionScope.GLOBAL,
                schema=schema,
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=spec.implementation_type,
                artifact_id=None,
                artifact_version=None,
                builtin_key=spec.key,
                builtin_template_id=None,
                is_builtin_template=False,
                is_active=True,
                is_system=True,
                published_at=datetime.utcnow(),
            )
            set_tool_management_metadata(tool, ownership="system")
            db.add(tool)
        else:
            tool.name = spec.name
            tool.slug = spec.slug
            tool.description = spec.description
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = schema
            tool.config_schema = config_schema
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = spec.implementation_type
            tool.artifact_id = None
            tool.artifact_version = None
            tool.builtin_key = spec.key
            tool.builtin_template_id = None
            tool.is_builtin_template = False
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.utcnow()
            set_tool_management_metadata(tool, ownership="system")

        seeded.append(tool)

    await db.commit()
    return seeded


async def seed_platform_architect_domain_tools(db) -> dict[str, str]:
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
    }
    tool_columns = await _get_table_columns(db, "tool_registry")
    if not required_cols.issubset(tool_columns):
        print("tool_registry missing required columns; skipping platform architect domain tool seed.")
        return {}

    seeded: dict[str, str] = {}
    for slug, spec in PLATFORM_ARCHITECT_DOMAIN_TOOLS.items():
        schema = build_platform_domain_tool_schema(slug, spec)
        config_schema = {
            "implementation": {
                "type": "function",
                "function_name": PLATFORM_NATIVE_FUNCTIONS[slug],
            },
            "execution": {
                "timeout_s": 60,
                "is_pure": False,
                "concurrency_group": "platform_sdk_local",
                "max_concurrency": 4,
                "strict_input_schema": True,
                "allowed_actions": list(spec["actions"].keys()),
            },
        }

        result = await db.execute(
            select(ToolRegistry).where(
                ToolRegistry.slug == slug,
                ToolRegistry.tenant_id == None,
            )
        )
        tool = result.scalars().first()
        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name=spec["name"],
                slug=slug,
                description=spec["description"],
                scope=ToolDefinitionScope.GLOBAL,
                schema=schema,
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=ToolImplementationType.FUNCTION,
                artifact_id=None,
                artifact_version=None,
                artifact_revision_id=None,
                builtin_key=None,
                builtin_template_id=None,
                is_builtin_template=False,
                is_active=True,
                is_system=True,
                published_at=datetime.utcnow(),
            )
            set_tool_management_metadata(tool, ownership="system")
            db.add(tool)
        else:
            tool.name = spec["name"]
            tool.description = spec["description"]
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = schema
            tool.config_schema = config_schema
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = ToolImplementationType.FUNCTION
            tool.artifact_id = None
            tool.artifact_version = None
            tool.artifact_revision_id = None
            tool.builtin_key = None
            tool.builtin_template_id = None
            tool.is_builtin_template = False
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.utcnow()
            set_tool_management_metadata(tool, ownership="system")
        await db.flush()
        seeded[slug] = str(tool.id)

    await db.commit()
    return seeded


async def seed_platform_architect_agent(db):
    """
    Seeds a tenant-scoped Platform Architect single-agent runtime (v1).
    """
    # Prevent enum mismatches when loading tool references
    await _normalize_tool_status_values(db)
    await _normalize_tool_impl_values(db)

    tenant_result = await db.execute(select(Tenant).limit(1))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        print("No tenant found; skipping Platform Architect agent seed.")
        return None

    tool_ids = await seed_platform_architect_domain_tools(db)
    expected_slugs = tuple(PLATFORM_ARCHITECT_DOMAIN_TOOLS.keys())
    if not all(tool_ids.get(slug) for slug in expected_slugs):
        print("Platform architect domain tools missing; skipping Platform Architect agent seed.")
        return None
    worker_tool_ids = await ensure_platform_architect_worker_tools(
        db,
        tenant_id=tenant.id,
    )

    model_id = await _resolve_default_chat_model_id(db, tenant.id)
    if not model_id:
        print("No chat model available; skipping Platform Architect agent seed.")
        return None

    architect_tool_ids = [
        *[tool_ids[slug] for slug in expected_slugs],
        *worker_tool_ids,
    ]
    graph_definition = build_architect_graph_definition(
        model_id=model_id,
        tool_ids=architect_tool_ids,
    )

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
        if agent is None:
            agent = Agent(
                tenant_id=tenant.id,
                name="Platform Architect",
                slug="platform-architect",
                description="Dynamic single-agent platform architect runtime using Control Plane SDK domain tools.",
                graph_definition=graph_definition,
                tools=architect_tool_ids,
                referenced_tool_ids=architect_tool_ids,
                status=AgentStatus.published,
                is_active=True,
                is_public=False,
            )
            db.add(agent)
        else:
            agent.name = "Platform Architect"
            agent.description = "Dynamic single-agent platform architect runtime using Control Plane SDK domain tools."
            agent.graph_definition = graph_definition
            agent.tools = architect_tool_ids
            agent.referenced_tool_ids = architect_tool_ids
            agent.status = AgentStatus.published
            agent.is_active = True
            agent.is_public = False

        await db.commit()
        await ensure_platform_architect_worker_orchestration_policy(
            db,
            tenant_id=tenant.id,
            orchestrator_agent_id=agent.id,
        )
        await db.commit()
        return agent

    await db.rollback()
    agent = await _seed_platform_architect_agent_legacy(db, tenant.id, graph_definition, architect_tool_ids, agent_columns)
    if agent is not None:
        await ensure_platform_architect_worker_orchestration_policy(
            db,
            tenant_id=tenant.id,
            orchestrator_agent_id=agent.id,
        )
        await db.commit()
    return agent


async def seed_artifact_coding_agent(db):
    tenant_result = await db.execute(select(Tenant).limit(1))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        print("No tenant found; skipping Artifact Coding agent seed.")
        return None
    agent = await ensure_artifact_coding_agent_profile(db, tenant.id)
    await db.commit()
    return agent


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


async def _seed_platform_architect_agent_legacy(
    db,
    tenant_id,
    graph_definition: dict,
    tool_ids: list[str],
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
        "tools": list(tool_ids or []),
        "referenced_tool_ids": list(tool_ids or []),
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
