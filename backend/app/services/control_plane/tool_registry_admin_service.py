from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ensure_sensitive_action_approved
from app.db.postgres.models.artifact_runtime import ArtifactKind
from app.db.postgres.models.rag import ExecutablePipeline, VisualPipeline
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    ToolVersion,
    get_tool_manager_value,
    set_tool_management_metadata,
)
from app.services.artifact_runtime.deployment_service import ArtifactDeploymentService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.builtin_tools import is_builtin_tools_v1_enabled
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import conflict, not_found, validation
from app.services.prompt_reference_resolver import PromptReferenceError, PromptReferenceResolver
from app.services.ui_blocks import frontend_requirements_for_tool


ALLOWED_TOOL_VALIDATION_MODES = {"strict", "none"}


def ensure_builtin_tools_enabled() -> None:
    if not is_builtin_tools_v1_enabled():
        raise not_found("Built-in tools v1 is disabled")


def serialize_scope(value: ToolDefinitionScope | str | None) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return value.value
    return str(value)


def status_value(tool: ToolRegistry | object) -> str:
    raw = getattr(tool, "status", None)
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        return str(raw.value).lower()
    return str(raw).lower()


def get_tool_impl_type(tool: ToolRegistry | object) -> ToolImplementationType:
    impl_type = getattr(tool, "implementation_type", None)
    if impl_type is not None:
        if isinstance(impl_type, ToolImplementationType):
            return impl_type
        impl_str = str(getattr(impl_type, "value", impl_type)).lower()
        for item in ToolImplementationType:
            if item.value.lower() == impl_str:
                return item
    config_schema = getattr(tool, "config_schema", {}) or {}
    impl_from_config = (config_schema.get("implementation") or {}).get("type")
    if impl_from_config:
        impl_str = str(impl_from_config).lower()
        for item in ToolImplementationType:
            if item.value.lower() == impl_str:
                return item
    if getattr(tool, "artifact_id", None):
        return ToolImplementationType.ARTIFACT
    if getattr(tool, "visual_pipeline_id", None) or getattr(tool, "executable_pipeline_id", None):
        return ToolImplementationType.RAG_PIPELINE
    if getattr(tool, "is_system", False):
        return ToolImplementationType.INTERNAL
    return ToolImplementationType.CUSTOM


def is_builtin_template(tool: ToolRegistry | object) -> bool:
    return False


def is_builtin_instance(tool: ToolRegistry | object) -> bool:
    return False


def is_sensitive_config_key(key: str) -> bool:
    text = key.strip().lower()
    return text in {
        "api_key", "token", "access_token", "refresh_token", "secret", "password", "authorization",
    } or text.endswith(("_api_key", "_token", "_secret", "_password"))


def redact_sensitive_config(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if is_sensitive_config_key(str(k)) else redact_sensitive_config(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_config(item) for item in value]
    return value


def get_tool_type(tool: ToolRegistry | object, impl_type: ToolImplementationType) -> str:
    if getattr(tool, "is_system", False) or getattr(tool, "builtin_key", None):
        return "built_in"
    if impl_type == ToolImplementationType.MCP:
        return "mcp"
    if getattr(tool, "artifact_id", None) or impl_type == ToolImplementationType.ARTIFACT:
        return "artifact"
    return "custom"


def get_agent_binding_id(tool: ToolRegistry | object) -> str | None:
    config_schema = getattr(tool, "config_schema", {}) or {}
    binding = config_schema.get("agent_binding") if isinstance(config_schema, dict) else None
    if isinstance(binding, dict) and binding.get("owned_by_source") is True and binding.get("agent_id"):
        return str(binding["agent_id"])
    return None


def get_tool_ownership(tool: ToolRegistry | object, impl_type: ToolImplementationType) -> str:
    if bool(getattr(tool, "is_system", False)):
        return "system"
    if get_agent_binding_id(tool):
        return "agent_bound"
    if getattr(tool, "artifact_id", None) or impl_type == ToolImplementationType.ARTIFACT:
        return "artifact_bound"
    if getattr(tool, "visual_pipeline_id", None) or getattr(tool, "executable_pipeline_id", None) or impl_type == ToolImplementationType.RAG_PIPELINE:
        return "pipeline_bound"
    return "manual"


def get_tool_source(tool: ToolRegistry | object, ownership: str) -> tuple[str | None, str | None]:
    if ownership == "agent_bound":
        return "agent", get_agent_binding_id(tool)
    if ownership == "artifact_bound":
        artifact_id = getattr(tool, "artifact_id", None)
        return "artifact", str(artifact_id) if artifact_id else None
    if ownership == "pipeline_bound":
        source_id = getattr(tool, "visual_pipeline_id", None) or getattr(tool, "executable_pipeline_id", None)
        return "pipeline", str(source_id) if source_id else None
    return None, None


def resolve_tool_metadata(tool: ToolRegistry | object, impl_type: ToolImplementationType) -> tuple[str, str, str | None, str | None]:
    ownership = str(getattr(getattr(tool, "ownership", None), "value", getattr(tool, "ownership", None)) or "") or None
    managed_by = str(getattr(getattr(tool, "managed_by", None), "value", getattr(tool, "managed_by", None)) or "") or None
    source_object_type = str(getattr(getattr(tool, "source_object_type", None), "value", getattr(tool, "source_object_type", None)) or "") or None
    source_object_id = str(getattr(getattr(tool, "source_object_id", None), "value", getattr(tool, "source_object_id", None)) or "") or None
    if ownership:
        managed_by = managed_by or get_tool_manager_value(ownership)
        if ownership in {"artifact_bound", "pipeline_bound", "agent_bound"}:
            derived_type, derived_id = get_tool_source(tool, ownership)
            source_object_type = source_object_type or derived_type
            source_object_id = source_object_id or derived_id
        else:
            source_object_type = None
            source_object_id = None
        return ownership, managed_by, source_object_type, source_object_id
    ownership = get_tool_ownership(tool, impl_type)
    managed_by = get_tool_manager_value(ownership)
    source_object_type, source_object_id = get_tool_source(tool, ownership)
    return ownership, managed_by, source_object_type, source_object_id


def normalize_execution_config(execution_config: dict | None) -> dict:
    execution = deepcopy(execution_config) if isinstance(execution_config, dict) else {}
    if "strict_input_schema" in execution:
        raise validation("execution.strict_input_schema has been removed; use execution.validation_mode")
    validation_mode = str(execution.get("validation_mode") or "strict").strip().lower()
    if validation_mode not in ALLOWED_TOOL_VALIDATION_MODES:
        raise validation("execution.validation_mode must be one of: strict, none")
    execution["validation_mode"] = validation_mode
    return execution


def compose_config_schema(
    *,
    current: dict | None,
    config_schema: dict | None,
    implementation_config: dict | None,
    execution_config: dict | None,
    implementation_type: ToolImplementationType | None,
) -> dict:
    next_schema = deepcopy(current or {})
    if config_schema is not None:
        next_schema = deepcopy(config_schema)
    if implementation_config is not None:
        next_schema["implementation"] = implementation_config
    elif implementation_type is not None:
        next_schema.setdefault("implementation", {})
        next_schema["implementation"]["type"] = implementation_type.value
    if execution_config is not None:
        next_schema["execution"] = normalize_execution_config(execution_config)
    else:
        next_schema["execution"] = normalize_execution_config(next_schema.get("execution"))
    return next_schema


def internal_tool_key() -> str:
    return f"tool-{uuid4().hex}"


def enum_name(value: ToolImplementationType | ToolStatus | ToolDefinitionScope | str | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def parse_uuid(raw: Any) -> UUID | None:
    try:
        return UUID(str(raw))
    except Exception:
        return None


def resolve_artifact_binding(
    *,
    artifact_id: str | None,
    artifact_version: str | None,
    config_schema: dict | None,
    implementation_type: ToolImplementationType | None,
) -> tuple[str | None, str | None]:
    if artifact_id:
        return artifact_id, artifact_version
    impl_type = implementation_type.value if hasattr(implementation_type, "value") else implementation_type
    impl_config = (config_schema or {}).get("implementation") if isinstance(config_schema, dict) else {}
    if str(impl_type or "").lower() == ToolImplementationType.ARTIFACT.value.lower() and isinstance(impl_config, dict):
        artifact_ref = impl_config.get("artifact_id")
        if artifact_ref:
            return str(artifact_ref), impl_config.get("artifact_version")
    return None, None


async def resolve_tool_artifact_revision_id(*, db: AsyncSession, organization_id: UUID, tool: ToolRegistry) -> UUID | None:
    artifact_id, _ = resolve_artifact_binding(
        artifact_id=getattr(tool, "artifact_id", None),
        artifact_version=getattr(tool, "artifact_version", None),
        config_schema=getattr(tool, "config_schema", None),
        implementation_type=getattr(tool, "implementation_type", None),
    )
    artifact_uuid = parse_uuid(artifact_id)
    if artifact_uuid is None:
        return None
    artifact = await ArtifactRegistryService(db).get_organization_artifact(artifact_id=artifact_uuid, organization_id=organization_id)
    if artifact is None:
        raise validation("Artifact-backed tool references an artifact outside organization scope")
    if artifact.kind != ArtifactKind.TOOL_IMPL:
        raise validation("Artifact-backed tool requires a tool_impl artifact")
    if artifact.latest_published_revision_id is None:
        raise validation("Artifact-backed tool requires a published artifact revision before publish")
    return artifact.latest_published_revision_id


async def publish_tool_record(
    *,
    db: AsyncSession,
    ctx: ControlPlaneContext,
    tool: ToolRegistry,
) -> ToolRegistry:
    await ensure_sensitive_action_approved(
        principal={
            "type": "user",
            "user": ctx.user,
            "user_id": str(ctx.user_id) if ctx.user_id else None,
            "organization_id": str(ctx.organization_id),
            "auth_token": ctx.auth_token,
            "scopes": list(ctx.scopes),
        },
        organization_id=ctx.organization_id,
        subject_type="tool",
        subject_id=str(tool.id),
        action_scope="tools.publish",
        db=db,
    )
    tool.artifact_revision_id = await resolve_tool_artifact_revision_id(db=db, organization_id=ctx.organization_id, tool=tool)
    if tool.artifact_revision_id:
        revision = await ArtifactRegistryService(db).get_revision(revision_id=tool.artifact_revision_id, organization_id=ctx.organization_id)
        if revision is None:
            raise validation("Artifact-backed tool revision is unavailable")
        await ArtifactDeploymentService(db).ensure_deployment(revision=revision, namespace="production", organization_id=ctx.organization_id)
    tool.status = ToolStatus.PUBLISHED
    tool.is_active = True
    tool.published_at = tool.published_at or datetime.utcnow()
    snapshot = {
        "schema": tool.schema or {},
        "config_schema": tool.config_schema or {},
        "implementation_type": enum_name(tool.implementation_type),
        "version": tool.version,
        "artifact_id": tool.artifact_id,
        "artifact_version": tool.artifact_version,
        "artifact_revision_id": str(tool.artifact_revision_id) if tool.artifact_revision_id else None,
    }
    db.add(ToolVersion(tool_id=tool.id, version=tool.version, schema_snapshot=snapshot, created_by=ctx.user.id if ctx.user else None))
    await db.commit()
    await db.refresh(tool)
    return tool


async def validate_pipeline_binding_for_tenant(db: AsyncSession, *, organization_id: UUID, pipeline_id_raw: str | None) -> None:
    if not pipeline_id_raw:
        raise validation("rag_pipeline tools require a pipeline binding")
    pipeline_uuid = parse_uuid(pipeline_id_raw)
    if pipeline_uuid is None:
        raise validation("Invalid pipeline id")
    executable = await db.execute(select(ExecutablePipeline.id).where(ExecutablePipeline.id == pipeline_uuid, ExecutablePipeline.organization_id == organization_id))
    if executable.scalar_one_or_none() is not None:
        return
    visual = await db.execute(select(VisualPipeline.id).where(VisualPipeline.id == pipeline_uuid, VisualPipeline.organization_id == organization_id))
    if visual.scalar_one_or_none() is not None:
        return
    raise validation("Pipeline not found in organization scope")


def maybe_validate_builtin_registry_status(requested_status: ToolStatus | None) -> None:
    if requested_status == ToolStatus.PUBLISHED:
        raise validation("Use publish endpoint to publish this tool")


async def validate_pipeline_config_if_needed(
    *,
    db: AsyncSession,
    organization_id: UUID,
    implementation_type: ToolImplementationType,
    config_schema: dict | None,
    visual_pipeline_id: UUID | None = None,
    executable_pipeline_id: UUID | None = None,
) -> None:
    if implementation_type != ToolImplementationType.RAG_PIPELINE:
        return
    pipeline_id = str(executable_pipeline_id or visual_pipeline_id) if (executable_pipeline_id or visual_pipeline_id) else None
    if pipeline_id is None:
        implementation = (config_schema or {}).get("implementation")
        pipeline_id = implementation.get("pipeline_id") if isinstance(implementation, dict) else None
    await validate_pipeline_binding_for_tenant(db, organization_id=organization_id, pipeline_id_raw=pipeline_id)


def resolve_toolset_payload(tool: ToolRegistry | object) -> dict[str, Any] | None:
    config_schema = getattr(tool, "config_schema", {}) or {}
    if not isinstance(config_schema, dict):
        return None

    raw = config_schema.get("toolset")
    if not isinstance(raw, dict):
        return None

    toolset_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    selection_mode = str(raw.get("selection_mode") or "expand_to_members").strip() or "expand_to_members"
    raw_member_ids = raw.get("member_ids")
    if not toolset_id or not name or not isinstance(raw_member_ids, list):
        return None

    member_ids: list[str] = []
    seen: set[str] = set()
    for value in raw_member_ids:
        member_id = str(value or "").strip()
        if not member_id or member_id in seen:
            continue
        seen.add(member_id)
        member_ids.append(member_id)

    current_tool_id = str(getattr(tool, "id", "") or "").strip()
    if not member_ids or (current_tool_id and current_tool_id not in member_ids):
        return None

    description = str(raw.get("description") or "").strip() or None
    return {
        "id": toolset_id,
        "name": name,
        "description": description,
        "selection_mode": selection_mode,
        "member_ids": member_ids,
    }


def serialize_tool(tool: ToolRegistry | object, *, view: str = "full") -> dict[str, Any]:
    impl_type = get_tool_impl_type(tool)
    ownership, managed_by, source_object_type, source_object_id = resolve_tool_metadata(tool, impl_type)
    config_schema = getattr(tool, "config_schema", {}) or {}
    if not isinstance(config_schema, dict):
        config_schema = {}
    config_schema["execution"] = normalize_execution_config(config_schema.get("execution"))
    implementation_config = redact_sensitive_config((config_schema.get("implementation") if isinstance(config_schema, dict) else {}) or {})
    execution_config = redact_sensitive_config((config_schema.get("execution") if isinstance(config_schema, dict) else {}) or {})
    payload = {
        "id": getattr(tool, "id"),
        "organization_id": getattr(tool, "organization_id", None),
        "name": getattr(tool, "name"),
        "description": getattr(tool, "description", None),
        "scope": serialize_scope(getattr(tool, "scope", None)),
        "status": getattr(tool, "status"),
        "version": str(getattr(tool, "version", "1.0.0")),
        "implementation_type": impl_type,
        "published_at": getattr(tool, "published_at", None),
        "tool_type": get_tool_type(tool, impl_type),
        "ownership": ownership,
        "managed_by": managed_by,
        "source_object_type": source_object_type,
        "source_object_id": source_object_id,
        "can_edit_in_registry": ownership == "manual",
        "can_publish_in_registry": ownership == "manual",
        "can_delete_in_registry": ownership == "manual",
        "artifact_id": getattr(tool, "artifact_id", None),
        "artifact_version": getattr(tool, "artifact_version", None),
        "artifact_revision_id": getattr(tool, "artifact_revision_id", None),
        "visual_pipeline_id": getattr(tool, "visual_pipeline_id", None),
        "executable_pipeline_id": getattr(tool, "executable_pipeline_id", None),
        "builtin_key": getattr(tool, "builtin_key", None),
        "builtin_template_id": getattr(tool, "builtin_template_id", None),
        "is_builtin_template": is_builtin_template(tool),
        "is_builtin_instance": is_builtin_instance(tool),
        "frontend_requirements": frontend_requirements_for_tool(tool),
        "toolset": resolve_toolset_payload(tool),
        "is_active": bool(getattr(tool, "is_active", False)),
        "is_system": bool(getattr(tool, "is_system", False)),
        "created_at": getattr(tool, "created_at"),
        "updated_at": getattr(tool, "updated_at"),
    }
    if view == "summary":
        return payload
    payload.update(
        {
            "input_schema": ((getattr(tool, "schema", None) or {}).get("input", {})),
            "output_schema": ((getattr(tool, "schema", None) or {}).get("output", {})),
            "config_schema": redact_sensitive_config(config_schema),
            "implementation_config": implementation_config,
            "execution_config": execution_config,
        }
    )
    return payload


class ToolRegistryAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _require_project_id(ctx: ControlPlaneContext) -> UUID:
        if ctx.project_id is None:
            raise validation("Active project context is required")
        return ctx.project_id

    def _scoped_conditions(self, *, ctx: ControlPlaneContext) -> list[Any]:
        project_id = self._require_project_id(ctx)
        return [
            or_(
                ToolRegistry.organization_id.is_(None),
                and_(
                    ToolRegistry.organization_id == ctx.organization_id,
                    ToolRegistry.project_id == project_id,
                ),
            ),
            ~and_(ToolRegistry.organization_id != None, ToolRegistry.builtin_key != None, ToolRegistry.is_system == False),
        ]

    async def list_tools(
        self,
        *,
        ctx: ControlPlaneContext,
        scope: ToolDefinitionScope | None = None,
        name: str | None = None,
        is_active: bool | None = True,
        status: ToolStatus | None = None,
        implementation_type: ToolImplementationType | None = None,
        tool_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolRegistry], int]:
        conditions = self._scoped_conditions(ctx=ctx)
        if scope:
            conditions.append(ToolRegistry.scope == scope)
        if name is not None and str(name).strip():
            conditions.append(func.lower(ToolRegistry.name) == str(name).strip().lower())
        if status is not None:
            conditions.append(func.lower(cast(ToolRegistry.status, String)) == status.value.lower())
        elif is_active is not None:
            conditions.append(ToolRegistry.is_active == is_active)
        if implementation_type is not None:
            conditions.append(ToolRegistry.implementation_type == implementation_type)
        if tool_type in {"built_in", "mcp", "artifact", "custom"}:
            built_in_pred = or_(
                ToolRegistry.is_system == True,
                ToolRegistry.builtin_key != None,
                and_(ToolRegistry.organization_id == None, ToolRegistry.implementation_type == ToolImplementationType.INTERNAL),
            )
            mcp_pred = ToolRegistry.implementation_type == ToolImplementationType.MCP
            artifact_pred = or_(ToolRegistry.artifact_id != None, ToolRegistry.implementation_type == ToolImplementationType.ARTIFACT)
            if tool_type == "built_in":
                conditions.append(built_in_pred)
            elif tool_type == "mcp":
                conditions.append(mcp_pred)
            elif tool_type == "artifact":
                conditions.append(artifact_pred)
            elif tool_type == "custom":
                conditions.append(~or_(built_in_pred, mcp_pred, artifact_pred))
        stmt = select(ToolRegistry).where(and_(*conditions)).order_by(ToolRegistry.name.asc()).offset(skip).limit(limit)
        tools = list((await self.db.execute(stmt)).scalars().all())
        total = (await self.db.execute(select(func.count(ToolRegistry.id)).where(and_(*conditions)))).scalar() or 0
        return tools, total

    async def get_tool(self, *, ctx: ControlPlaneContext, tool_id: UUID | None = None) -> ToolRegistry:
        conditions = self._scoped_conditions(ctx=ctx)
        if tool_id is not None:
            conditions.append(ToolRegistry.id == tool_id)
        else:
            raise validation("tool_id is required", field="tool_id")
        tool = (
            await self.db.execute(
                select(ToolRegistry).where(and_(*conditions))
            )
        ).scalar_one_or_none()
        if tool is None:
            raise not_found("Tool not found")
        return tool

    async def create_tool(self, *, ctx: ControlPlaneContext, request: Any) -> ToolRegistry:
        project_id = self._require_project_id(ctx)
        if request.scope != ToolDefinitionScope.TENANT:
            raise validation("Only organization-scoped tools can be created via this endpoint")
        slug = internal_tool_key()
        config_schema = compose_config_schema(
            current=request.config_schema,
            config_schema=request.config_schema,
            implementation_config=request.implementation_config,
            execution_config=request.execution_config,
            implementation_type=request.implementation_type,
        )
        impl_type = request.implementation_type
        if impl_type is None:
            probe = ToolRegistry(
                organization_id=ctx.organization_id,
                name=request.name,
                slug=slug,
                description=request.description,
                scope=request.scope,
                schema={"input": request.input_schema, "output": request.output_schema},
                config_schema=config_schema,
                artifact_id=request.artifact_id,
                artifact_version=request.artifact_version,
                is_active=True,
                is_system=False,
            )
            impl_type = get_tool_impl_type(probe)
        if impl_type in {ToolImplementationType.ARTIFACT, ToolImplementationType.RAG_PIPELINE}:
            raise validation("artifact and rag_pipeline tools are domain-owned. Create them from the artifact or pipeline editor.")
        input_schema = deepcopy(request.input_schema or {})
        output_schema = deepcopy(request.output_schema or {})
        try:
            await PromptReferenceResolver(self.db, ctx.organization_id, project_id).validate_tool_payload(
                description=request.description,
                input_schema=input_schema,
                output_schema=output_schema,
            )
        except PromptReferenceError as exc:
            raise validation(str(exc)) from exc
        requested_status = request.status or ToolStatus.DRAFT
        maybe_validate_builtin_registry_status(requested_status)
        await validate_pipeline_config_if_needed(
            db=self.db,
            organization_id=ctx.organization_id,
            implementation_type=impl_type,
            config_schema=config_schema,
        )
        tool = ToolRegistry(
            organization_id=ctx.organization_id,
            project_id=project_id,
            name=request.name,
            slug=slug,
            description=request.description,
            scope=request.scope,
            schema={"input": input_schema, "output": output_schema},
            config_schema=config_schema,
            implementation_type=impl_type,
            status=requested_status,
            version="1.0.0",
            published_at=None,
            artifact_id=request.artifact_id,
            artifact_version=request.artifact_version,
            artifact_revision_id=None,
            builtin_key=None,
            builtin_template_id=None,
            is_builtin_template=False,
            is_active=requested_status != ToolStatus.DISABLED,
            is_system=False,
        )
        set_tool_management_metadata(tool, ownership="manual")
        self.db.add(tool)
        await self.db.commit()
        await self.db.refresh(tool)
        return tool

    async def update_tool(self, *, ctx: ControlPlaneContext, tool_id: UUID, request: Any) -> ToolRegistry:
        project_id = self._require_project_id(ctx)
        tool = (
            await self.db.execute(
                select(ToolRegistry).where(
                    ToolRegistry.id == tool_id,
                    ToolRegistry.organization_id == ctx.organization_id,
                    ToolRegistry.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if tool is None:
            raise not_found("Tool not found")
        ownership, _, _, _ = resolve_tool_metadata(tool, get_tool_impl_type(tool))
        if ownership in {"artifact_bound", "pipeline_bound", "agent_bound"}:
            raise validation("This tool is managed by its owning domain")
        if tool.is_system:
            raise validation("Cannot modify system tools")
        if is_builtin_instance(tool):
            raise not_found("Tool not found")
        if request.name is not None:
            tool.name = request.name
        if request.description is not None:
            tool.description = request.description
        if request.input_schema is not None or request.output_schema is not None:
            schema = deepcopy(tool.schema or {})
            if request.input_schema is not None:
                schema["input"] = request.input_schema
            if request.output_schema is not None:
                schema["output"] = request.output_schema
            tool.schema = schema
        try:
            await PromptReferenceResolver(self.db, ctx.organization_id, project_id).validate_tool_payload(
                description=tool.description if request.description is None else request.description,
                input_schema=((tool.schema or {}).get("input") if isinstance(tool.schema, dict) else {}),
                output_schema=((tool.schema or {}).get("output") if isinstance(tool.schema, dict) else {}),
            )
        except PromptReferenceError as exc:
            raise validation(str(exc)) from exc
        tool.config_schema = compose_config_schema(
            current=tool.config_schema,
            config_schema=request.config_schema,
            implementation_config=request.implementation_config,
            execution_config=request.execution_config,
            implementation_type=request.implementation_type,
        )
        artifact_binding_changed = False
        if request.artifact_id is not None:
            artifact_binding_changed = request.artifact_id != tool.artifact_id
            tool.artifact_id = request.artifact_id
        if request.artifact_version is not None:
            artifact_binding_changed = artifact_binding_changed or request.artifact_version != tool.artifact_version
            tool.artifact_version = request.artifact_version
        if request.implementation_config is not None:
            current_impl = (tool.config_schema or {}).get("implementation") if isinstance(tool.config_schema, dict) else {}
            if current_impl != request.implementation_config:
                artifact_binding_changed = True
        if request.implementation_type is not None:
            tool.implementation_type = request.implementation_type
        if artifact_binding_changed:
            tool.artifact_revision_id = None
        if request.status is not None:
            if request.status == ToolStatus.PUBLISHED and status_value(tool) != "published":
                raise validation("Use POST /tools/{tool_id}/publish to publish a tool")
            tool.status = request.status
            if request.status == ToolStatus.DISABLED:
                tool.is_active = False
            elif request.is_active is None:
                tool.is_active = True
        if request.is_active is not None:
            tool.is_active = request.is_active
        effective_impl_type = get_tool_impl_type(tool)
        await validate_pipeline_config_if_needed(
            db=self.db,
            organization_id=ctx.organization_id,
            implementation_type=effective_impl_type,
            config_schema=tool.config_schema,
            visual_pipeline_id=getattr(tool, "visual_pipeline_id", None),
            executable_pipeline_id=getattr(tool, "executable_pipeline_id", None),
        )
        await self.db.commit()
        await self.db.refresh(tool)
        return tool

    async def publish_tool(self, *, ctx: ControlPlaneContext, tool_id: UUID) -> ToolRegistry:
        project_id = self._require_project_id(ctx)
        tool = (
            await self.db.execute(
                select(ToolRegistry).where(
                    ToolRegistry.id == tool_id,
                    ToolRegistry.organization_id == ctx.organization_id,
                    ToolRegistry.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if tool is None:
            raise not_found("Tool not found")
        if tool.is_system:
            raise validation("Cannot publish system tools")
        if is_builtin_instance(tool):
            raise not_found("Tool not found")
        ownership, _, _, _ = resolve_tool_metadata(tool, get_tool_impl_type(tool))
        if ownership in {"artifact_bound", "pipeline_bound", "agent_bound"}:
            raise validation("Publish this tool from its owning domain")
        await validate_pipeline_config_if_needed(
            db=self.db,
            organization_id=ctx.organization_id,
            implementation_type=get_tool_impl_type(tool),
            config_schema=tool.config_schema,
            visual_pipeline_id=getattr(tool, "visual_pipeline_id", None),
            executable_pipeline_id=getattr(tool, "executable_pipeline_id", None),
        )
        return await publish_tool_record(db=self.db, ctx=ctx, tool=tool)

    async def create_tool_version(self, *, ctx: ControlPlaneContext, tool_id: UUID, new_version: str) -> ToolRegistry:
        project_id = self._require_project_id(ctx)
        if not re.match(r"^\\d+\\.\\d+\\.\\d+$", new_version):
            raise validation("new_version must be valid semver (e.g. 1.0.0)")
        tool = (
            await self.db.execute(
                select(ToolRegistry).where(
                    ToolRegistry.id == tool_id,
                    ToolRegistry.organization_id == ctx.organization_id,
                    ToolRegistry.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if tool is None:
            raise not_found("Tool not found")
        if tool.is_system:
            raise validation("Cannot version system tools")
        snapshot = {
            "schema": tool.schema or {},
            "config_schema": tool.config_schema or {},
            "implementation_type": enum_name(tool.implementation_type),
            "version": new_version,
            "artifact_id": tool.artifact_id,
            "artifact_version": tool.artifact_version,
            "artifact_revision_id": str(tool.artifact_revision_id) if tool.artifact_revision_id else None,
        }
        self.db.add(ToolVersion(tool_id=tool.id, version=new_version, schema_snapshot=snapshot, created_by=ctx.user.id if ctx.user else None))
        tool.version = new_version
        await self.db.commit()
        await self.db.refresh(tool)
        return tool
