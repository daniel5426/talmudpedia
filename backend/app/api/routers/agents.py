"""
Agents API Router - Thin dispatch layer for agent endpoints.

Routers should only: Validate, Authenticate, Dispatch.
All business logic lives in AgentService.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.postgres.session import get_db
from app.db.postgres.models.identity import Tenant
from app.services.agent_service import (
    AgentService,
    CreateAgentData,
    UpdateAgentData,
    ExecuteAgentData,
    AgentServiceError,
    AgentNotFoundError,
    AgentSlugExistsError,
    AgentPublishedError,
    AgentNotPublishedError,
)
from app.api.schemas.agents import (
    CreateAgentRequest,
    UpdateAgentRequest,
    GraphDefinitionSchema,
    AgentResponse,
    AgentListResponse,
    ExecuteAgentRequest,
    ExecuteAgentResponse,
)
from sqlalchemy import select


router = APIRouter(prefix="/agents", tags=["agents"])


# =============================================================================
# Helpers
# =============================================================================

async def get_tenant_id(db: AsyncSession) -> UUID:
    """Get current tenant ID - placeholder for auth integration."""
    result = await db.execute(select(Tenant).limit(1))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=500, detail="No tenant configured")
    return tenant.id


def agent_to_response(agent) -> AgentResponse:
    """Convert Agent model to response."""
    return AgentResponse(
        id=str(agent.id),
        tenant_id=str(agent.tenant_id),
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        graph_definition=agent.graph_definition or {"nodes": [], "edges": []},
        memory_config=agent.memory_config or {},
        execution_constraints=agent.execution_constraints or {},
        version=agent.version,
        status=agent.status.value if hasattr(agent.status, "value") else (agent.status or "draft"),

        is_active=agent.is_active,
        is_public=agent.is_public,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        published_at=agent.published_at,
    )


def handle_service_error(e: AgentServiceError):
    """Map service errors to HTTP responses."""
    if isinstance(e, AgentNotFoundError):
        raise HTTPException(status_code=404, detail=e.message)
    if isinstance(e, AgentSlugExistsError):
        raise HTTPException(status_code=400, detail=e.message)
    if isinstance(e, AgentPublishedError):
        raise HTTPException(status_code=400, detail=e.message)
    if isinstance(e, AgentNotPublishedError):
        raise HTTPException(status_code=400, detail=e.message)
    raise HTTPException(status_code=500, detail=e.message)


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.get("", response_model=AgentListResponse)
async def list_agents(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List all agents."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    agents, total = await service.list_agents(status=status, skip=skip, limit=limit)
    
    return AgentListResponse(
        agents=[agent_to_response(a) for a in agents],
        total=total
    )


@router.post("", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.create_agent(CreateAgentData(
            name=request.name,
            slug=request.slug,
            description=request.description,
            graph_definition=request.graph_definition.model_dump() if request.graph_definition else None,
            memory_config=request.memory_config,
            execution_constraints=request.execution_constraints,
        ))
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get an agent by ID."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.get_agent(UUID(agent_id))
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.update_agent(UUID(agent_id), UpdateAgentData(
            name=request.name,
            description=request.description,
            graph_definition=request.graph_definition.model_dump() if request.graph_definition else None,
            memory_config=request.memory_config,
            execution_constraints=request.execution_constraints,
        ))
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.put("/{agent_id}/graph", response_model=AgentResponse)
async def update_graph(
    agent_id: str,
    request: GraphDefinitionSchema,
    db: AsyncSession = Depends(get_db),
):
    """Update agent graph."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.update_graph(UUID(agent_id), request.model_dump())
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Delete or archive an agent."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        return await service.delete_agent(UUID(agent_id))
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Validation & Publishing
# =============================================================================

@router.post("/{agent_id}/validate")
async def validate_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Validate agent graph."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        result = await service.validate_agent(UUID(agent_id))
        return {"valid": result.valid, "errors": result.errors}
    except AgentServiceError as e:
        handle_service_error(e)


@router.post("/{agent_id}/publish", response_model=AgentResponse)
async def publish_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Publish an agent."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.publish_agent(UUID(agent_id))
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Versioning
# =============================================================================

@router.get("/{agent_id}/versions")
async def list_versions(agent_id: str, db: AsyncSession = Depends(get_db)):
    """List agent versions."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        versions = await service.list_versions(UUID(agent_id))
        return {"versions": versions}
    except AgentServiceError as e:
        handle_service_error(e)


@router.get("/{agent_id}/versions/{version}")
async def get_version(agent_id: str, version: int, db: AsyncSession = Depends(get_db)):
    """Get specific version."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        return await service.get_version(UUID(agent_id), version)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Execution
# =============================================================================

@router.post("/{agent_id}/execute", response_model=ExecuteAgentResponse)
async def execute_agent(
    agent_id: str,
    request: ExecuteAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute a published agent."""
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        result = await service.execute_agent(UUID(agent_id), ExecuteAgentData(
            input=request.input,
            messages=request.messages,
            context=request.context,
        ))
        return ExecuteAgentResponse(
            run_id=result.run_id,
            output=result.output,
            steps=result.steps,
            messages=result.messages,
            usage=result.usage,
        )
    except AgentServiceError as e:
        handle_service_error(e)


@router.post("/{agent_id}/stream")
async def stream_agent(
    agent_id: str,
    request: ExecuteAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Stream agent execution (SSE)."""
    from app.agent.graph.schema import AgentGraph, MemoryConfig, ExecutionConstraints
    from app.agent.graph.compiler import AgentCompiler
    
    tenant_id = await get_tenant_id(db)
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.get_agent(UUID(agent_id))
    except AgentServiceError as e:
        handle_service_error(e)
    
    async def event_generator():
        try:
            graph = AgentGraph(**agent.graph_definition)
            memory_config = MemoryConfig(**agent.memory_config)
            execution_constraints = ExecutionConstraints(**agent.execution_constraints)
            
            compiler = AgentCompiler(tenant_id=tenant_id, db=db)
            executable = await compiler.compile(
                agent_id=agent.id,
                version=agent.version,
                graph=graph,
                memory_config=memory_config,
                execution_constraints=execution_constraints,
            )
            
            initial_messages = request.messages.copy()
            if request.input:
                initial_messages.append({"role": "user", "content": request.input})
            
            async for event in executable.stream({"messages": initial_messages, "steps": []}):
                yield f"data: {json.dumps(event)}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
