"""
RAG Pipelines Router - PostgreSQL implementation.

Manages visual pipelines, compilation, and pipeline job execution.
Now uses PostgreSQL instead of MongoDB.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from typing import List, Optional, Dict, Any, Tuple
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
    PipelineStepExecution,
    PipelineStepStatus,
    PipelineType,
)
from app.db.postgres.models.operators import CustomOperator, OperatorCategory
from app.rag.pipeline.registry import (
    OperatorRegistry,
    OperatorSpec,
    ConfigFieldSpec,
    ConfigFieldType,
    DataType,
)
from app.db.postgres.models.rbac import Action, ResourceType, ActorType
from app.api.routers.auth import get_current_user
from app.api.dependencies import get_current_principal, require_scopes, ensure_sensitive_action_approved
from app.core.rbac import check_permission
from app.core.audit import log_simple_action
from app.rag.pipeline import PipelineCompiler, OperatorRegistry
from app.rag.pipeline.executor import PipelineExecutor
from app.rag.pipeline.input_storage import PipelineInputStorage
from fastapi import BackgroundTasks

router = APIRouter()



async def run_pipeline_job_background(job_id: UUID):
    """Execute pipeline job in background with its own DB session."""
    async with sessionmaker() as session:
        executor = PipelineExecutor(session)
        await executor.execute_job(job_id)


# =============================================================================
# Large Data Support Helpers
# =============================================================================

def resolve_json_path(data: Any, path: str) -> Any:
    """Simple JSON path resolver (e.g. 'results[0].text')."""
    import re
    parts = re.split(r'\.|\[|\]', path)
    parts = [p for p in parts if p]
    
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
    return current


def truncate_large_strings(data: Any, limit: int = 50000, path: str = "") -> Tuple[Any, Dict[str, Any]]:
    """Recursively truncate strings longer than limit and record their paths."""
    truncated_fields = {}
    
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            new_v, sub_truncated = truncate_large_strings(v, limit, f"{path}.{k}" if path else k)
            new_dict[k] = new_v
            truncated_fields.update(sub_truncated)
        return new_dict, truncated_fields
    
    elif isinstance(data, list):
        new_list = []
        for i, v in enumerate(data):
            new_v, sub_truncated = truncate_large_strings(v, limit, f"{path}[{i}]")
            new_list.append(new_v)
            truncated_fields.update(sub_truncated)
        return new_list, truncated_fields
    
    elif isinstance(data, str) and len(data) > limit:
        truncated_fields[path] = {
            "full_size": len(data),
            "current_size": limit,
            "path": path,
            "is_truncated": True
        }
        return data[:limit] + "... [TRUNCATED]", truncated_fields
    
    return data, truncated_fields


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
    current_user: Optional[User] = None,
    db: AsyncSession = Depends(get_db),
    context: Optional[Dict[str, Any]] = None,
):
    """Get pipeline context with tenant and user info."""
    if context and context.get("type") == "workload":
        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        try:
            tenant_uuid = UUID(str(tenant_id))
        except Exception:
            tenant_uuid = None
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant, None, db

    if not tenant_slug:
        if current_user is None or current_user.role != "admin":
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
    user: Optional[User],
    action: Action,
    pipeline_id: Optional[UUID] = None,
    db: AsyncSession = None,
) -> bool:
    """Check if user has permission for pipeline operations."""
    if user is None:
        return True
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
    pipeline_type: PipelineType = PipelineType.INGESTION
    nodes: List[PipelineNodeRequest] = []
    edges: List[PipelineEdgeRequest] = []
    org_unit_id: Optional[UUID] = None


class UpdatePipelineRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pipeline_type: Optional[PipelineType] = None
    nodes: Optional[List[PipelineNodeRequest]] = None
    edges: Optional[List[PipelineEdgeRequest]] = None


class CreateJobRequest(BaseModel):
    executable_pipeline_id: UUID
    input_params: Dict[str, Any] = {}


class InputSchemaField(BaseModel):
    name: str
    field_type: str
    required: bool
    runtime: bool = True
    default: Optional[Any] = None
    description: Optional[str] = None
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    required_capability: Optional[str] = None
    operator_id: str
    operator_display_name: Optional[str] = None
    step_id: str
    json_schema: Optional[Dict[str, Any]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class InputSchemaStep(BaseModel):
    step_id: str
    operator_id: str
    operator_display_name: Optional[str] = None
    category: Optional[str] = None
    config: Dict[str, Any] = {}
    fields: List[InputSchemaField] = []


class ExecutablePipelineInputSchema(BaseModel):
    steps: List[InputSchemaStep] = []


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
        "pipeline_type": p.pipeline_type.value if hasattr(p.pipeline_type, "value") else p.pipeline_type,
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
        "pipeline_type": p.pipeline_type.value if hasattr(p.pipeline_type, "value") else p.pipeline_type,
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
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.catalog.read")),
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
    if context.get("type") == "workload" and context.get("tenant_id"):
        tenant_id = context.get("tenant_id")
        try:
            tenant_uuid = UUID(str(tenant_id))
        except Exception:
            tenant_uuid = None
        if tenant_uuid:
            await sync_custom_operators(db, tenant_uuid)
            return registry.get_catalog(str(tenant_uuid))
        return registry.get_catalog(str(tenant_id))

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
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user=context.get("user"), db=db, context=context)

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
        pipeline_type=request.pipeline_type,
        created_by=user.id if user else None,
    )

    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)

    if user:
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
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Update a visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user=context.get("user"), db=db, context=context)

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
    if request.pipeline_type is not None:
        pipeline.pipeline_type = request.pipeline_type

    pipeline.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(pipeline)

    if user:
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
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a visual pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user=context.get("user"), db=db, context=context)

    if not await require_pipeline_permission(tenant, user, Action.DELETE, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(VisualPipeline).where(VisualPipeline.id == pipeline_id)
    if tenant:
        query = query.where(VisualPipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    await ensure_sensitive_action_approved(
        principal=context,
        tenant_id=tenant.id if tenant else context.get("tenant_id"),
        subject_type="pipeline",
        subject_id=str(pipeline.id),
        action_scope="pipelines.delete",
        db=db,
    )

    pipeline_name = pipeline.name

    await db.delete(pipeline)
    await db.commit()

    if user:
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
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Compile a visual pipeline to an executable pipeline."""
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user=context.get("user"), db=db, context=context)

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
            self.pipeline_type = p.pipeline_type
    
    mock_pipeline = MockVisualPipeline(pipeline)
    
    try:
        compiler = PipelineCompiler()
        compiled_by = str(user.id) if user else str(context.get("initiator_user_id") or context.get("principal_id") or "")
        compile_result = compiler.compile(mock_pipeline, compiled_by=compiled_by, tenant_id=str(tenant.id))
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
        pipeline_type=pipeline.pipeline_type,
        compiled_by=user.id if user else None,
    )

    db.add(exec_pipeline)

    # Mark visual pipeline as published
    pipeline.is_published = True
    pipeline.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(exec_pipeline)

    if user:
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


class PipelineInputSchemaBuilder:
    def __init__(
        self,
        dag: List[Dict[str, Any]],
        registry: OperatorRegistry,
        tenant_id: Optional[str],
    ):
        self._dag = dag
        self._registry = registry
        self._tenant_id = tenant_id

    def build(self) -> ExecutablePipelineInputSchema:
        steps: List[InputSchemaStep] = []

        for step in self._dag:
            depends_on = step.get("depends_on") or []
            if depends_on:
                continue

            operator_id = step.get("operator")
            if not operator_id:
                continue

            spec = self._registry.get(operator_id, self._tenant_id)
            if not spec:
                continue

            step_id = step.get("step_id") or operator_id
            config = step.get("config") or {}
            fields = self._build_fields(spec, config, step_id)
            steps.append(InputSchemaStep(
                step_id=step_id,
                operator_id=operator_id,
                operator_display_name=spec.display_name,
                category=spec.category.value if spec.category else None,
                config=config,
                fields=fields,
            ))

        return ExecutablePipelineInputSchema(steps=steps)

    def _build_fields(
        self,
        spec: OperatorSpec,
        config: Dict[str, Any],
        step_id: str,
    ) -> List[InputSchemaField]:
        fields: List[InputSchemaField] = []
        required_names = spec.get_required_field_names()
        for field in spec.required_config + spec.optional_config:
            if field.name in config:
                continue
            if not field.runtime:
                continue
            fields.append(InputSchemaField(
                name=field.name,
                field_type=field.field_type.value,
                required=field.required or field.name in required_names,
                runtime=field.runtime,
                default=field.default,
                description=field.description,
                options=field.options,
                placeholder=field.placeholder,
                required_capability=field.required_capability,
                operator_id=spec.operator_id,
                operator_display_name=spec.display_name,
                step_id=step_id,
                json_schema=field.json_schema,
                min_value=field.min_value,
                max_value=field.max_value,
            ))
        return fields


class PipelineInputValidator:
    def __init__(
        self,
        dag: List[Dict[str, Any]],
        registry: OperatorRegistry,
        tenant_id: Optional[str],
        storage: PipelineInputStorage,
    ):
        self._builder = PipelineInputSchemaBuilder(dag, registry, tenant_id)
        self._storage = storage

    def validate(self, input_params: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
        schema = self._builder.build()
        step_ids = [step.step_id for step in schema.steps]
        normalized, errors = self._normalize_input_params(input_params, step_ids)
        if errors:
            return {}, errors

        for step in schema.steps:
            step_params = normalized.get(step.step_id, {})
            allowed_fields = {field.name: field for field in step.fields}

            for key in step_params.keys():
                if key not in allowed_fields:
                    errors.append({
                        "step_id": step.step_id,
                        "field": key,
                        "message": "Unexpected runtime field",
                    })

            for field in step.fields:
                value_provided = field.name in step_params
                if field.required and not value_provided and field.default is None:
                    errors.append({
                        "step_id": step.step_id,
                        "field": field.name,
                        "message": "Missing required field",
                    })
                    continue
                if value_provided:
                    value = step_params.get(field.name)
                    if value is None and field.required and field.default is None:
                        errors.append({
                            "step_id": step.step_id,
                            "field": field.name,
                            "message": "Missing required field",
                        })
                        continue
                    errors.extend(self._validate_field_value(step.step_id, field, value))

        return normalized, errors

    def _normalize_input_params(
        self,
        input_params: Dict[str, Any],
        step_ids: List[str],
    ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
        if input_params is None:
            return {step_id: {} for step_id in step_ids}, []
        if not isinstance(input_params, dict):
            return {}, [{
                "step_id": "__root__",
                "field": "__root__",
                "message": "input_params must be an object",
            }]

        if len(step_ids) == 1 and step_ids[0] not in input_params:
            step_params = input_params if isinstance(input_params, dict) else {}
            return {step_ids[0]: step_params}, []

        normalized: Dict[str, Dict[str, Any]] = {}
        errors: List[Dict[str, str]] = []
        for step_id in step_ids:
            value = input_params.get(step_id, {})
            if value is None:
                normalized[step_id] = {}
                continue
            if not isinstance(value, dict):
                errors.append({
                    "step_id": step_id,
                    "field": "__root__",
                    "message": "Step input must be an object",
                })
                continue
            normalized[step_id] = value

        extra_keys = [key for key in input_params.keys() if key not in step_ids]
        if extra_keys:
            for key in extra_keys:
                errors.append({
                    "step_id": "__root__",
                    "field": key,
                    "message": "Unknown step id",
                })

        return normalized, errors

    def _validate_field_value(
        self,
        step_id: str,
        field: InputSchemaField,
        value: Any,
    ) -> List[Dict[str, str]]:
        errors: List[Dict[str, str]] = []
        field_type = field.field_type

        if field_type == ConfigFieldType.STRING.value:
            if not isinstance(value, str):
                errors.append(self._error(step_id, field.name, "Must be a string"))
        elif field_type == ConfigFieldType.SECRET.value:
            if not isinstance(value, str) or not value.startswith("$secret:"):
                errors.append(self._error(step_id, field.name, "Must be a secret reference"))
        elif field_type == ConfigFieldType.SELECT.value:
            if not isinstance(value, str):
                errors.append(self._error(step_id, field.name, "Must be a string"))
            elif field.options and value not in field.options:
                errors.append(self._error(step_id, field.name, f"Must be one of: {field.options}"))
        elif field_type == ConfigFieldType.INTEGER.value:
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(self._error(step_id, field.name, "Must be an integer"))
            else:
                errors.extend(self._validate_numeric_bounds(step_id, field, float(value)))
        elif field_type == ConfigFieldType.FLOAT.value:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(self._error(step_id, field.name, "Must be a number"))
            else:
                errors.extend(self._validate_numeric_bounds(step_id, field, float(value)))
        elif field_type == ConfigFieldType.BOOLEAN.value:
            if not isinstance(value, bool):
                errors.append(self._error(step_id, field.name, "Must be a boolean"))
        elif field_type == ConfigFieldType.JSON.value:
            if value == "" or value is None:
                if field.required:
                    errors.append(self._error(step_id, field.name, "Missing required JSON field"))
                return errors
            
            if isinstance(value, str):
                try:
                    import json
                    json.loads(value)
                except Exception:
                    errors.append(self._error(step_id, field.name, "Invalid JSON format"))
            elif not isinstance(value, (dict, list)):
                errors.append(self._error(step_id, field.name, "Must be an object or list"))
        elif field_type in {
            ConfigFieldType.MODEL_SELECT.value,
            ConfigFieldType.CODE.value,
            ConfigFieldType.FILE_PATH.value,
        }:
            if not isinstance(value, str):
                errors.append(self._error(step_id, field.name, "Must be a string"))
            elif field_type == ConfigFieldType.FILE_PATH.value:
                if self._storage.is_managed_path(value) and not self._storage.path_exists(value):
                    errors.append(self._error(step_id, field.name, "Uploaded file not found"))

        return errors

    def _validate_numeric_bounds(
        self,
        step_id: str,
        field: InputSchemaField,
        value: float,
    ) -> List[Dict[str, str]]:
        errors: List[Dict[str, str]] = []
        if field.min_value is not None and value < field.min_value:
            errors.append(self._error(step_id, field.name, f"Must be >= {field.min_value}"))
        if field.max_value is not None and value > field.max_value:
            errors.append(self._error(step_id, field.name, f"Must be <= {field.max_value}"))
        return errors

    def _error(self, step_id: str, field_name: str, message: str) -> Dict[str, str]:
        return {"step_id": step_id, "field": field_name, "message": message}


@router.get("/executable-pipelines/{exec_id}/input-schema")
async def get_executable_pipeline_input_schema(
    exec_id: UUID,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not await require_pipeline_permission(tenant, user, Action.READ, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(ExecutablePipeline).where(ExecutablePipeline.id == exec_id)
    if tenant:
        query = query.where(ExecutablePipeline.tenant_id == tenant.id)

    result = await db.execute(query)
    exec_pipeline = result.scalar_one_or_none()
    if not exec_pipeline:
        raise HTTPException(status_code=404, detail="Executable pipeline not found")

    if tenant:
        await sync_custom_operators(db, tenant.id)

    compiled_graph = exec_pipeline.compiled_graph or {}
    dag = compiled_graph.get("dag") or []
    registry = OperatorRegistry.get_instance()
    tenant_id = str(tenant.id) if tenant else None
    return PipelineInputSchemaBuilder(dag, registry, tenant_id).build().model_dump()


@router.post("/pipeline-inputs/upload")
async def upload_pipeline_input_file(
    file: UploadFile = File(...),
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, user, db = await get_pipeline_context(tenant_slug, current_user, db)

    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    if not await require_pipeline_permission(tenant, user, Action.WRITE, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")

    storage = PipelineInputStorage()
    storage.cleanup_expired(24 * 60 * 60)
    metadata = await storage.save_upload(tenant.id, file)
    return {"path": metadata["path"], "filename": metadata["filename"], "upload_id": metadata["upload_id"]}


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

    await sync_custom_operators(db, tenant.id)

    compiled_graph = exec_pipeline.compiled_graph or {}
    dag = compiled_graph.get("dag") or []
    registry = OperatorRegistry.get_instance()
    validator = PipelineInputValidator(dag, registry, str(tenant.id), PipelineInputStorage())
    normalized_params, validation_errors = validator.validate(request.input_params)
    if validation_errors:
        raise HTTPException(status_code=422, detail={"errors": validation_errors})

    job = PipelineJob(
        tenant_id=tenant.id,
        executable_pipeline_id=exec_id,
        status=PipelineJobStatus.QUEUED,
        input_params=normalized_params,
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
    visual_pipeline_id: Optional[UUID] = None,
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
    
    if visual_pipeline_id:
        query = query.join(ExecutablePipeline).where(ExecutablePipeline.visual_pipeline_id == visual_pipeline_id)
    
    if status:
        try:
            status_enum = PipelineJobStatus(status.upper())
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
        
    # Limit for individual string fields (50KB)
    STRING_LIMIT = 50000
    
    # If it's a list, we paginate it
    if isinstance(data, list):
        total = len(data)
        start = (page - 1) * limit
        end = start + limit
        sliced_data = data[start:end]
        pages = (total + limit - 1) // limit if total > 0 else 0
        
        # Further truncate large strings within the page
        truncated_data, truncated_fields = truncate_large_strings(sliced_data, limit=STRING_LIMIT)
        
        return {
            "data": truncated_data,
            "truncated_fields": truncated_fields,
            "total": total,
            "page": page,
            "pages": pages,
            "is_list": True
        }
    else:
        # If it's not a list (e.g. dict or primitive), we just return it whole
        # We consider it as a single "page"
        truncated_data, truncated_fields = truncate_large_strings(data, limit=STRING_LIMIT)
        
        return {
            "data": truncated_data,
            "truncated_fields": truncated_fields,
            "total": 1,
            "page": 1,
            "pages": 1,
            "is_list": False
        }


@router.get("/jobs/{job_id}/steps/{step_id}/field")
async def get_step_field_content(
    job_id: UUID,
    step_id: str,
    type: str, # input | output
    path: str,
    offset: int = 0,
    limit: int = 100000,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a slice of a large string field within the step data."""
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

    # Resolve path
    field_value = resolve_json_path(data, path)
    
    if field_value is None:
        raise HTTPException(status_code=404, detail=f"Field at path '{path}' not found")
        
    if not isinstance(field_value, str):
         # If it's not a string, return it as JSON but it's not really the intended use of this endpoint
         return {"data": field_value, "is_string": False}
         
    # Slice the string
    total_size = len(field_value)
    end = offset + limit
    sliced_content = field_value[offset:end]
    
    return {
        "content": sliced_content,
        "offset": offset,
        "limit": limit,
        "total_size": total_size,
        "has_more": end < total_size,
        "is_string": True
    }
