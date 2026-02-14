from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    ensure_sensitive_action_approved,
    get_current_principal,
    require_scopes,
)
from app.db.postgres.models.identity import Tenant
from app.db.postgres.models.rag import ExecutablePipeline, PipelineType, VisualPipeline
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    ToolVersion,
)
from app.db.postgres.session import get_db
from app.services.builtin_tools import is_builtin_tools_v1_enabled

router = APIRouter(prefix="/tools", tags=["tools"])


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
    status: ToolStatus
    version: str
    implementation_type: ToolImplementationType
    published_at: Optional[datetime] = None
    tool_type: str
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None
    builtin_key: Optional[str] = None
    builtin_template_id: Optional[uuid.UUID] = None
    is_builtin_template: bool = False
    is_builtin_instance: bool = False
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime


class ToolListResponse(BaseModel):
    tools: list[ToolResponse]
    total: int


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
    if getattr(tool, "is_system", False):
        return ToolImplementationType.INTERNAL
    return ToolImplementationType.CUSTOM


def _is_builtin_template(tool: ToolRegistry | object) -> bool:
    return bool(getattr(tool, "is_builtin_template", False))


def _is_builtin_instance(tool: ToolRegistry | object) -> bool:
    return bool(getattr(tool, "builtin_key", None)) and not _is_builtin_template(tool)


def _is_builtin(tool: ToolRegistry | object) -> bool:
    return bool(getattr(tool, "builtin_key", None)) or bool(getattr(tool, "is_system", False)) or _is_builtin_template(tool)


def _get_tool_type(tool: ToolRegistry | object, impl_type: ToolImplementationType) -> str:
    if _is_builtin(tool):
        return "built_in"
    if impl_type == ToolImplementationType.MCP:
        return "mcp"
    if getattr(tool, "artifact_id", None) or impl_type == ToolImplementationType.ARTIFACT:
        return "artifact"
    return "custom"


def _serialize_tool(tool: ToolRegistry | object) -> ToolResponse:
    impl_type = _get_tool_impl_type(tool)
    return ToolResponse(
        id=getattr(tool, "id"),
        tenant_id=getattr(tool, "tenant_id", None),
        name=getattr(tool, "name"),
        slug=getattr(tool, "slug"),
        description=getattr(tool, "description", None),
        scope=_serialize_scope(getattr(tool, "scope", None)),
        input_schema=((getattr(tool, "schema", None) or {}).get("input", {})),
        output_schema=((getattr(tool, "schema", None) or {}).get("output", {})),
        config_schema=(getattr(tool, "config_schema", {}) or {}),
        status=getattr(tool, "status"),
        version=str(getattr(tool, "version", "1.0.0")),
        implementation_type=impl_type,
        published_at=getattr(tool, "published_at", None),
        tool_type=_get_tool_type(tool, impl_type),
        artifact_id=getattr(tool, "artifact_id", None),
        artifact_version=getattr(tool, "artifact_version", None),
        builtin_key=getattr(tool, "builtin_key", None),
        builtin_template_id=getattr(tool, "builtin_template_id", None),
        is_builtin_template=_is_builtin_template(tool),
        is_builtin_instance=_is_builtin_instance(tool),
        is_active=bool(getattr(tool, "is_active", False)),
        is_system=bool(getattr(tool, "is_system", False)),
        created_at=getattr(tool, "created_at"),
        updated_at=getattr(tool, "updated_at"),
    )


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
        next_schema["execution"] = execution_config
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

    tool.status = ToolStatus.PUBLISHED
    tool.is_active = True
    tool.published_at = tool.published_at or datetime.utcnow()

    snapshot = {
        "schema": tool.schema or {},
        "config_schema": tool.config_schema or {},
        "implementation_type": _enum_name(tool.implementation_type),
        "version": tool.version,
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


async def _validate_retrieval_pipeline_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    pipeline_id_raw: Optional[str],
) -> None:
    if not pipeline_id_raw:
        raise HTTPException(status_code=400, detail="rag_retrieval tools require implementation.pipeline_id")

    try:
        pipeline_uuid = uuid.UUID(str(pipeline_id_raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid retrieval pipeline id")

    executable = await db.execute(
        select(ExecutablePipeline.id).where(
            ExecutablePipeline.id == pipeline_uuid,
            ExecutablePipeline.tenant_id == tenant_id,
            ExecutablePipeline.pipeline_type == PipelineType.RETRIEVAL,
        )
    )
    if executable.scalar_one_or_none() is not None:
        return

    visual = await db.execute(
        select(VisualPipeline.id).where(
            VisualPipeline.id == pipeline_uuid,
            VisualPipeline.tenant_id == tenant_id,
            VisualPipeline.pipeline_type == PipelineType.RETRIEVAL,
        )
    )
    if visual.scalar_one_or_none() is not None:
        return

    raise HTTPException(status_code=400, detail="Retrieval pipeline not found in tenant scope")


def _maybe_validate_builtin_registry_status(requested_status: ToolStatus | None) -> None:
    if requested_status == ToolStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Use publish endpoint to publish this tool")


async def _validate_retrieval_pipeline_config_if_needed(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    implementation_type: ToolImplementationType,
    config_schema: dict | None,
) -> None:
    if implementation_type != ToolImplementationType.RAG_RETRIEVAL:
        return
    implementation = (config_schema or {}).get("implementation")
    pipeline_id = implementation.get("pipeline_id") if isinstance(implementation, dict) else None
    await _validate_retrieval_pipeline_for_tenant(
        db,
        tenant_id=tenant_id,
        pipeline_id_raw=pipeline_id,
    )


@router.get("", response_model=ToolListResponse)
async def list_tools(
    scope: Optional[ToolDefinitionScope] = None,
    is_active: Optional[bool] = True,
    status: Optional[ToolStatus] = None,
    implementation_type: Optional[ToolImplementationType] = None,
    tool_type: Optional[str] = Query(None, description="Primary tool bucket: built_in, mcp, artifact, custom"),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    conditions = [or_(ToolRegistry.tenant_id == tid, ToolRegistry.tenant_id == None)]
    if scope:
        conditions.append(ToolRegistry.scope == scope)
    if status is not None:
        conditions.append(ToolRegistry.status == status)
    elif is_active is not None:
        conditions.append(ToolRegistry.is_active == is_active)
    if implementation_type is not None:
        conditions.append(ToolRegistry.implementation_type == implementation_type)

    if tool_type in {"built_in", "mcp", "artifact", "custom"}:
        built_in_pred = or_(
            ToolRegistry.is_system == True,
            ToolRegistry.is_builtin_template == True,
            ToolRegistry.builtin_key != None,
            and_(ToolRegistry.tenant_id == None, ToolRegistry.implementation_type == ToolImplementationType.INTERNAL),
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

    stmt = (
        select(ToolRegistry)
        .where(and_(*conditions))
        .order_by(ToolRegistry.name.asc())
        .offset(skip)
        .limit(limit)
    )
    tools = (await db.execute(stmt)).scalars().all()

    count_stmt = select(func.count(ToolRegistry.id)).where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar() or 0

    return ToolListResponse(tools=[_serialize_tool(t) for t in tools], total=total)


@router.get("/builtins/templates", response_model=ToolListResponse)
async def list_builtin_templates(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_tools_context),
):
    _ensure_builtin_tools_enabled()

    stmt = (
        select(ToolRegistry)
        .where(
            ToolRegistry.tenant_id == None,
            ToolRegistry.is_builtin_template == True,
            ToolRegistry.builtin_key != None,
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
                ToolRegistry.is_builtin_template == True,
                ToolRegistry.builtin_key != None,
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
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    if request.scope != ToolDefinitionScope.TENANT:
        raise HTTPException(status_code=400, detail="Only tenant-scoped tools can be created via this endpoint")

    await _ensure_slug_available(db, request.slug)

    config_schema = _compose_config_schema(
        current=request.config_schema,
        config_schema=request.config_schema,
        implementation_config=request.implementation_config,
        execution_config=request.execution_config,
        implementation_type=request.implementation_type,
    )

    impl_type = request.implementation_type
    if impl_type is None:
        probe = ToolRegistry(
            tenant_id=tid,
            name=request.name,
            slug=request.slug,
            description=request.description,
            scope=request.scope,
            schema={"input": request.input_schema, "output": request.output_schema},
            config_schema=config_schema,
            artifact_id=request.artifact_id,
            artifact_version=request.artifact_version,
            is_active=True,
            is_system=False,
        )
        impl_type = _get_tool_impl_type(probe)

    requested_status = request.status or ToolStatus.DRAFT
    _maybe_validate_builtin_registry_status(requested_status)
    await _validate_retrieval_pipeline_config_if_needed(
        db=db,
        tenant_id=tid,
        implementation_type=impl_type,
        config_schema=config_schema,
    )

    tool = ToolRegistry(
        tenant_id=tid,
        name=request.name,
        slug=request.slug,
        description=request.description,
        scope=request.scope,
        schema={"input": request.input_schema, "output": request.output_schema},
        config_schema=config_schema,
        implementation_type=impl_type,
        status=requested_status,
        version="1.0.0",
        published_at=None,
        artifact_id=request.artifact_id,
        artifact_version=request.artifact_version,
        builtin_key=None,
        builtin_template_id=None,
        is_builtin_template=False,
        is_active=requested_status != ToolStatus.DISABLED,
        is_system=False,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return _serialize_tool(tool)


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    tool = (
        await db.execute(
            select(ToolRegistry).where(
                ToolRegistry.id == tool_id,
                or_(ToolRegistry.tenant_id == tid, ToolRegistry.tenant_id == None),
            )
        )
    ).scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _serialize_tool(tool)


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: uuid.UUID,
    request: UpdateToolRequest,
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
        raise HTTPException(status_code=400, detail="Cannot modify system tools")
    if _is_builtin_instance(tool):
        raise HTTPException(status_code=404, detail="Tool not found")

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

    tool.config_schema = _compose_config_schema(
        current=tool.config_schema,
        config_schema=request.config_schema,
        implementation_config=request.implementation_config,
        execution_config=request.execution_config,
        implementation_type=request.implementation_type,
    )

    if request.artifact_id is not None:
        tool.artifact_id = request.artifact_id
    if request.artifact_version is not None:
        tool.artifact_version = request.artifact_version
    if request.implementation_type is not None:
        tool.implementation_type = request.implementation_type

    if request.status is not None:
        if request.status == ToolStatus.PUBLISHED and _status_value(tool) != "published":
            raise HTTPException(status_code=400, detail="Use POST /tools/{tool_id}/publish to publish a tool")
        tool.status = request.status
        if request.status == ToolStatus.DISABLED:
            tool.is_active = False
        elif request.is_active is None:
            tool.is_active = True

    if request.is_active is not None:
        tool.is_active = request.is_active

    effective_impl_type = _get_tool_impl_type(tool)
    await _validate_retrieval_pipeline_config_if_needed(
        db=db,
        tenant_id=tid,
        implementation_type=effective_impl_type,
        config_schema=tool.config_schema,
    )

    await db.commit()
    await db.refresh(tool)
    return _serialize_tool(tool)


@router.post("/{tool_id}/publish", response_model=ToolResponse)
async def publish_tool(
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
        raise HTTPException(status_code=400, detail="Cannot publish system tools")
    if _is_builtin_instance(tool):
        raise HTTPException(status_code=404, detail="Tool not found")

    await _validate_retrieval_pipeline_config_if_needed(
        db=db,
        tenant_id=tid,
        implementation_type=_get_tool_impl_type(tool),
        config_schema=tool.config_schema,
    )

    tool = await _publish_tool(db=db, tool=tool, tenant_ctx=tenant_ctx, principal=principal, tenant_id=tid)
    return _serialize_tool(tool)


@router.post("/{tool_id}/version", response_model=ToolResponse)
async def create_tool_version(
    tool_id: uuid.UUID,
    new_version: str = Query(..., description="New semver version"),
    _: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tools_context),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    if not re.match(r"^\d+\.\d+\.\d+$", new_version):
        raise HTTPException(status_code=400, detail="new_version must be valid semver (e.g. 1.0.0)")

    tool = (
        await db.execute(select(ToolRegistry).where(ToolRegistry.id == tool_id, ToolRegistry.tenant_id == tid))
    ).scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.is_system:
        raise HTTPException(status_code=400, detail="Cannot version system tools")

    snapshot = {
        "schema": tool.schema or {},
        "config_schema": tool.config_schema or {},
        "implementation_type": _enum_name(tool.implementation_type),
        "version": new_version,
    }
    actor = tenant_ctx.get("user")
    db.add(
        ToolVersion(
            tool_id=tool.id,
            version=new_version,
            schema_snapshot=snapshot,
            created_by=actor.id if actor else None,
        )
    )
    tool.version = new_version
    await db.commit()
    await db.refresh(tool)
    return _serialize_tool(tool)


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
