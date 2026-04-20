from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    ensure_sensitive_action_approved,
    get_current_principal,
    require_scopes,
)
from app.db.postgres.models.identity import Tenant
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
from app.db.postgres.session import get_db
from app.services.artifact_runtime.deployment_service import ArtifactDeploymentService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.db.postgres.models.artifact_runtime import ArtifactKind
from app.services.builtin_tools import is_builtin_tools_v1_enabled
from app.services.prompt_reference_resolver import PromptReferenceError, PromptReferenceResolver
from app.services.ui_blocks import frontend_requirements_for_tool
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane import tool_registry_admin_service as tool_admin

router = APIRouter(prefix="/tools", tags=["tools"])

_ALLOWED_TOOL_VALIDATION_MODES = {"strict", "none"}


async def get_tools_context(
    context=Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if context.get("type") == "workload":
        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        try:
            tenant_uuid = uuid.UUID(str(tenant_id))
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid tenant context")
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {"tenant_id": str(tenant.id), "tenant": tenant, "user": None, "is_service": True}

    tenant_id = context.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        tenant_uuid = uuid.UUID(str(tenant_id))
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid tenant context")
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "tenant_id": str(tenant.id),
        "tenant": tenant,
        "user": context.get("user"),
        "is_service": False,
    }


def _service_context(*, tenant_ctx: dict[str, Any], principal: dict[str, Any] | None = None) -> ControlPlaneContext:
    principal = principal or {}
    return ControlPlaneContext.from_tenant_context(
        tenant_ctx,
        user=tenant_ctx.get("user") or principal.get("user"),
        user_id=getattr(tenant_ctx.get("user") or principal.get("user"), "id", None),
        auth_token=principal.get("auth_token"),
        scopes=principal.get("scopes"),
        is_service=bool(tenant_ctx.get("is_service")),
    )


class CreateToolRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    input_schema: dict
    output_schema: dict
    config_schema: Optional[dict] = None
    implementation_type: Optional[ToolImplementationType] = None
    implementation_config: Optional[dict] = None
    execution_config: Optional[dict] = None
    scope: ToolDefinitionScope = ToolDefinitionScope.TENANT
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None
    status: Optional[ToolStatus] = None


class UpdateToolRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    config_schema: Optional[dict] = None
    implementation_type: Optional[ToolImplementationType] = None
    implementation_config: Optional[dict] = None
    execution_config: Optional[dict] = None
    is_active: Optional[bool] = None
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None
    status: Optional[ToolStatus] = None


class ToolResponse(BaseModel):
    id: uuid.UUID
    tenant_id: Optional[uuid.UUID]
    name: str
    slug: str
    description: Optional[str]
    scope: str
    input_schema: dict
    output_schema: dict
    config_schema: dict
    implementation_config: dict
    execution_config: dict
    status: ToolStatus
    version: str
    implementation_type: ToolImplementationType
    published_at: Optional[datetime] = None
    tool_type: str
    ownership: str
    managed_by: str
    source_object_type: Optional[str] = None
    source_object_id: Optional[str] = None
    can_edit_in_registry: bool
    can_publish_in_registry: bool
    can_delete_in_registry: bool
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None
    artifact_revision_id: Optional[uuid.UUID] = None
    visual_pipeline_id: Optional[uuid.UUID] = None
    executable_pipeline_id: Optional[uuid.UUID] = None
    builtin_key: Optional[str] = None
    builtin_template_id: Optional[uuid.UUID] = None
    is_builtin_template: bool = False
    is_builtin_instance: bool = False
    frontend_requirements: Optional[dict[str, Any]] = None
    toolset: Optional[dict[str, Any]] = None
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime


class ToolListResponse(BaseModel):
    tools: list[ToolResponse]
    total: int


_PIPELINE_DEFAULT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query text"},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        "filters": {"type": "object"},
    },
    "required": ["query"],
    "additionalProperties": False,
}

_PIPELINE_DEFAULT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}


def _ensure_builtin_tools_enabled() -> None:
    if not is_builtin_tools_v1_enabled():
        raise HTTPException(status_code=404, detail="Built-in tools v1 is disabled")


def _serialize_scope(value: ToolDefinitionScope | str | None) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _status_value(tool: ToolRegistry | object) -> str:
    raw = getattr(tool, "status", None)
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        return str(raw.value).lower()
    return str(raw).lower()


def _get_tool_impl_type(tool: ToolRegistry | object) -> ToolImplementationType:
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


def _is_builtin_template(tool: ToolRegistry | object) -> bool:
    # Deprecated architecture: templates are no longer part of runtime behavior.
    return False


def _is_builtin_instance(tool: ToolRegistry | object) -> bool:
    # Deprecated architecture: instances are no longer part of runtime behavior.
    return False


def _is_builtin(tool: ToolRegistry | object) -> bool:
    return bool(getattr(tool, "builtin_key", None)) or bool(getattr(tool, "is_system", False))


def _is_sensitive_config_key(key: str) -> bool:
    text = key.strip().lower()
    if text in {
        "api_key",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "authorization",
    }:
        return True
    return text.endswith(("_api_key", "_token", "_secret", "_password"))


def _redact_sensitive_config(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            if _is_sensitive_config_key(str(k)):
                redacted[k] = "***"
            else:
                redacted[k] = _redact_sensitive_config(v)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_config(v) for v in value]
    return value


def _normalize_retrieval_tool_schemas(
    input_schema: Optional[dict],
    output_schema: Optional[dict],
) -> tuple[dict, dict]:
    normalized_input = deepcopy(input_schema) if isinstance(input_schema, dict) else {}
    normalized_output = deepcopy(output_schema) if isinstance(output_schema, dict) else {}

    if not normalized_input:
        normalized_input = deepcopy(_RETRIEVAL_DEFAULT_INPUT_SCHEMA)
    else:
        normalized_input.setdefault("type", "object")
        props = normalized_input.get("properties")
        if not isinstance(props, dict):
            props = {}
        if "query" not in props:
            props["query"] = {"type": "string", "description": "Search query text"}
        if "top_k" not in props:
            props["top_k"] = {"type": "integer", "minimum": 1, "maximum": 50}
        if "filters" not in props:
            props["filters"] = {"type": "object"}
        normalized_input["properties"] = props

        required = normalized_input.get("required")
        if not isinstance(required, list):
            required = []
        if "query" not in required:
            required.append("query")
        normalized_input["required"] = required
        normalized_input.setdefault("additionalProperties", False)

    if not normalized_output:
        normalized_output = deepcopy(_RETRIEVAL_DEFAULT_OUTPUT_SCHEMA)
    else:
        normalized_output.setdefault("type", "object")
        props = normalized_output.get("properties")
        if not isinstance(props, dict):
            props = {}
        props.setdefault("results", {"type": "array", "items": {"type": "object"}})
        props.setdefault("count", {"type": "integer"})
        normalized_output["properties"] = props
        required = normalized_output.get("required")
        if not isinstance(required, list):
            required = []
        if "results" not in required:
            required.append("results")
        normalized_output["required"] = required
        normalized_output.setdefault("additionalProperties", True)

    return normalized_input, normalized_output


def _get_tool_type(tool: ToolRegistry | object, impl_type: ToolImplementationType) -> str:
    if _is_builtin(tool):
        return "built_in"
    if impl_type == ToolImplementationType.MCP:
        return "mcp"
    if getattr(tool, "artifact_id", None) or impl_type == ToolImplementationType.ARTIFACT:
        return "artifact"
    return "custom"


def _get_agent_binding_id(tool: ToolRegistry | object) -> str | None:
    config_schema = getattr(tool, "config_schema", {}) or {}
    if not isinstance(config_schema, dict):
        return None
    binding = config_schema.get("agent_binding")
    if isinstance(binding, dict) and binding.get("owned_by_source") is True and binding.get("agent_id"):
        return str(binding["agent_id"])
    return None


def _get_tool_ownership(tool: ToolRegistry | object, impl_type: ToolImplementationType) -> str:
    if bool(getattr(tool, "is_system", False)):
        return "system"
    if _get_agent_binding_id(tool):
        return "agent_bound"
    if getattr(tool, "artifact_id", None) or impl_type == ToolImplementationType.ARTIFACT:
        return "artifact_bound"
    if getattr(tool, "visual_pipeline_id", None) or getattr(tool, "executable_pipeline_id", None) or impl_type == ToolImplementationType.RAG_PIPELINE:
        return "pipeline_bound"
    return "manual"


def _get_tool_manager(ownership: str) -> str:
    return get_tool_manager_value(ownership)


def _get_tool_source(tool: ToolRegistry | object, ownership: str) -> tuple[str | None, str | None]:
    if ownership == "agent_bound":
        return "agent", _get_agent_binding_id(tool)
    if ownership == "artifact_bound":
        artifact_id = getattr(tool, "artifact_id", None)
        return "artifact", str(artifact_id) if artifact_id else None
    if ownership == "pipeline_bound":
        visual_pipeline_id = getattr(tool, "visual_pipeline_id", None)
        executable_pipeline_id = getattr(tool, "executable_pipeline_id", None)
        source_id = visual_pipeline_id or executable_pipeline_id
        return "pipeline", str(source_id) if source_id else None
    return None, None


def _tool_metadata_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(getattr(value, "value", value))


def _resolve_tool_metadata(
    tool: ToolRegistry | object,
    impl_type: ToolImplementationType,
) -> tuple[str, str, str | None, str | None]:
    ownership = _tool_metadata_value(getattr(tool, "ownership", None))
    managed_by = _tool_metadata_value(getattr(tool, "managed_by", None))
    source_object_type = _tool_metadata_value(getattr(tool, "source_object_type", None))
    source_object_id = _tool_metadata_value(getattr(tool, "source_object_id", None))

    if ownership:
        managed_by = managed_by or _get_tool_manager(ownership)
        if ownership in {"artifact_bound", "pipeline_bound", "agent_bound"}:
            derived_type, derived_id = _get_tool_source(tool, ownership)
            source_object_type = source_object_type or derived_type
            source_object_id = source_object_id or derived_id
        else:
            source_object_type = None
            source_object_id = None
        return ownership, managed_by, source_object_type, source_object_id

    ownership = _get_tool_ownership(tool, impl_type)
    managed_by = _get_tool_manager(ownership)
    source_object_type, source_object_id = _get_tool_source(tool, ownership)
    return ownership, managed_by, source_object_type, source_object_id


def _serialize_tool(tool: ToolRegistry | object) -> ToolResponse:
    impl_type = _get_tool_impl_type(tool)
    ownership, managed_by, source_object_type, source_object_id = _resolve_tool_metadata(tool, impl_type)
    config_schema = getattr(tool, "config_schema", {}) or {}
    if not isinstance(config_schema, dict):
        config_schema = {}
    config_schema["execution"] = _normalize_execution_config(config_schema.get("execution"))
    implementation_config = _redact_sensitive_config((config_schema.get("implementation") if isinstance(config_schema, dict) else {}) or {})
    execution_config = _redact_sensitive_config((config_schema.get("execution") if isinstance(config_schema, dict) else {}) or {})
    return ToolResponse(
        id=getattr(tool, "id"),
        tenant_id=getattr(tool, "tenant_id", None),
        name=getattr(tool, "name"),
        slug=getattr(tool, "slug"),
        description=getattr(tool, "description", None),
        scope=_serialize_scope(getattr(tool, "scope", None)),
        input_schema=((getattr(tool, "schema", None) or {}).get("input", {})),
        output_schema=((getattr(tool, "schema", None) or {}).get("output", {})),
        config_schema=_redact_sensitive_config(config_schema),
        implementation_config=implementation_config,
        execution_config=execution_config,
        status=getattr(tool, "status"),
        version=str(getattr(tool, "version", "1.0.0")),
        implementation_type=impl_type,
        published_at=getattr(tool, "published_at", None),
        tool_type=_get_tool_type(tool, impl_type),
        ownership=ownership,
        managed_by=managed_by,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        can_edit_in_registry=ownership == "manual",
        can_publish_in_registry=ownership == "manual",
        can_delete_in_registry=ownership == "manual",
        artifact_id=getattr(tool, "artifact_id", None),
        artifact_version=getattr(tool, "artifact_version", None),
        artifact_revision_id=getattr(tool, "artifact_revision_id", None),
        visual_pipeline_id=getattr(tool, "visual_pipeline_id", None),
        executable_pipeline_id=getattr(tool, "executable_pipeline_id", None),
        builtin_key=getattr(tool, "builtin_key", None),
        builtin_template_id=getattr(tool, "builtin_template_id", None),
        is_builtin_template=_is_builtin_template(tool),
        is_builtin_instance=_is_builtin_instance(tool),
        frontend_requirements=frontend_requirements_for_tool(tool),
        toolset=tool_admin.resolve_toolset_payload(tool),
        is_active=bool(getattr(tool, "is_active", False)),
        is_system=bool(getattr(tool, "is_system", False)),
        created_at=getattr(tool, "created_at"),
        updated_at=getattr(tool, "updated_at"),
    )


def _normalize_execution_config(execution_config: Optional[dict]) -> dict:
    execution = deepcopy(execution_config) if isinstance(execution_config, dict) else {}
    if "strict_input_schema" in execution:
        raise HTTPException(status_code=400, detail="execution.strict_input_schema has been removed; use execution.validation_mode")
    validation_mode = str(execution.get("validation_mode") or "strict").strip().lower()
    if validation_mode not in _ALLOWED_TOOL_VALIDATION_MODES:
        raise HTTPException(status_code=400, detail="execution.validation_mode must be one of: strict, none")
    execution["validation_mode"] = validation_mode
    return execution


def _compose_config_schema(
    *,
    current: Optional[dict],
    config_schema: Optional[dict],
    implementation_config: Optional[dict],
    execution_config: Optional[dict],
    implementation_type: Optional[ToolImplementationType],
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
        next_schema["execution"] = _normalize_execution_config(execution_config)
    else:
        next_schema["execution"] = _normalize_execution_config(next_schema.get("execution"))
    return next_schema


async def _ensure_slug_available(db: AsyncSession, slug: str) -> None:
    exists = await db.execute(select(ToolRegistry.id).where(ToolRegistry.slug == slug))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"Tool with slug '{slug}' already exists")


def _enum_name(value: ToolImplementationType | ToolStatus | ToolDefinitionScope | str | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _parse_uuid(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except Exception:
        return None


def _resolve_artifact_binding(
    *,
    artifact_id: Optional[str],
    artifact_version: Optional[str],
    config_schema: Optional[dict],
    implementation_type: Optional[ToolImplementationType],
) -> tuple[Optional[str], Optional[str]]:
    if artifact_id:
        return artifact_id, artifact_version

    impl_type = implementation_type.value if hasattr(implementation_type, "value") else implementation_type
    impl_config = (config_schema or {}).get("implementation") if isinstance(config_schema, dict) else {}
    if str(impl_type or "").lower() == ToolImplementationType.ARTIFACT.value.lower() and isinstance(impl_config, dict):
        artifact_ref = impl_config.get("artifact_id")
        if artifact_ref:
            return str(artifact_ref), impl_config.get("artifact_version")
    return None, None


async def _resolve_tool_artifact_revision_id(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    tool: ToolRegistry,
) -> uuid.UUID | None:
    artifact_id, _artifact_version = _resolve_artifact_binding(
        artifact_id=getattr(tool, "artifact_id", None),
        artifact_version=getattr(tool, "artifact_version", None),
        config_schema=getattr(tool, "config_schema", None),
        implementation_type=getattr(tool, "implementation_type", None),
    )
    artifact_uuid = _parse_uuid(artifact_id)
    if artifact_uuid is None:
        return None

    artifact = await ArtifactRegistryService(db).get_tenant_artifact(
        artifact_id=artifact_uuid,
        tenant_id=tenant_id,
    )
    if artifact is None:
        raise HTTPException(status_code=400, detail="Artifact-backed tool references an artifact outside tenant scope")
    if artifact.kind != ArtifactKind.TOOL_IMPL:
        raise HTTPException(status_code=400, detail="Artifact-backed tool requires a tool_impl artifact")
    if artifact.latest_published_revision_id is None:
        raise HTTPException(status_code=400, detail="Artifact-backed tool requires a published artifact revision before publish")
    return artifact.latest_published_revision_id


async def _publish_tool(
    *,
    db: AsyncSession,
    tool: ToolRegistry,
    tenant_ctx: dict,
    principal: dict,
    tenant_id: uuid.UUID,
) -> ToolRegistry:
    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tenant_id,
        subject_type="tool",
        subject_id=str(tool.id),
        action_scope="tools.publish",
        db=db,
    )

    tool.artifact_revision_id = await _resolve_tool_artifact_revision_id(
        db=db,
        tenant_id=tenant_id,
        tool=tool,
    )
    if tool.artifact_revision_id:
        revision = await ArtifactRegistryService(db).get_revision(
            revision_id=tool.artifact_revision_id,
            tenant_id=tenant_id,
        )
        if revision is None:
            raise HTTPException(status_code=400, detail="Artifact-backed tool revision is unavailable")
        await ArtifactDeploymentService(db).ensure_deployment(
            revision=revision,
            namespace="production",
            tenant_id=tenant_id,
        )
    tool.status = ToolStatus.PUBLISHED
    tool.is_active = True
    tool.published_at = tool.published_at or datetime.utcnow()

    snapshot = {
        "schema": tool.schema or {},
        "config_schema": tool.config_schema or {},
        "implementation_type": _enum_name(tool.implementation_type),
        "version": tool.version,
        "artifact_id": tool.artifact_id,
        "artifact_version": tool.artifact_version,
        "artifact_revision_id": str(tool.artifact_revision_id) if tool.artifact_revision_id else None,
    }
    actor = tenant_ctx.get("user")
    db.add(
        ToolVersion(
            tool_id=tool.id,
            version=tool.version,
            schema_snapshot=snapshot,
            created_by=actor.id if actor else None,
        )
    )
    await db.commit()
    await db.refresh(tool)
    return tool


async def _validate_pipeline_binding_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    pipeline_id_raw: Optional[str],
) -> None:
    if not pipeline_id_raw:
        raise HTTPException(status_code=400, detail="rag_pipeline tools require a pipeline binding")

    try:
        pipeline_uuid = uuid.UUID(str(pipeline_id_raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pipeline id")

    executable = await db.execute(
        select(ExecutablePipeline.id).where(
            ExecutablePipeline.id == pipeline_uuid,
            ExecutablePipeline.tenant_id == tenant_id,
        )
    )
    if executable.scalar_one_or_none() is not None:
        return

    visual = await db.execute(
        select(VisualPipeline.id).where(
            VisualPipeline.id == pipeline_uuid,
            VisualPipeline.tenant_id == tenant_id,
        )
    )
    if visual.scalar_one_or_none() is not None:
        return

    raise HTTPException(status_code=400, detail="Pipeline not found in tenant scope")


def _maybe_validate_builtin_registry_status(requested_status: ToolStatus | None) -> None:
    if requested_status == ToolStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Use publish endpoint to publish this tool")


async def _validate_pipeline_config_if_needed(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    implementation_type: ToolImplementationType,
    config_schema: dict | None,
    visual_pipeline_id: uuid.UUID | None = None,
    executable_pipeline_id: uuid.UUID | None = None,
) -> None:
    if implementation_type != ToolImplementationType.RAG_PIPELINE:
        return
    pipeline_id = str(executable_pipeline_id or visual_pipeline_id) if (executable_pipeline_id or visual_pipeline_id) else None
    if pipeline_id is None:
        implementation = (config_schema or {}).get("implementation")
        pipeline_id = implementation.get("pipeline_id") if isinstance(implementation, dict) else None
    await _validate_pipeline_binding_for_tenant(
        db,
        tenant_id=tenant_id,
        pipeline_id_raw=pipeline_id,
    )


@router.get("", response_model=dict[str, Any])
async def list_tools(
    scope: Optional[ToolDefinitionScope] = None,
    is_active: Optional[bool] = True,
    status: Optional[ToolStatus] = None,
    implementation_type: Optional[ToolImplementationType] = None,
    tool_type: Optional[str] = Query(None, description="Primary tool bucket: built_in, mcp, artifact, custom"),
    skip: int = 0,
    limit: int = 20,
    view: str = Query("summary"),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    try:
        query = ListQuery.from_payload({"skip": skip, "limit": limit, "view": view})
        tools, total = await tool_admin.ToolRegistryAdminService(db).list_tools(
            ctx=_service_context(tenant_ctx=tenant_ctx),
            scope=scope,
            is_active=is_active,
            status=status,
            implementation_type=implementation_type,
            tool_type=tool_type,
            skip=query.skip,
            limit=query.limit,
        )
        return {
            "items": [tool_admin.serialize_tool(t, view=query.view) for t in tools],
            "total": total,
            "has_more": query.skip + len(tools) < total,
            "skip": query.skip,
            "limit": query.limit,
            "view": query.view,
        }
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.get("/builtins/templates", response_model=ToolListResponse)
async def list_builtin_templates(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_tools_context),
):
    _ensure_builtin_tools_enabled()

    # Backward-compatible endpoint name; returns global built-in catalog.
    stmt = (
        select(ToolRegistry)
        .where(
            ToolRegistry.tenant_id == None,
            or_(ToolRegistry.builtin_key != None, ToolRegistry.is_system == True),
        )
        .order_by(ToolRegistry.name.asc())
        .offset(skip)
        .limit(limit)
    )
    tools = (await db.execute(stmt)).scalars().all()
    total = (
        await db.execute(
            select(func.count(ToolRegistry.id)).where(
                ToolRegistry.tenant_id == None,
                or_(ToolRegistry.builtin_key != None, ToolRegistry.is_system == True),
            )
        )
    ).scalar() or 0

    return ToolListResponse(tools=[_serialize_tool(t) for t in tools], total=total)


@router.post("", response_model=ToolResponse)
async def create_tool(
    request: CreateToolRequest,
    _: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    try:
        tool = await tool_admin.ToolRegistryAdminService(db).create_tool(
            ctx=_service_context(tenant_ctx=tenant_ctx),
            request=request,
        )
        return tool_admin.serialize_tool(tool)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    try:
        tool = await tool_admin.ToolRegistryAdminService(db).get_tool(
            ctx=_service_context(tenant_ctx=tenant_ctx),
            tool_id=tool_id,
        )
        return tool_admin.serialize_tool(tool)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: uuid.UUID,
    request: UpdateToolRequest,
    _: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    try:
        tool = await tool_admin.ToolRegistryAdminService(db).update_tool(
            ctx=_service_context(tenant_ctx=tenant_ctx),
            tool_id=tool_id,
            request=request,
        )
        return tool_admin.serialize_tool(tool)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/{tool_id}/publish", response_model=ToolResponse)
async def publish_tool(
    tool_id: uuid.UUID,
    principal: dict = Depends(get_current_principal),
    _: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    try:
        tool = await tool_admin.ToolRegistryAdminService(db).publish_tool(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal),
            tool_id=tool_id,
        )
        return tool_admin.serialize_tool(tool)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/{tool_id}/version", response_model=ToolResponse)
async def create_tool_version(
    tool_id: uuid.UUID,
    new_version: str = Query(..., description="New semver version"),
    _: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    try:
        tool = await tool_admin.ToolRegistryAdminService(db).create_tool_version(
            ctx=_service_context(tenant_ctx=tenant_ctx),
            tool_id=tool_id,
            new_version=new_version,
        )
        return tool_admin.serialize_tool(tool)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: uuid.UUID,
    principal: dict = Depends(get_current_principal),
    _: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    tool = (
        await db.execute(select(ToolRegistry).where(ToolRegistry.id == tool_id, ToolRegistry.tenant_id == tid))
    ).scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system tools")
    if _is_builtin_instance(tool):
        raise HTTPException(status_code=404, detail="Tool not found")
    ownership, _, _, _ = _resolve_tool_metadata(tool, _get_tool_impl_type(tool))
    if ownership in {"artifact_bound", "pipeline_bound", "agent_bound"}:
        raise HTTPException(status_code=400, detail="Delete this tool from its owning domain")

    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tid,
        subject_type="tool",
        subject_id=str(tool.id),
        action_scope="tools.delete",
        db=db,
    )

    await db.delete(tool)
    await db.commit()
    return {"status": "deleted", "id": tool_id}
