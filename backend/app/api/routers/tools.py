from datetime import datetime
from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, func, text
from sqlalchemy.exc import ProgrammingError

from app.db.postgres.models.registry import ToolRegistry, ToolVersion, ToolDefinitionScope
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
    scope: ToolDefinitionScope = ToolDefinitionScope.TENANT
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None

class UpdateToolRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    config_schema: Optional[dict] = None
    is_active: Optional[bool] = None
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None

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
    artifact_id: Optional[str] = None
    artifact_version: Optional[str] = None
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime

class ToolListResponse(BaseModel):
    tools: list[ToolResponse]
    total: int

# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=ToolListResponse)
async def list_tools(
    scope: Optional[ToolDefinitionScope] = None,
    is_active: bool = True,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """List all tools for the current tenant or global tools."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    try:
        stmt = select(ToolRegistry).where(
            and_(
                (ToolRegistry.tenant_id == tid) | (ToolRegistry.tenant_id == None),
                ToolRegistry.is_active == is_active
            )
        ).offset(skip).limit(limit).order_by(ToolRegistry.name.asc())

        result = await db.execute(stmt)
        tools = result.scalars().all()

        count_stmt = select(func.count(ToolRegistry.id)).where(
            (ToolRegistry.tenant_id == tid) | (ToolRegistry.tenant_id == None)
        )
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
            tools.append(ToolResponse(
                id=row[0],
                tenant_id=row[1],
                name=row[2],
                slug=row[3],
                description=row[4],
                scope=row[5],
                input_schema=(row[6] or {}).get("input", {}),
                output_schema=(row[6] or {}).get("output", {}),
                config_schema=row[7] or {},
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
        config_schema=request.config_schema or {},
        artifact_id=request.artifact_id,
        artifact_version=request.artifact_version,
        is_active=True,
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
    
    if request.config_schema is not None:
        tool.config_schema = request.config_schema
    
    if request.artifact_id is not None:
        tool.artifact_id = request.artifact_id
    if request.artifact_version is not None:
        tool.artifact_version = request.artifact_version

    if request.is_active is not None:
        tool.is_active = request.is_active
        
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
