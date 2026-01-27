"""
RAG Pipelines Router - PostgreSQL implementation.

Manages visual pipelines, compilation, and pipeline job execution.
Now uses PostgreSQL instead of MongoDB.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_db
from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.identity import User, Tenant, OrgMembership
from app.db.postgres.models.rag import (
    VisualPipeline,
    ExecutablePipeline,
    PipelineJob,
    PipelineJobStatus,
    OperatorCategory,
    CustomOperator,
    PipelineStepExecution,
    PipelineStepStatus,
)
from app.rag.pipeline.registry import (
    OperatorRegistry,
    OperatorSpec,
    ConfigFieldSpec,
    ConfigFieldType,
    DataType,
)
from app.db.postgres.models.rbac import Action, ResourceType, ActorType
from app.api.routers.auth import get_current_user
from app.core.rbac import check_permission
from app.core.audit import log_simple_action
from app.rag.pipeline import PipelineCompiler, OperatorRegistry
from app.rag.pipeline.executor import PipelineExecutor
from fastapi import BackgroundTasks

router = APIRouter()


async def run_pipeline_job_background(job_id: UUID):
    """Execute pipeline job in background with its own DB session."""
    async with sessionmaker() as session:
        executor = PipelineExecutor(session)
        await executor.execute_job(job_id)



# =============================================================================
# Helpers
# =============================================================================

# =============================================================================
# Helpers
# =============================================================================

async def sync_custom_operators(db: AsyncSession, tenant_id: UUID):
    """Fetch custom operators from DB and register them in the registry."""
    query = select(CustomOperator).where(CustomOperator.tenant_id == tenant_id, CustomOperator.is_active == True)
    result = await db.execute(query)
    custom_ops = result.scalars().all()
    
    registry = OperatorRegistry.get_instance()
    specs = []
    for op in custom_ops:
        required_config = []
        optional_config = []
        
        if op.config_schema:
            for field in op.config_schema:
                try:
                    spec = ConfigFieldSpec(**field)
                    if spec.required:
                        required_config.append(spec)
                    else:
                        optional_config.append(spec)
                except Exception as e:
                    print(f"Error parsing config field for {op.name}: {e}")
                    continue

        try:
            op_spec = OperatorSpec(
                operator_id=op.name,
                display_name=op.display_name,
                category=op.category, 
                version=op.version,
                description=op.description,
                input_type=op.input_type,
                output_type=op.output_type,
                required_config=required_config,
                optional_config=optional_config,
                is_custom=True,
                python_code=op.python_code,
                author=str(op.created_by) if op.created_by else None,
            )
            specs.append(op_spec)
        except Exception as e:
             print(f"Error creating OperatorSpec for {op.name}: {e}")
        
    registry.load_custom_operators(specs, str(tenant_id))


async def get_pipeline_context(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get pipeline context with tenant and user info."""
    if not tenant_slug:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Tenant context required")
        return None, current_user, db

    # Find tenant by slug
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check membership
    membership_result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == current_user.id
        )
    )
    membership = membership_result.scalar_one_or_none()

    if not membership and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    return tenant, current_user, db


async def require_pipeline_permission(
    tenant: Optional[Tenant],
    user: User,
    action: Action,
    pipeline_id: Optional[UUID] = None,
    db: AsyncSession = None,
) -> bool:
    """Check if user has permission for pipeline operations."""
    if user.role == "admin":
        return True

    if not tenant:
        return False

    # For now, just check membership. Could extend with full RBAC check.
    return True


# =============================================================================
# Schemas
# =============================================================================

class PipelineNodeRequest(BaseModel):
    id: str
    category: str
    operator: str
    position: Dict[str, float]
    config: Dict[str, Any] = {}


class PipelineEdgeRequest(BaseModel):
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None


class CreatePipelineRequest(BaseModel):
    name: str
    description: Optional[str] = None
    nodes: List[PipelineNodeRequest] = []
    edges: List[PipelineEdgeRequest] = []
    org_unit_id: Optional[UUID] = None


class UpdatePipelineRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[PipelineNodeRequest]] = None
    edges: Optional[List[PipelineEdgeRequest]] = None


class CreateJobRequest(BaseModel):
    executable_pipeline_id: UUID
    input_params: Dict[str, Any] = {}


# =============================================================================
# Helper: Convert model to dict response
# =============================================================================

def pipeline_to_dict(p: VisualPipeline) -> Dict[str, Any]:
    """Convert VisualPipeline model to dict response."""
    return {
        "id": str(p.id),
        "tenant_id": str(p.tenant_id),
        "org_unit_id": str(p.org_unit_id) if p.org_unit_id else None,
        "name": p.name,
        "description": p.description,
        "nodes": p.nodes or [],
        "edges": p.edges or [],
        "version": p.version,
        "is_published": p.is_published,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "created_by": str(p.created_by) if p.created_by else None,
    }


def exec_pipeline_to_dict(p: ExecutablePipeline) -> Dict[str, Any]:
    """Convert ExecutablePipeline model to dict response."""
    return {
        "id": str(p.id),
        "visual_pipeline_id": str(p.visual_pipeline_id),
        "tenant_id": str(p.tenant_id),
        "version": p.version,
        "compiled_graph": p.compiled_graph or {},
        "is_valid": p.is_valid,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "compiled_by": str(p.compiled_by) if p.compiled_by else None,
    }


def job_to_dict(j: PipelineJob) -> Dict[str, Any]:
    """Convert PipelineJob model to dict response."""
    return {
        "id": str(j.id),
        "tenant_id": str(j.tenant_id),
        "executable_pipeline_id": str(j.executable_pipeline_id),
        "status": j.status.value if hasattr(j.status, 'value') else j.status,
        "input_params": j.input_params or {},
        "output": j.output,
        "error_message": j.error_message,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "triggered_by": str(j.triggered_by) if j.triggered_by else None,
    }


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/catalog")
async def get_operator_catalog(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get operator catalog."""
    registry = OperatorRegistry.get_instance()
    
    if tenant_slug:
        result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()
        if tenant:
             await sync_custom_operators(db, tenant.id)
             return registry.get_catalog(str(tenant.id))
            
    return registry.get_catalog()



@router.get("/operators/{operator_id}")
async def get_operator_spec(
    operator_id: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get operator specification."""
    registry = OperatorRegistry.get_instance()
    tenant_id = None
    
    if tenant_slug:
        result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()
        if tenant:
             await sync_custom_operators(db, tenant.id)
             tenant_id = str(tenant.id)
    
    spec = registry.get(operator_id, tenant_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Operator not found")
    return spec.model_dump()


@router.get("/operators")
async def list_operator_specs(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all operator specifications."""
    registry = OperatorRegistry.get_instance()
    tenant_id = None
    
    if tenant_slug:
        result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = result.scalar_one_or_none()
        if tenant:
             await sync_custom_operators(db, tenant.id)
             tenant_id = str(tenant.id)
    
    specs = registry.list_all(tenant_id)
    return {spec.operator_id: spec.model_dump() for spec in specs}


@router.get("/visual-pipelines")
async def list_visual_pipelines(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all visual pipelines."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.READ, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(VisualPipeline)
    if tenant:
        query = query.where(VisualPipeline.tenant_id == tenant.id)
    query = query.order_by(VisualPipeline.updated_at.desc())

    result = await db.execute(query)
    pipelines = result.scalars().all()

    return {"pipelines": [pipeline_to_dict(p) for p in pipelines]}


@router.post("/visual-pipelines")
async def create_visual_pipeline(
    request: CreatePipelineRequest,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required to create pipeline")

    if not await require_pipeline_permission(tenant, user, Action.WRITE, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Convert nodes and edges to JSONB
    nodes = [n.model_dump(mode='json') for n in request.nodes]
    edges = [e.model_dump(mode='json') for e in request.edges]

    org_unit_id = request.org_unit_id

    pipeline = VisualPipeline(
        tenant_id=tenant.id,
        org_unit_id=org_unit_id,
        name=request.name,
        description=request.description,
        nodes=nodes,
        edges=edges,
        version=1,
        is_published=False,
        created_by=user.id,
    )

    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)

    await log_simple_action(
        tenant_id=tenant.id,
        org_unit_id=org_unit_id,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.PIPELINE,
        resource_id=str(pipeline.id),
        resource_name=request.name,
        request=http_request,
    )

    return {"id": str(pipeline.id), "status": "created"}


@router.get("/visual-pipelines/{pipeline_id}")
async def get_visual_pipeline(
    pipeline_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a visual pipeline by ID."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.READ, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(VisualPipeline).where(VisualPipeline.id == pipeline_id)
    if tenant:
        query = query.where(VisualPipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    return pipeline_to_dict(pipeline)


@router.put("/visual-pipelines/{pipeline_id}")
async def update_visual_pipeline(
    pipeline_id: UUID,
    request: UpdatePipelineRequest,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.WRITE, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(VisualPipeline).where(VisualPipeline.id == pipeline_id)
    if tenant:
        query = query.where(VisualPipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # If pipeline was published, increment version and unpublish
    if pipeline.is_published:
        pipeline.version = pipeline.version + 1
        pipeline.is_published = False

    if request.name is not None:
        pipeline.name = request.name
    if request.description is not None:
        pipeline.description = request.description
    if request.nodes is not None:
        pipeline.nodes = [n.model_dump(mode='json') for n in request.nodes]
    if request.edges is not None:
        pipeline.edges = [e.model_dump(mode='json') for e in request.edges]

    pipeline.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(pipeline)

    await log_simple_action(
        tenant_id=tenant.id if tenant else None,
        org_unit_id=pipeline.org_unit_id,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.PIPELINE,
        resource_id=pipeline_id,
        resource_name=pipeline.name,
        request=http_request,
    )

    return {"status": "updated", "version": pipeline.version}


@router.delete("/visual-pipelines/{pipeline_id}")
async def delete_visual_pipeline(
    pipeline_id: UUID,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.DELETE, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(VisualPipeline).where(VisualPipeline.id == pipeline_id)
    if tenant:
        query = query.where(VisualPipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    pipeline_name = pipeline.name

    await db.delete(pipeline)
    await db.commit()

    await log_simple_action(
        tenant_id=tenant.id if tenant else None,
        org_unit_id=pipeline.org_unit_id if pipeline else None,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.DELETE,
        resource_type=ResourceType.PIPELINE,
        resource_id=pipeline_id,
        resource_name=pipeline_name,
        request=http_request,
    )

    return {"status": "deleted"}


@router.post("/visual-pipelines/{pipeline_id}/compile")
async def compile_pipeline(
    pipeline_id: UUID,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compile a visual pipeline to an executable pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.WRITE, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(VisualPipeline).where(VisualPipeline.id == pipeline_id)
    if tenant:
        query = query.where(VisualPipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Sync custom operators
    await sync_custom_operators(db, tenant.id)

    # Create a mock VisualPipeline object for the compiler
    # (The compiler expects the old MongoDB model format)
    class MockVisualPipeline:
        def __init__(self, p):
            self.id = p.id
            self.tenant_id = p.tenant_id
            self.org_unit_id = p.org_unit_id
            self.name = p.name
            self.description = p.description
            self.nodes = p.nodes or []
            self.edges = p.edges or []
            self.version = p.version
    
    mock_pipeline = MockVisualPipeline(pipeline)
    
    try:
        compiler = PipelineCompiler()
        compile_result = compiler.compile(mock_pipeline, compiled_by=str(user.id), tenant_id=str(tenant.id))
    except Exception as e:
        return {
            "success": False,
            "errors": [{"message": str(e)}],
            "warnings": [],
        }

    if not compile_result.success:
        return {
            "success": False,
            "errors": [e.model_dump() for e in compile_result.errors],
            "warnings": [w.model_dump() for w in compile_result.warnings],
        }

    # Create ExecutablePipeline
    exec_pipeline = ExecutablePipeline(
        visual_pipeline_id=pipeline.id,
        tenant_id=pipeline.tenant_id,
        version=pipeline.version,
        compiled_graph=compile_result.executable_pipeline.model_dump(mode='json') if hasattr(compile_result.executable_pipeline, 'model_dump') else {},
        is_valid=True,
        compiled_by=user.id,
    )

    db.add(exec_pipeline)

    # Mark visual pipeline as published
    pipeline.is_published = True
    pipeline.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(exec_pipeline)

    await log_simple_action(
        tenant_id=tenant.id if tenant else None,
        org_unit_id=pipeline.org_unit_id,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.PIPELINE,
        resource_id=pipeline_id,
        resource_name=f"{pipeline.name} (compiled v{pipeline.version})",
        request=http_request,
    )

    return {
        "success": True,
        "executable_pipeline_id": str(exec_pipeline.id),
        "version": pipeline.version,
        "warnings": [w.model_dump() for w in compile_result.warnings] if compile_result.warnings else [],
    }


@router.get("/visual-pipelines/{pipeline_id}/versions")
async def list_pipeline_versions(
    pipeline_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all compiled versions of a visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.READ, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(ExecutablePipeline).where(ExecutablePipeline.visual_pipeline_id == pipeline_id)
    if tenant:
        query = query.where(ExecutablePipeline.tenant_id == tenant.id)
    query = query.order_by(ExecutablePipeline.version.desc())

    result = await db.execute(query)
    versions = result.scalars().all()

    return {
        "versions": [
            {
                "id": str(v.id),
                "version": v.version,
                "is_valid": v.is_valid,
                "compiled_by": str(v.compiled_by) if v.compiled_by else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]
    }


@router.get("/executable-pipelines/{exec_id}")
async def get_executable_pipeline(
    exec_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an executable pipeline by ID."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    query = select(ExecutablePipeline).where(ExecutablePipeline.id == exec_id)
    if tenant:
        query = query.where(ExecutablePipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    exec_pipeline = result.scalar_one_or_none()

    if not exec_pipeline:
        raise HTTPException(status_code=404, detail="Executable pipeline not found")

    return exec_pipeline_to_dict(exec_pipeline)


@router.post("/jobs")
async def create_pipeline_job(
    request: CreateJobRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new pipeline job."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    exec_id = request.executable_pipeline_id

    # Verify executable pipeline exists
    exec_query = select(ExecutablePipeline).where(
        ExecutablePipeline.id == exec_id,
        ExecutablePipeline.tenant_id == tenant.id
    )
    exec_result = await db.execute(exec_query)
    exec_pipeline = exec_result.scalar_one_or_none()

    if not exec_pipeline:
        raise HTTPException(status_code=404, detail="Executable pipeline not found")

    job = PipelineJob(
        tenant_id=tenant.id,
        executable_pipeline_id=exec_id,
        status=PipelineJobStatus.QUEUED,
        input_params=request.input_params,
        triggered_by=user.id,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    await log_simple_action(
        tenant_id=tenant.id,
        org_unit_id=None,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.JOB,
        resource_id=str(job.id),
        resource_name=f"Pipeline Job (exec: {request.executable_pipeline_id})",
        request=http_request,
    )

    # Trigger background execution
    background_tasks.add_task(run_pipeline_job_background, job.id)

    return {
        "job_id": str(job.id),
        "status": "queued",
        "executable_pipeline_id": request.executable_pipeline_id,
    }


@router.get("/jobs")
async def list_pipeline_jobs(
    executable_pipeline_id: Optional[UUID] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pipeline jobs."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    query = select(PipelineJob)
    
    if tenant:
        query = query.where(PipelineJob.tenant_id == tenant.id)
    
    if executable_pipeline_id:
        query = query.where(PipelineJob.executable_pipeline_id == executable_pipeline_id)
    
    if status:
        try:
            status_enum = PipelineJobStatus(status)
            query = query.where(PipelineJob.status == status_enum)
        except ValueError:
            pass

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.order_by(PipelineJob.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "jobs": [job_to_dict(j) for j in jobs],
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit if total else 0,
    }


@router.get("/jobs/{job_id}")
async def get_pipeline_job(
    job_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a pipeline job by ID."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    query = select(PipelineJob).where(PipelineJob.id == job_id)
    if tenant:
        query = query.where(PipelineJob.tenant_id == tenant.id)

    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job_to_dict(job)


def step_to_dict(s: PipelineStepExecution, lite: bool = False) -> Dict[str, Any]:
    """Convert PipelineStepExecution model to dict response."""
    data = {
        "id": str(s.id),
        "job_id": str(s.job_id),
        "step_id": s.step_id,
        "operator_id": s.operator_id,
        "status": s.status,
        "metadata": s.metadata_,
        "error_message": s.error_message,
        "execution_order": s.execution_order,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }
    
    if not lite:
        data["input_data"] = s.input_data
        data["output_data"] = s.output_data
        
    return data


@router.get("/jobs/{job_id}/steps")
async def list_job_steps(
    job_id: UUID,
    lite: bool = True,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List execution steps for a job."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)
    
    # Check permissions (same as job read)
    job = await db.get(PipelineJob, job_id)
    if not job:
         raise HTTPException(status_code=404, detail="Job not found")
         
    if tenant and job.tenant_id != tenant.id:
         raise HTTPException(status_code=404, detail="Job not found")

    # Fetch steps
    query = select(PipelineStepExecution).where(PipelineStepExecution.job_id == job_id).order_by(PipelineStepExecution.execution_order)
    result = await db.execute(query)
    steps = result.scalars().all()
    
    return {"steps": [step_to_dict(s, lite=lite) for s in steps]}


@router.get("/jobs/{job_id}/steps/{step_id}/data")
async def get_step_data(
    job_id: UUID,
    step_id: str,
    type: str, # input | output
    page: int = 1,
    limit: int = 20,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated input or output data for a specific step."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)
    
    # Find the step execution
    query = select(PipelineStepExecution).where(
        PipelineStepExecution.job_id == job_id,
        PipelineStepExecution.step_id == step_id
    )
    result = await db.execute(query)
    step = result.scalar_one_or_none()
    
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
        
    if tenant and step.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Step not found")
        
    if type == "input":
        data = step.input_data
    elif type == "output":
         data = step.output_data
    else:
        raise HTTPException(status_code=400, detail="Invalid data type. Must be 'input' or 'output'")
        
    # Handle data types
    if data is None:
        return {"data": None, "total": 0, "page": 1, "pages": 0}
        
    # If it's a list, we paginate it
    if isinstance(data, list):
        total = len(data)
        start = (page - 1) * limit
        end = start + limit
        sliced_data = data[start:end]
        pages = (total + limit - 1) // limit if total > 0 else 0
        
        return {
            "data": sliced_data,
            "total": total,
            "page": page,
            "pages": pages,
            "is_list": True
        }
    else:
        # If it's not a list (e.g. dict or primitive), we just return it whole
        # We consider it as a single "page"
        return {
            "data": data,
            "total": 1,
            "page": 1,
            "pages": 1,
            "is_list": False
        }
