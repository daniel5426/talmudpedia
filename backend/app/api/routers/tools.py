from datetime import datetime
from typing import Optional
import uuid
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, func, text
from sqlalchemy.exc import ProgrammingError

from app.db.postgres.models.registry import (
    ToolRegistry,
    ToolVersion,
    ToolDefinitionScope,
    ToolStatus,
    ToolImplementationType,
)
from app.db.postgres.session import get_db
from app.api.dependencies import get_current_user, get_tenant_context

router = APIRouter(prefix="/tools", tags=["tools"])

# ============================================================================
# Request/Response Schemas
# ============================================================================

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
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime

class ToolListResponse(BaseModel):
    tools: list[ToolResponse]
    total: int

def _get_tool_impl_type(tool: ToolRegistry) -> ToolImplementationType:
    if getattr(tool, "implementation_type", None):
        return tool.implementation_type
    config_schema = getattr(tool, "config_schema", {}) or {}
    impl_type = (config_schema.get("implementation") or {}).get("type")
    if impl_type in [t.value for t in ToolImplementationType]:
        return ToolImplementationType(impl_type)
    if getattr(tool, "artifact_id", None):
        return ToolImplementationType.ARTIFACT
    if getattr(tool, "is_system", False):
        return ToolImplementationType.INTERNAL
    return ToolImplementationType.CUSTOM

def _get_tool_type(tool: ToolRegistry, impl_type: ToolImplementationType) -> str:
    if getattr(tool, "is_system", False) or (tool.tenant_id is None and impl_type == ToolImplementationType.INTERNAL):
        return "built_in"
    config_schema = getattr(tool, "config_schema", {}) or {}
    if impl_type == ToolImplementationType.MCP or (config_schema.get("implementation") or {}).get("type") == "mcp":
        return "mcp"
    if getattr(tool, "artifact_id", None) or impl_type == ToolImplementationType.ARTIFACT:
        return "artifact"
    return "custom"

# ============================================================================
# Endpoints
# ============================================================================

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
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """List all tools for the current tenant or global tools."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    try:
        conditions = [
            (ToolRegistry.tenant_id == tid) | (ToolRegistry.tenant_id == None),
        ]
        if scope:
            conditions.append(ToolRegistry.scope == scope)
        if status is not None:
            conditions.append(ToolRegistry.status == status)
        elif is_active is not None:
            conditions.append(ToolRegistry.is_active == is_active)
        if implementation_type is not None:
            conditions.append(ToolRegistry.implementation_type == implementation_type)

        if tool_type in {"built_in", "mcp", "artifact", "custom"}:
            if tool_type == "built_in":
                conditions.append(
                    (ToolRegistry.is_system == True) | (
                        (ToolRegistry.tenant_id == None) & (ToolRegistry.implementation_type == ToolImplementationType.INTERNAL)
                    )
                )
            elif tool_type == "mcp":
                conditions.append(
                    (ToolRegistry.implementation_type == ToolImplementationType.MCP) |
                    (ToolRegistry.config_schema["implementation"]["type"].astext == "mcp")
                )
            elif tool_type == "artifact":
                conditions.append(
                    (ToolRegistry.artifact_id != None) | (ToolRegistry.implementation_type == ToolImplementationType.ARTIFACT)
                )
            elif tool_type == "custom":
                conditions.append(
                    ~(
                        (ToolRegistry.is_system == True) |
                        ((ToolRegistry.tenant_id == None) & (ToolRegistry.implementation_type == ToolImplementationType.INTERNAL)) |
                        (ToolRegistry.implementation_type == ToolImplementationType.MCP) |
                        (ToolRegistry.config_schema["implementation"]["type"].astext == "mcp") |
                        (ToolRegistry.artifact_id != None) |
                        (ToolRegistry.implementation_type == ToolImplementationType.ARTIFACT)
                    )
                )

        stmt = select(ToolRegistry).where(and_(*conditions)).offset(skip).limit(limit).order_by(ToolRegistry.name.asc())

        result = await db.execute(stmt)
        tools = result.scalars().all()

        count_stmt = select(func.count(ToolRegistry.id)).where(and_(*conditions))
        total_res = await db.execute(count_stmt)
        total = total_res.scalar()

        return ToolListResponse(
            tools=[ToolResponse(
                id=t.id,
                tenant_id=t.tenant_id,
                name=t.name,
                slug=t.slug,
                description=t.description,
                scope=t.scope.value,
                input_schema=t.schema.get("input", {}),
                output_schema=t.schema.get("output", {}),
                config_schema=t.config_schema or {},
                status=t.status,
                version=t.version,
                implementation_type=_get_tool_impl_type(t),
                published_at=t.published_at,
                tool_type=_get_tool_type(t, _get_tool_impl_type(t)),
                artifact_id=t.artifact_id,
                artifact_version=t.artifact_version,
                is_active=t.is_active,
                is_system=t.is_system,
                created_at=t.created_at,
                updated_at=t.updated_at
            ) for t in tools],
            total=total
        )
    except ProgrammingError:
        # Fallback for legacy schema without artifact columns
        await db.rollback()
        raw = await db.execute(
            text(
                """
                SELECT id, tenant_id, name, slug, description, scope, schema, config_schema,
                       is_active, is_system, created_at, updated_at
                FROM tool_registry
                WHERE (tenant_id = :tid OR tenant_id IS NULL)
                  AND is_active = :is_active
                ORDER BY name ASC
                LIMIT :limit OFFSET :skip
                """
            ),
            {"tid": str(tid), "is_active": is_active, "limit": limit, "skip": skip},
        )
        rows = raw.fetchall()

        count_raw = await db.execute(
            text(
                """
                SELECT COUNT(id)
                FROM tool_registry
                WHERE (tenant_id = :tid OR tenant_id IS NULL)
                """
            ),
            {"tid": str(tid)},
        )
        total = count_raw.scalar() or 0

        tools = []
        for row in rows:
            config_schema = row[7] or {}
            impl_type_val = (config_schema.get("implementation") or {}).get("type")
            impl_type = ToolImplementationType(impl_type_val) if impl_type_val in [t.value for t in ToolImplementationType] else ToolImplementationType.CUSTOM
            tool_type_val = "custom"
            if row[9]:
                tool_type_val = "built_in"
            elif impl_type == ToolImplementationType.MCP:
                tool_type_val = "mcp"
            tools.append(ToolResponse(
                id=row[0],
                tenant_id=row[1],
                name=row[2],
                slug=row[3],
                description=row[4],
                scope=row[5],
                input_schema=(row[6] or {}).get("input", {}),
                output_schema=(row[6] or {}).get("output", {}),
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED if row[8] else ToolStatus.DISABLED,
                version="1.0.0",
                implementation_type=impl_type,
                published_at=row[10] if row[8] else None,
                tool_type=tool_type_val,
                artifact_id=None,
                artifact_version=None,
                is_active=row[8],
                is_system=row[9],
                created_at=row[10],
                updated_at=row[11],
            ))

        return ToolListResponse(tools=tools, total=total)

@router.post("", response_model=ToolResponse)
async def create_tool(
    request: CreateToolRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Create a new tool definition."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    # Check for duplicate slug
    stmt = select(ToolRegistry).where(ToolRegistry.slug == request.slug)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Tool with slug '{request.slug}' already exists")
    
    config_schema = request.config_schema or {}
    if request.implementation_config:
        config_schema["implementation"] = request.implementation_config
    elif request.implementation_type:
        config_schema.setdefault("implementation", {"type": request.implementation_type.value})
    if request.execution_config:
        config_schema["execution"] = request.execution_config

    impl_type = request.implementation_type
    if impl_type is None:
        impl_type = _get_tool_impl_type(ToolRegistry(
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
        ))

    requested_status = request.status or ToolStatus.DRAFT
    published_at = datetime.utcnow() if requested_status == ToolStatus.PUBLISHED else None
    is_active = requested_status != ToolStatus.DISABLED
    new_tool = ToolRegistry(
        tenant_id=tid if request.scope == ToolDefinitionScope.TENANT else None,
        name=request.name,
        slug=request.slug,
        description=request.description,
        scope=request.scope,
        schema={
            "input": request.input_schema,
            "output": request.output_schema
        },
        config_schema=config_schema,
        implementation_type=impl_type,
        status=requested_status,
        version="1.0.0",
        published_at=published_at,
        artifact_id=request.artifact_id,
        artifact_version=request.artifact_version,
        is_active=is_active,
        is_system=False
    )
    
    db.add(new_tool)
    await db.commit()
    await db.refresh(new_tool)
    
    return ToolResponse(
        id=new_tool.id,
        tenant_id=new_tool.tenant_id,
        name=new_tool.name,
        slug=new_tool.slug,
        description=new_tool.description,
        scope=new_tool.scope.value,
        input_schema=new_tool.schema.get("input", {}),
        output_schema=new_tool.schema.get("output", {}),
        config_schema=new_tool.config_schema or {},
        status=new_tool.status,
        version=new_tool.version,
        implementation_type=_get_tool_impl_type(new_tool),
        published_at=new_tool.published_at,
        tool_type=_get_tool_type(new_tool, _get_tool_impl_type(new_tool)),
        artifact_id=new_tool.artifact_id,
        artifact_version=new_tool.artifact_version,
        is_active=new_tool.is_active,
        is_system=new_tool.is_system,
        created_at=new_tool.created_at,
        updated_at=new_tool.updated_at
    )

@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Get a specific tool by ID."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ToolRegistry).where(
        and_(
            ToolRegistry.id == tool_id,
            (ToolRegistry.tenant_id == tid) | (ToolRegistry.tenant_id == None)
        )
    )
    res = await db.execute(stmt)
    tool = res.scalar_one_or_none()
    
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
        
    return ToolResponse(
        id=tool.id,
        tenant_id=tool.tenant_id,
        name=tool.name,
        slug=tool.slug,
        description=tool.description,
        scope=tool.scope.value,
        input_schema=tool.schema.get("input", {}),
        output_schema=tool.schema.get("output", {}),
        config_schema=tool.config_schema or {},
        status=tool.status,
        version=tool.version,
        implementation_type=_get_tool_impl_type(tool),
        published_at=tool.published_at,
        tool_type=_get_tool_type(tool, _get_tool_impl_type(tool)),
        artifact_id=tool.artifact_id,
        artifact_version=tool.artifact_version,
        is_active=tool.is_active,
        is_system=tool.is_system,
        created_at=tool.created_at,
        updated_at=tool.updated_at
    )

@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: uuid.UUID,
    request: UpdateToolRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Update a tool definition."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ToolRegistry).where(
        and_(ToolRegistry.id == tool_id, ToolRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    tool = res.scalar_one_or_none()
    
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
        
    if tool.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system tools")
        
    if request.name is not None:
        tool.name = request.name
    if request.description is not None:
        tool.description = request.description
    
    # Update nested schema
    current_schema = dict(tool.schema or {})
    if request.input_schema is not None:
        current_schema["input"] = request.input_schema
    if request.output_schema is not None:
        current_schema["output"] = request.output_schema
    tool.schema = current_schema
    
    config_schema = dict(tool.config_schema or {})
    if request.config_schema is not None:
        config_schema = request.config_schema
    if request.implementation_config is not None:
        config_schema["implementation"] = request.implementation_config
    elif request.implementation_type is not None:
        config_schema.setdefault("implementation", {"type": request.implementation_type.value})
    if request.execution_config is not None:
        config_schema["execution"] = request.execution_config
    tool.config_schema = config_schema
    
    if request.artifact_id is not None:
        tool.artifact_id = request.artifact_id
    if request.artifact_version is not None:
        tool.artifact_version = request.artifact_version
    if request.implementation_type is not None:
        tool.implementation_type = request.implementation_type

    if request.status is not None:
        tool.status = request.status
        if request.status == ToolStatus.PUBLISHED and tool.published_at is None:
            tool.published_at = datetime.utcnow()
        if request.status == ToolStatus.DISABLED:
            tool.is_active = False
        elif request.is_active is None:
            tool.is_active = True

    if request.is_active is not None:
        tool.is_active = request.is_active
        
    await db.commit()
    await db.refresh(tool)
    
    return await get_tool(tool.id, db, tenant_ctx, current_user)

@router.post("/{tool_id}/publish", response_model=ToolResponse)
async def publish_tool(
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Publish a tool and snapshot its schema."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    stmt = select(ToolRegistry).where(
        and_(ToolRegistry.id == tool_id, ToolRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    tool = res.scalar_one_or_none()

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.is_system:
        raise HTTPException(status_code=400, detail="Cannot publish system tools")

    tool.status = ToolStatus.PUBLISHED
    tool.is_active = True
    tool.published_at = tool.published_at or datetime.utcnow()

    snapshot = {
        "schema": tool.schema or {},
        "config_schema": tool.config_schema or {},
        "implementation_type": tool.implementation_type.value if tool.implementation_type else None,
        "version": tool.version,
    }
    version_entry = ToolVersion(
        tool_id=tool.id,
        version=tool.version,
        schema_snapshot=snapshot,
        created_by=current_user.id if current_user else None,
    )
    db.add(version_entry)
    await db.commit()
    await db.refresh(tool)

    return await get_tool(tool.id, db, tenant_ctx, current_user)

@router.post("/{tool_id}/version", response_model=ToolResponse)
async def create_tool_version(
    tool_id: uuid.UUID,
    new_version: str = Query(..., description="New semver version"),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Create a new tool version snapshot and bump version in registry."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    if not re.match(r"^\\d+\\.\\d+\\.\\d+$", new_version):
        raise HTTPException(status_code=400, detail="new_version must be valid semver (e.g. 1.0.0)")

    stmt = select(ToolRegistry).where(
        and_(ToolRegistry.id == tool_id, ToolRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    tool = res.scalar_one_or_none()

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.is_system:
        raise HTTPException(status_code=400, detail="Cannot version system tools")

    snapshot = {
        "schema": tool.schema or {},
        "config_schema": tool.config_schema or {},
        "implementation_type": tool.implementation_type.value if tool.implementation_type else None,
        "version": new_version,
    }
    version_entry = ToolVersion(
        tool_id=tool.id,
        version=new_version,
        schema_snapshot=snapshot,
        created_by=current_user.id if current_user else None,
    )
    db.add(version_entry)
    tool.version = new_version
    await db.commit()
    await db.refresh(tool)

    return await get_tool(tool.id, db, tenant_ctx, current_user)

@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Delete a tool (only custom tenant tools can be deleted)."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ToolRegistry).where(
        and_(ToolRegistry.id == tool_id, ToolRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    tool = res.scalar_one_or_none()
    
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
        
    if tool.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system tools")
        
    await db.delete(tool)
    await db.commit()
    
    return {"status": "deleted", "id": tool_id}
