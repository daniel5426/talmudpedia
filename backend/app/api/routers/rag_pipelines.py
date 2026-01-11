from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel

from app.db.models.user import User
from app.db.models.tenant import Tenant
from app.db.models.rag import (
    VisualPipeline,
    PipelineNode,
    PipelineNodePosition,
    PipelineEdge,
    ExecutablePipeline,
    PipelineJob,
    PipelineJobStatus,
    OperatorCategory,
)
from app.db.models.rbac import Action, ResourceType, ActorType
from app.db.connection import MongoDatabase
from app.api.routers.auth import get_current_user
from app.core.rbac import check_permission
from app.core.audit import log_simple_action
from app.rag.pipeline import PipelineCompiler, OperatorRegistry


router = APIRouter()


async def get_pipeline_context(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    if not tenant_slug:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Tenant context required")
        return None, current_user

    db = MongoDatabase.get_db()
    tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
    if not tenant_doc:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant = Tenant(**tenant_doc)

    membership = await db.org_memberships.find_one({
        "tenant_id": tenant.id,
        "user_id": current_user.id,
    })

    if not membership and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    return tenant, current_user


async def require_pipeline_permission(
    tenant: Optional[Tenant],
    user: User,
    action: Action,
    pipeline_id: Optional[str] = None,
) -> bool:
    if user.role == "admin":
        return True

    if not tenant:
        return False

    db = MongoDatabase.get_db()
    resource_id = None
    resource_owner_id = None

    if pipeline_id:
        pipeline_doc = await db.visual_pipelines.find_one({
            "_id": ObjectId(pipeline_id),
            "tenant_id": tenant.id
        })
        if pipeline_doc:
            resource_id = pipeline_doc["_id"]
            resource_owner_id = pipeline_doc.get("org_unit_id")

    from app.db.models.rbac import Permission
    return await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.PIPELINE, action=action),
        resource_id=resource_id,
        resource_owner_id=resource_owner_id,
    )


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
    org_unit_id: Optional[str] = None


class UpdatePipelineRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[PipelineNodeRequest]] = None
    edges: Optional[List[PipelineEdgeRequest]] = None


class CreateJobRequest(BaseModel):
    executable_pipeline_id: str
    input_params: Dict[str, Any] = {}


@router.get("/catalog")
async def get_operator_catalog(
    current_user: User = Depends(get_current_user),
):
    registry = OperatorRegistry.get_instance()
    return registry.get_catalog()


@router.get("/operators/{operator_id}")
async def get_operator_spec(
    operator_id: str,
    current_user: User = Depends(get_current_user),
):
    registry = OperatorRegistry.get_instance()
    spec = registry.get(operator_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Operator not found")
    return spec.model_dump()


@router.get("/visual-pipelines")
async def list_visual_pipelines(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not await require_pipeline_permission(tenant, user, Action.READ):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    query = {}
    if tenant:
        query["tenant_id"] = tenant.id

    cursor = db.visual_pipelines.find(query).sort("updated_at", -1)
    pipelines = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        if doc.get("tenant_id"):
            doc["tenant_id"] = str(doc["tenant_id"])
        if doc.get("org_unit_id"):
            doc["org_unit_id"] = str(doc["org_unit_id"])
        pipelines.append(doc)

    return {"pipelines": pipelines}


@router.post("/visual-pipelines")
async def create_visual_pipeline(
    request: CreatePipelineRequest,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required to create pipeline")

    if not await require_pipeline_permission(tenant, user, Action.WRITE):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    nodes = [
        PipelineNode(
            id=n.id,
            category=OperatorCategory(n.category),
            operator=n.operator,
            position=PipelineNodePosition(**n.position),
            config=n.config,
        )
        for n in request.nodes
    ]

    edges = [
        PipelineEdge(
            id=e.id,
            source=e.source,
            target=e.target,
            source_handle=e.source_handle,
            target_handle=e.target_handle,
        )
        for e in request.edges
    ]

    org_unit_id = ObjectId(request.org_unit_id) if request.org_unit_id else None

    pipeline = VisualPipeline(
        tenant_id=tenant.id,
        org_unit_id=org_unit_id,
        name=request.name,
        description=request.description,
        nodes=nodes,
        edges=edges,
        version=1,
        is_published=False,
        created_by=str(user.id),
    )

    result = await db.visual_pipelines.insert_one(pipeline.model_dump(by_alias=True))

    await log_simple_action(
        tenant_id=tenant.id,
        org_unit_id=org_unit_id,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.PIPELINE,
        resource_id=str(result.inserted_id),
        resource_name=request.name,
        request=http_request,
    )

    return {"id": str(result.inserted_id), "status": "created"}


@router.get("/visual-pipelines/{pipeline_id}")
async def get_visual_pipeline(
    pipeline_id: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not await require_pipeline_permission(tenant, user, Action.READ, pipeline_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    query = {"_id": ObjectId(pipeline_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    doc = await db.visual_pipelines.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    doc["id"] = str(doc["_id"])
    del doc["_id"]
    if doc.get("tenant_id"):
        doc["tenant_id"] = str(doc["tenant_id"])
    if doc.get("org_unit_id"):
        doc["org_unit_id"] = str(doc["org_unit_id"])

    return doc


@router.put("/visual-pipelines/{pipeline_id}")
async def update_visual_pipeline(
    pipeline_id: str,
    request: UpdatePipelineRequest,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not await require_pipeline_permission(tenant, user, Action.WRITE, pipeline_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    query = {"_id": ObjectId(pipeline_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    existing = await db.visual_pipelines.find_one(query)
    if not existing:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if existing.get("is_published"):
        update_data["version"] = existing.get("version", 1) + 1
        update_data["is_published"] = False

    if request.name is not None:
        update_data["name"] = request.name
    if request.description is not None:
        update_data["description"] = request.description
    if request.nodes is not None:
        update_data["nodes"] = [
            PipelineNode(
                id=n.id,
                category=OperatorCategory(n.category),
                operator=n.operator,
                position=PipelineNodePosition(**n.position),
                config=n.config,
            ).model_dump()
            for n in request.nodes
        ]
    if request.edges is not None:
        update_data["edges"] = [
            PipelineEdge(
                id=e.id,
                source=e.source,
                target=e.target,
                source_handle=e.source_handle,
                target_handle=e.target_handle,
            ).model_dump()
            for e in request.edges
        ]

    await db.visual_pipelines.update_one(query, {"$set": update_data})

    await log_simple_action(
        tenant_id=tenant.id if tenant else None,
        org_unit_id=existing.get("org_unit_id"),
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.PIPELINE,
        resource_id=pipeline_id,
        resource_name=existing.get("name"),
        request=http_request,
    )

    return {"status": "updated", "version": update_data.get("version", existing.get("version", 1))}


@router.delete("/visual-pipelines/{pipeline_id}")
async def delete_visual_pipeline(
    pipeline_id: str,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not await require_pipeline_permission(tenant, user, Action.DELETE, pipeline_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    query = {"_id": ObjectId(pipeline_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    existing = await db.visual_pipelines.find_one(query)
    if not existing:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    await db.visual_pipelines.delete_one(query)

    await log_simple_action(
        tenant_id=tenant.id if tenant else None,
        org_unit_id=existing.get("org_unit_id"),
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.DELETE,
        resource_type=ResourceType.PIPELINE,
        resource_id=pipeline_id,
        resource_name=existing.get("name"),
        request=http_request,
    )

    return {"status": "deleted"}


@router.post("/visual-pipelines/{pipeline_id}/compile")
async def compile_pipeline(
    pipeline_id: str,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not await require_pipeline_permission(tenant, user, Action.WRITE, pipeline_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    query = {"_id": ObjectId(pipeline_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    doc = await db.visual_pipelines.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    visual_pipeline = VisualPipeline(**doc)

    compiler = PipelineCompiler()
    result = compiler.compile(visual_pipeline, compiled_by=str(user.id))

    if not result.success:
        return {
            "success": False,
            "errors": [e.model_dump() for e in result.errors],
            "warnings": [w.model_dump() for w in result.warnings],
        }

    exec_doc = result.executable_pipeline.model_dump(by_alias=True)
    insert_result = await db.executable_pipelines.insert_one(exec_doc)

    await db.visual_pipelines.update_one(
        {"_id": ObjectId(pipeline_id)},
        {"$set": {"is_published": True, "updated_at": datetime.utcnow()}}
    )

    await log_simple_action(
        tenant_id=tenant.id if tenant else None,
        org_unit_id=doc.get("org_unit_id"),
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.PIPELINE,
        resource_id=pipeline_id,
        resource_name=f"{doc.get('name')} (compiled v{visual_pipeline.version})",
        request=http_request,
    )

    return {
        "success": True,
        "executable_pipeline_id": str(insert_result.inserted_id),
        "version": visual_pipeline.version,
        "warnings": [w.model_dump() for w in result.warnings],
    }


@router.get("/visual-pipelines/{pipeline_id}/versions")
async def list_pipeline_versions(
    pipeline_id: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not await require_pipeline_permission(tenant, user, Action.READ, pipeline_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    db = MongoDatabase.get_db()

    query = {"visual_pipeline_id": ObjectId(pipeline_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    cursor = db.executable_pipelines.find(query).sort("version", -1)
    versions = []
    async for doc in cursor:
        versions.append({
            "id": str(doc["_id"]),
            "version": doc["version"],
            "is_valid": doc.get("is_valid", True),
            "compiled_by": doc.get("compiled_by"),
            "created_at": doc.get("created_at"),
        })

    return {"versions": versions}


@router.get("/executable-pipelines/{exec_id}")
async def get_executable_pipeline(
    exec_id: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)
    db = MongoDatabase.get_db()

    query = {"_id": ObjectId(exec_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    doc = await db.executable_pipelines.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Executable pipeline not found")

    doc["id"] = str(doc["_id"])
    del doc["_id"]
    doc["visual_pipeline_id"] = str(doc["visual_pipeline_id"])
    if doc.get("tenant_id"):
        doc["tenant_id"] = str(doc["tenant_id"])

    return doc


@router.post("/jobs")
async def create_pipeline_job(
    request: CreateJobRequest,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    db = MongoDatabase.get_db()

    exec_doc = await db.executable_pipelines.find_one({
        "_id": ObjectId(request.executable_pipeline_id),
        "tenant_id": tenant.id,
    })
    if not exec_doc:
        raise HTTPException(status_code=404, detail="Executable pipeline not found")

    job = PipelineJob(
        tenant_id=tenant.id,
        executable_pipeline_id=ObjectId(request.executable_pipeline_id),
        status=PipelineJobStatus.QUEUED,
        input_params=request.input_params,
        triggered_by=str(user.id),
    )

    result = await db.pipeline_jobs.insert_one(job.model_dump(by_alias=True))

    await log_simple_action(
        tenant_id=tenant.id,
        org_unit_id=None,
        actor_id=user.id,
        actor_type=ActorType.USER,
        actor_email=user.email,
        action=Action.WRITE,
        resource_type=ResourceType.JOB,
        resource_id=str(result.inserted_id),
        resource_name=f"Pipeline Job (exec: {request.executable_pipeline_id})",
        request=http_request,
    )

    return {
        "job_id": str(result.inserted_id),
        "status": "queued",
        "executable_pipeline_id": request.executable_pipeline_id,
    }


@router.get("/jobs")
async def list_pipeline_jobs(
    executable_pipeline_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    db = MongoDatabase.get_db()

    query: Dict[str, Any] = {}
    if tenant:
        query["tenant_id"] = tenant.id
    if executable_pipeline_id:
        query["executable_pipeline_id"] = ObjectId(executable_pipeline_id)
    if status:
        query["status"] = status

    cursor = db.pipeline_jobs.find(query).sort("created_at", -1).skip(skip).limit(limit)
    jobs = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["executable_pipeline_id"] = str(doc["executable_pipeline_id"])
        jobs.append(doc)

    total = await db.pipeline_jobs.count_documents(query)

    return {
        "jobs": jobs,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/jobs/{job_id}")
async def get_pipeline_job(
    job_id: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant, user = await get_pipeline_context(tenant_slug, current_user)

    db = MongoDatabase.get_db()

    query = {"_id": ObjectId(job_id)}
    if tenant:
        query["tenant_id"] = tenant.id

    doc = await db.pipeline_jobs.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")

    doc["id"] = str(doc["_id"])
    del doc["_id"]
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["executable_pipeline_id"] = str(doc["executable_pipeline_id"])

    return doc
