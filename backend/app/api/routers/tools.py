"""
Tools Registry API - CRUD operations for tool definitions.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId

from app.db.models.tool_registry import (
    ToolDefinition,
    ToolExecution,
    ToolImplementationType,
    ToolStatus,
    ToolFailurePolicy,
    ToolExecutionStatus,
)
from app.db.connection import MongoDatabase
from app.api.dependencies import get_current_user, get_tenant_context

router = APIRouter(prefix="/tools", tags=["tools"])


# ============================================================================
# Request/Response Schemas
# ============================================================================

class CreateToolRequest(BaseModel):
    name: str
    slug: str
    description: str
    input_schema: dict
    output_schema: dict
    implementation_type: ToolImplementationType
    implementation_config: Optional[dict] = None
    execution_config: Optional[dict] = None


class UpdateToolRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    implementation_config: Optional[dict] = None
    execution_config: Optional[dict] = None


class TestToolRequest(BaseModel):
    input: dict


class ToolResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    input_schema: dict
    output_schema: dict
    implementation_type: str
    implementation_config: dict
    execution_config: dict
    version: str
    status: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class ToolListResponse(BaseModel):
    tools: list[ToolResponse]
    total: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=ToolListResponse)
async def list_tools(
    implementation_type: Optional[ToolImplementationType] = None,
    status: Optional[ToolStatus] = None,
    skip: int = 0,
    limit: int = 50,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """List all tools for the current tenant."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    query = {"tenant_id": ObjectId(tenant_ctx["tenant_id"])}
    if implementation_type:
        query["implementation_type"] = implementation_type.value
    if status:
        query["status"] = status.value
    
    total = await collection.count_documents(query)
    cursor = collection.find(query).skip(skip).limit(limit).sort("name", 1)
    tools = await cursor.to_list(length=limit)
    
    return ToolListResponse(
        tools=[ToolResponse(
            id=str(t["_id"]),
            name=t["name"],
            slug=t["slug"],
            description=t["description"],
            input_schema=t.get("input_schema", {}),
            output_schema=t.get("output_schema", {}),
            implementation_type=t["implementation_type"],
            implementation_config=t.get("implementation_config", {}),
            execution_config=t.get("execution_config", {}),
            version=t.get("version", "1.0.0"),
            status=t.get("status", "draft"),
            tenant_id=str(t["tenant_id"]),
            created_at=t["created_at"],
            updated_at=t["updated_at"],
            published_at=t.get("published_at"),
        ) for t in tools],
        total=total
    )


@router.post("", response_model=ToolResponse)
async def create_tool(
    request: CreateToolRequest,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Create a new tool definition."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    # Check for duplicate slug
    existing = await collection.find_one({
        "slug": request.slug,
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if existing:
        raise HTTPException(status_code=400, detail=f"Tool with slug '{request.slug}' already exists")
    
    tool_doc = {
        "name": request.name,
        "slug": request.slug,
        "description": request.description,
        "input_schema": request.input_schema,
        "output_schema": request.output_schema,
        "implementation_type": request.implementation_type.value,
        "implementation_config": request.implementation_config or {},
        "execution_config": request.execution_config or {
            "timeout_seconds": 30,
            "retry_config": {
                "max_attempts": 3,
                "backoff_multiplier": 2.0,
                "initial_delay_ms": 1000,
                "max_delay_ms": 30000,
            },
            "failure_policy": ToolFailurePolicy.FAIL_FAST.value,
            "circuit_breaker_threshold": 5,
        },
        "tenant_id": ObjectId(tenant_ctx["tenant_id"]),
        "version": "1.0.0",
        "status": ToolStatus.DRAFT.value,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": ObjectId(current_user["id"]) if current_user.get("id") else None,
    }
    
    result = await collection.insert_one(tool_doc)
    tool_doc["_id"] = result.inserted_id
    
    return ToolResponse(
        id=str(tool_doc["_id"]),
        name=tool_doc["name"],
        slug=tool_doc["slug"],
        description=tool_doc["description"],
        input_schema=tool_doc["input_schema"],
        output_schema=tool_doc["output_schema"],
        implementation_type=tool_doc["implementation_type"],
        implementation_config=tool_doc["implementation_config"],
        execution_config=tool_doc["execution_config"],
        version=tool_doc["version"],
        status=tool_doc["status"],
        tenant_id=str(tool_doc["tenant_id"]),
        created_at=tool_doc["created_at"],
        updated_at=tool_doc["updated_at"],
    )


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Get a specific tool by ID."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    tool = await collection.find_one({
        "_id": ObjectId(tool_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    return ToolResponse(
        id=str(tool["_id"]),
        name=tool["name"],
        slug=tool["slug"],
        description=tool["description"],
        input_schema=tool.get("input_schema", {}),
        output_schema=tool.get("output_schema", {}),
        implementation_type=tool["implementation_type"],
        implementation_config=tool.get("implementation_config", {}),
        execution_config=tool.get("execution_config", {}),
        version=tool.get("version", "1.0.0"),
        status=tool.get("status", "draft"),
        tenant_id=str(tool["tenant_id"]),
        created_at=tool["created_at"],
        updated_at=tool["updated_at"],
        published_at=tool.get("published_at"),
    )


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: str,
    request: UpdateToolRequest,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Update a tool definition (only drafts can be modified)."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    tool = await collection.find_one({
        "_id": ObjectId(tool_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    if tool.get("status") == ToolStatus.PUBLISHED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify published tool. Create a new version instead."
        )
    
    update_doc = {"updated_at": datetime.utcnow()}
    if request.name is not None:
        update_doc["name"] = request.name
    if request.description is not None:
        update_doc["description"] = request.description
    if request.input_schema is not None:
        update_doc["input_schema"] = request.input_schema
    if request.output_schema is not None:
        update_doc["output_schema"] = request.output_schema
    if request.implementation_config is not None:
        update_doc["implementation_config"] = request.implementation_config
    if request.execution_config is not None:
        update_doc["execution_config"] = request.execution_config
    
    await collection.update_one({"_id": ObjectId(tool_id)}, {"$set": update_doc})
    
    return await get_tool(tool_id, tenant_ctx, current_user)


@router.post("/{tool_id}/publish", response_model=ToolResponse)
async def publish_tool(
    tool_id: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Publish a tool, making it immutable and available for use."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    tool = await collection.find_one({
        "_id": ObjectId(tool_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    if tool.get("status") == ToolStatus.PUBLISHED.value:
        raise HTTPException(status_code=400, detail="Tool is already published")
    
    await collection.update_one(
        {"_id": ObjectId(tool_id)},
        {
            "$set": {
                "status": ToolStatus.PUBLISHED.value,
                "published_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        }
    )
    
    return await get_tool(tool_id, tenant_ctx, current_user)


@router.post("/{tool_id}/version", response_model=ToolResponse)
async def create_new_version(
    tool_id: str,
    new_version: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Create a new draft version of a tool."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    tool = await collection.find_one({
        "_id": ObjectId(tool_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Create new document as draft
    new_tool = {k: v for k, v in tool.items() if k != "_id"}
    new_tool["version"] = new_version
    new_tool["status"] = ToolStatus.DRAFT.value
    new_tool["created_at"] = datetime.utcnow()
    new_tool["updated_at"] = datetime.utcnow()
    new_tool["published_at"] = None
    
    result = await collection.insert_one(new_tool)
    
    return await get_tool(str(result.inserted_id), tenant_ctx, current_user)


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Delete a tool (only drafts can be deleted)."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    tool = await collection.find_one({
        "_id": ObjectId(tool_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    if tool.get("status") == ToolStatus.PUBLISHED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete published tool. Deprecate it instead."
        )
    
    await collection.delete_one({"_id": ObjectId(tool_id)})
    
    return {"status": "deleted", "id": tool_id}


@router.post("/{tool_id}/test")
async def test_tool(
    tool_id: str,
    request: TestToolRequest,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Test a tool execution with sample input."""
    db = MongoDatabase.get_db()
    collection = db["tool_definitions"]
    
    tool = await collection.find_one({
        "_id": ObjectId(tool_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # TODO: Implement actual tool execution
    # For now, return a mock response showing the tool would be invoked
    
    return {
        "tool_id": tool_id,
        "tool_name": tool["name"],
        "input": request.input,
        "status": "mock_success",
        "message": "Tool execution not yet implemented. This is a placeholder response.",
        "output": None,
    }
