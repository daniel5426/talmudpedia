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
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import User, OrgMembership, OrgRole
from typing import Dict, Any
import jwt
from app.core.security import SECRET_KEY, ALGORITHM
from fastapi import Request

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
from typing import Optional


router = APIRouter(prefix="/agents", tags=["agents"])


# =============================================================================
# Helpers
# =============================================================================

async def get_agent_context(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns a context dict with 'user' and 'tenant_id'.
    Users can manage agents if they are System Admins OR have an Org role.
    """
    # Identify tenant via membership
    result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == current_user.id).limit(1)
    )
    membership = result.scalar_one_or_none()
    
    if membership:
        return {"user": current_user, "tenant_id": membership.tenant_id}
    
    # If admin and no membership (true system admin), they can see everything but creation might fail
    if current_user.role == "admin":
         return {"user": current_user, "tenant_id": None}
        
    raise HTTPException(status_code=403, detail="Not authorized to manage agents")


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
# Catalog Endpoint
# =============================================================================

@router.get("/operators")
async def list_operators(
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """
    List all available agent operators including artifacts.
    """
    from app.agent.registry import AgentOperatorRegistry
    
    # Ensure artifacts are registered (lazy load if needed)
    from app.agent.executors.standard import register_standard_operators
    register_standard_operators()
    
    operators = AgentOperatorRegistry.list_operators()
    return [op.model_dump() for op in operators]


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.get("", response_model=AgentListResponse)
async def list_agents(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """List all agents."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    agents, total = await service.list_agents(status=status, skip=skip, limit=limit)
    
    return AgentListResponse(
        agents=[agent_to_response(a) for a in agents],
        total=total
    )


@router.post("", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.create_agent(
            data=CreateAgentData(
                name=request.name,
                slug=request.slug,
                description=request.description,
                graph_definition=request.graph_definition.model_dump() if request.graph_definition else None,
                memory_config=request.memory_config,
                execution_constraints=request.execution_constraints,
            ),
            user_id=context["user"].id
        )
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Get an agent by ID."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.get_agent(agent_id)
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.put("/{agent_id}", response_model=AgentResponse)
@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    request: UpdateAgentRequest,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.update_agent(agent_id, UpdateAgentData(
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
    agent_id: UUID,
    request: GraphDefinitionSchema,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Update agent graph."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.update_graph(agent_id, request.model_dump())
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Delete or archive an agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        return await service.delete_agent(agent_id)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Validation & Publishing
# =============================================================================

@router.post("/{agent_id}/validate")
async def validate_agent(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Validate agent graph."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        result = await service.validate_agent(agent_id)
        return {"valid": result.valid, "errors": result.errors}
    except AgentServiceError as e:
        handle_service_error(e)


@router.post("/{agent_id}/publish", response_model=AgentResponse)
async def publish_agent(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Publish an agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.publish_agent(agent_id)
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Versioning
# =============================================================================

@router.get("/{agent_id}/versions")
async def list_versions(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """List agent versions."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        versions = await service.list_versions(agent_id)
        return {"versions": versions}
    except AgentServiceError as e:
        handle_service_error(e)


@router.get("/{agent_id}/versions/{version}")
async def get_version(
    agent_id: UUID, 
    version: int, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Get specific version."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        return await service.get_version(agent_id, version)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Execution
# =============================================================================

@router.post("/{agent_id}/execute", response_model=ExecuteAgentResponse)
async def execute_agent(
    agent_id: UUID,
    request: ExecuteAgentRequest,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Execute a published agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        result = await service.execute_agent(agent_id, ExecuteAgentData(
            input=request.input,
            messages=request.messages,
            context=request.context,
        ))
        # Convert LangChain messages to dicts for Pydantic validation
        serialized_messages = []
        for msg in result.messages:
            if isinstance(msg, dict):
                serialized_messages.append(msg)
            elif hasattr(msg, "model_dump"):
                serialized_messages.append(msg.model_dump())
            elif hasattr(msg, "dict"):
                serialized_messages.append(msg.dict())
            else:
                serialized_messages.append({"content": str(msg), "type": "unknown"})

        return ExecuteAgentResponse(
            run_id=result.run_id,
            output=result.output,
            steps=result.steps,
            messages=serialized_messages,
            usage=result.usage,
        )
    except AgentServiceError as e:
        handle_service_error(e)


@router.post("/{agent_id}/stream")
async def stream_agent(
    agent_id: UUID,
    request: ExecuteAgentRequest,
    mode: Optional[str] = None, # "debug" or "production"
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream agent execution (SSE).
    Supports 'debug' (Playground) and 'production' (End-User) modes.
    """
    from app.agent.execution.service import AgentExecutorService
    from app.agent.execution.types import ExecutionMode
    from app.agent.execution.adapter import StreamAdapter
    
    # 1. Determine Mode
    # Default to PRODUCTION for safety
    execution_mode = ExecutionMode.PRODUCTION
    
    # Allow override if internal user (authenticated via standard auth)
    # TODO: Check specifically for "service account" or "public key" vs "user session"
    # For now, get_agent_context implies internal user/admin. 
    # Real public users would use a different specific auth dependency (e.g. get_public_agent_context).
    # Assuming get_agent_context ensures an internal user/member:
    if mode and mode.lower() == "debug":
        execution_mode = ExecutionMode.DEBUG

    executor = AgentExecutorService(db=db)
    
    # 2. Identify or Create Run
    run_id = request.run_id
    resume_payload = None
    
    if run_id:
        # Resume existing run
        try:
            # For playground, user message is the resume payload
            resume_payload = {"input": request.input} if request.input else {}
            await executor.resume_run(run_id, resume_payload, background=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot resume run {run_id}: {e}")
    else:
        # Start new run
        current_messages = [msg.model_dump() if hasattr(msg, "model_dump") else msg for msg in request.messages]
        
        if request.input:
            current_messages.append({"role": "user", "content": request.input})
            
        input_params = {
            "messages": current_messages,
            "input": request.input
        }
        # Start run with explicit mode metadata
        run_id = await executor.start_run(agent_id, input_params, user_id=context["user"].id, background=False, mode=execution_mode)

    async def event_generator():
        import time
        # raw stream from engine (full firehose)
        raw_stream = executor.run_and_stream(run_id, db, resume_payload, mode=execution_mode)
        
        # filtered stream via adapter
        filtered_stream = StreamAdapter.filter_stream(raw_stream, execution_mode)
        
        # Initial Event: Run ID + Padding to force proxy flush (4KB of comments)
        yield ": " + (" " * 4096) + "\n\n"
        yield f"data: {json.dumps({'event': 'run_id', 'run_id': str(run_id)})}\n\n"
        
        try:
            async for event_dict in filtered_stream:
                # event_dict is already a dict from the adapter
                print(f"[DEBUG] {time.time()} Agents Router: Yielding SSE event: {event_dict.get('event')}")
                yield f"data: {json.dumps(event_dict)}\n\n"
            
            print(f"[DEBUG] {time.time()} Agents Router: Yielding DONE")
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"[STREAM] Error during stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Content-Encoding": "identity", # Disable compression
        }
    )
    
@router.post("/{agent_id}/run", response_model=Dict[str, Any])
async def start_run_v2(
    agent_id: UUID,
    request: ExecuteAgentRequest,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Start an agent execution using the new AgentExecutorService (Phase 4 engine).
    Returns the Run ID immediately.
    """
    print(f"[DEBUG] start_run_v2 called for agent_id: {agent_id}")
    print(f"[DEBUG] Request data: {request.model_dump()}")
    
    from app.agent.execution.service import AgentExecutorService
    
    tenant_id = context["tenant_id"]
    # Ensure user has access
    service = AgentService(db=db, tenant_id=tenant_id)
    try:
        agent = await service.get_agent(agent_id) # Validates existence and checks ownership implicitly
        print(f"[DEBUG] Agent found: {agent.name}")
    except Exception as e:
        print(f"[DEBUG] Error finding/checking agent: {e}")
        raise
    
    executor = AgentExecutorService(db=db)
    
    # Construct input params
    # Convert Pydantic messages to dicts
    current_messages = [msg.model_dump() if hasattr(msg, "model_dump") else msg for msg in request.messages]
    
    # Append input as user message if provided
    if request.input:
        current_messages.append({"role": "user", "content": request.input})
        
    input_params = {
        "messages": current_messages,
        "input": request.input
    }
    
    try:
        run_id = await executor.start_run(agent_id, input_params, user_id=context["user"].id)
        print(f"[DEBUG] Run started successfully. Run ID: {run_id}")
        return {"run_id": str(run_id)}
    except Exception as e:
        print(f"[DEBUG] Error starting run in executor: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/resume", response_model=Dict[str, Any])
async def resume_run_v2(
    run_id: UUID,
    request: Dict[str, Any], # Payload depends on what the node waits for
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Resume a paused agent run.
    """
    from app.agent.execution.service import AgentExecutorService
    
    executor = AgentExecutorService(db=db)
    # TODO: Verify run belongs to tenant/user
    
    await executor.resume_run(run_id, request)
    return {"status": "resumed"}


@router.get("/runs/{run_id}", response_model=Dict[str, Any])
async def get_run_status(
    run_id: UUID,
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status and result of a run.
    """
    from app.db.postgres.models.agents import AgentRun, AgentTrace
    
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalars().first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    # TODO: Check tenant
    
    return {
        "id": str(run.id),
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "result": run.output_result,
        "error": run.error_message,
        "checkpoint": run.checkpoint # Debugging
    }
