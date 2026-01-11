from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel

from app.db.models.user import User
from app.db.models.tenant import Tenant
from app.db.models.rag import (
    RAGIndex,
    RAGIngestionJob,
    RAGIngestionJobStatus,
    RAGPipelineConfig,
)
from app.db.models.rbac import Permission, Action, ResourceType, ActorType
from app.db.connection import MongoDatabase
from app.api.routers.auth import get_current_user
from app.core.rbac import get_tenant_context, check_permission
from app.core.audit import log_simple_action, audit_action
from app.rag.factory import (
    RAGFactory,
    RAGConfig,
    EmbeddingConfig,
    VectorStoreConfig,
    ChunkerConfig,
    LoaderConfig,
    EmbeddingProviderType,
    VectorStoreType,
    ChunkerType,
    LoaderType,
)
from app.rag.pipeline.orchestrator import RAGOrchestrator
from app.rag.pipeline.job import IngestionJobConfig


router = APIRouter()


async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


async def get_rag_context(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
) -> Tuple[Optional[Tenant], User]:
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


async def require_index_permission(
    tenant: Optional[Tenant],
    user: User,
    action: Action,
    index_name: Optional[str] = None,
) -> bool:
    if user.role == "admin":
        return True
    
    if not tenant:
        return False
    
    db = MongoDatabase.get_db()
    resource_id = None
    resource_owner_id = None
    
    if index_name:
        index_doc = await db.rag_indices.find_one({"name": index_name, "tenant_id": tenant.id})
        if index_doc:
            resource_id = index_doc["_id"]
            resource_owner_id = index_doc.get("owner_id")
    
    return await check_permission(
        user_id=user.id,
        tenant_id=tenant.id,
        required_permission=Permission(resource_type=ResourceType.INDEX, action=action),
        resource_id=resource_id,
        resource_owner_id=resource_owner_id,
    )


class CreateIndexRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    dimension: int = 768
    namespace: Optional[str] = None
    metadata: Dict[str, Any] = {}
    owner_id: Optional[str] = None


class ChunkPreviewRequest(BaseModel):
    text: str
    chunk_size: int = 650
    chunk_overlap: int = 50


class IngestionRequest(BaseModel):
    index_name: str
    documents: List[Dict[str, Any]]
    namespace: Optional[str] = None
    embedding_provider: str = "gemini"
    vector_store_provider: str = "pinecone"
    chunker_strategy: str = "token_based"
    chunk_size: int = 650
    chunk_overlap: int = 50
    use_celery: bool = True


class LoaderIngestionRequest(BaseModel):
    index_name: str
    loader_type: str = "local"
    source_path: str
    namespace: Optional[str] = None
    embedding_provider: str = "gemini"
    vector_store_provider: str = "pinecone"
    chunker_strategy: str = "token_based"
    chunk_size: int = 650
    chunk_overlap: int = 50
    loader_config: Dict[str, Any] = {}


class PipelineConfigRequest(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_provider: str = "gemini"
    vector_store_provider: str = "pinecone"
    chunker_strategy: str = "token_based"
    chunk_size: int = 650
    chunk_overlap: int = 50
    is_default: bool = False


@router.get("/stats")
async def get_rag_stats(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    db = MongoDatabase.get_db()
    
    tenant = None
    query = {}
    if tenant_slug:
        tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
        if tenant_doc:
            tenant = Tenant(**tenant_doc)
            query["tenant_id"] = tenant.id
    
    if not await require_index_permission(tenant, current_user, Action.READ):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    total_indices = await db.rag_indices.count_documents(query)
    total_jobs = await db.rag_jobs.count_documents(query)
    completed_jobs = await db.rag_jobs.count_documents({**query, "status": RAGIngestionJobStatus.COMPLETED})
    failed_jobs = await db.rag_jobs.count_documents({**query, "status": RAGIngestionJobStatus.FAILED})
    running_jobs = await db.rag_jobs.count_documents({**query, "status": RAGIngestionJobStatus.RUNNING})
    
    match_stage = {"$match": query} if query else {"$match": {}}
    total_chunks_pipeline = [
        match_stage,
        {"$group": {"_id": None, "total": {"$sum": "$chunk_count"}}}
    ]
    chunks_result = await db.rag_indices.aggregate(total_chunks_pipeline).to_list(1)
    total_chunks = chunks_result[0]["total"] if chunks_result else 0
    
    total_pipelines = await db.visual_pipelines.count_documents(query)
    compiled_pipelines = await db.executable_pipelines.count_documents(query)
    active_pipeline_jobs = await db.pipeline_jobs.count_documents({**query, "status": "running"})
    
    vector_store = RAGFactory.create_vector_store(VectorStoreConfig())
    live_indices = await vector_store.list_indices()
    
    return {
        "total_indices": total_indices,
        "live_indices": len(live_indices),
        "total_chunks": total_chunks,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "running_jobs": running_jobs,
        "total_pipelines": total_pipelines,
        "compiled_pipelines": compiled_pipelines,
        "active_pipeline_jobs": active_pipeline_jobs,
        "available_providers": RAGFactory.get_available_providers()
    }


@router.get("/indices")
async def list_indices(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    db = MongoDatabase.get_db()
    
    tenant = None
    if tenant_slug:
        tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
        if tenant_doc:
            tenant = Tenant(**tenant_doc)
    
    if not await require_index_permission(tenant, current_user, Action.READ):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    vector_store = RAGFactory.create_vector_store(VectorStoreConfig())
    live_indices = await vector_store.list_indices()
    
    indices = []
    for idx_name in live_indices:
        query = {"name": idx_name}
        if tenant:
            query["tenant_id"] = tenant.id
        
        db_record = await db.rag_indices.find_one(query)
        
        if tenant and not db_record:
            continue
        
        stats = await vector_store.get_index_stats(idx_name)
        
        indices.append({
            "name": idx_name,
            "display_name": db_record.get("display_name") if db_record else idx_name,
            "dimension": stats.dimension if stats else 0,
            "total_vectors": stats.total_vector_count if stats else 0,
            "namespaces": stats.namespaces if stats else {},
            "status": "active",
            "synced": db_record is not None,
            "tenant_id": str(db_record.get("tenant_id")) if db_record and db_record.get("tenant_id") else None,
            "owner_id": str(db_record.get("owner_id")) if db_record and db_record.get("owner_id") else None,
        })
    
    return {"indices": indices}


@router.post("/indices")
async def create_index(
    request: CreateIndexRequest,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    db = MongoDatabase.get_db()
    
    tenant = None
    if tenant_slug:
        tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
        if tenant_doc:
            tenant = Tenant(**tenant_doc)
    
    if not await require_index_permission(tenant, current_user, Action.WRITE):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {"name": request.name}
    if tenant:
        query["tenant_id"] = tenant.id
    
    existing = await db.rag_indices.find_one(query)
    if existing:
        raise HTTPException(status_code=400, detail="Index already exists")
    
    embedding = RAGFactory.create_embedding_provider(EmbeddingConfig())
    vector_store = RAGFactory.create_vector_store(VectorStoreConfig())
    
    dimension = request.dimension or embedding.dimension
    success = await vector_store.create_index(request.name, dimension)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create index")
    
    owner_id = ObjectId(request.owner_id) if request.owner_id else (tenant.id if tenant else None)
    
    index_doc = RAGIndex(
        tenant_id=tenant.id if tenant else None,
        owner_id=owner_id,
        name=request.name,
        display_name=request.display_name or request.name,
        vector_store_provider="pinecone",
        embedding_provider="gemini",
        dimension=dimension,
        namespace=request.namespace,
        metadata=request.metadata
    )
    
    result = await db.rag_indices.insert_one(index_doc.model_dump(by_alias=True))
    
    if tenant:
        await log_simple_action(
            tenant_id=tenant.id,
            org_unit_id=owner_id,
            actor_id=current_user.id,
            actor_type=ActorType.USER,
            actor_email=current_user.email,
            action=Action.WRITE,
            resource_type=ResourceType.INDEX,
            resource_id=str(result.inserted_id),
            resource_name=request.name,
            request=http_request,
        )
    
    return {"status": "created", "name": request.name, "dimension": dimension}


@router.get("/indices/{index_name}")
async def get_index(
    index_name: str,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    db = MongoDatabase.get_db()
    
    tenant = None
    if tenant_slug:
        tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
        if tenant_doc:
            tenant = Tenant(**tenant_doc)
    
    if not await require_index_permission(tenant, current_user, Action.READ, index_name):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    vector_store = RAGFactory.create_vector_store(VectorStoreConfig())
    stats = await vector_store.get_index_stats(index_name)
    
    if not stats:
        raise HTTPException(status_code=404, detail="Index not found")
    
    query = {"name": index_name}
    if tenant:
        query["tenant_id"] = tenant.id
    
    db_record = await db.rag_indices.find_one(query)
    
    return {
        "name": index_name,
        "display_name": db_record.get("display_name") if db_record else index_name,
        "dimension": stats.dimension,
        "total_vectors": stats.total_vector_count,
        "namespaces": stats.namespaces,
        "metadata": db_record.get("metadata", {}) if db_record else {},
        "tenant_id": str(db_record.get("tenant_id")) if db_record and db_record.get("tenant_id") else None,
        "owner_id": str(db_record.get("owner_id")) if db_record and db_record.get("owner_id") else None,
    }


@router.delete("/indices/{index_name}")
async def delete_index(
    index_name: str,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    db = MongoDatabase.get_db()
    
    tenant = None
    if tenant_slug:
        tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
        if tenant_doc:
            tenant = Tenant(**tenant_doc)
    
    if not await require_index_permission(tenant, current_user, Action.DELETE, index_name):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {"name": index_name}
    if tenant:
        query["tenant_id"] = tenant.id
    
    index_doc = await db.rag_indices.find_one(query)
    
    vector_store = RAGFactory.create_vector_store(VectorStoreConfig())
    success = await vector_store.delete_index(index_name)
    
    await db.rag_indices.delete_one(query)
    
    if tenant and index_doc:
        await log_simple_action(
            tenant_id=tenant.id,
            org_unit_id=index_doc.get("owner_id"),
            actor_id=current_user.id,
            actor_type=ActorType.USER,
            actor_email=current_user.email,
            action=Action.DELETE,
            resource_type=ResourceType.INDEX,
            resource_id=str(index_doc["_id"]),
            resource_name=index_name,
            request=http_request,
        )
    
    return {"status": "deleted" if success else "not_found", "name": index_name}


@router.post("/chunk-preview")
async def chunk_preview(
    request: ChunkPreviewRequest,
    admin: User = Depends(get_admin_user)
):
    chunker = RAGFactory.create_chunker(ChunkerConfig(
        target_tokens=request.chunk_size,
        max_tokens=request.chunk_size + 100,
        overlap_tokens=request.chunk_overlap
    ))
    
    chunks = chunker.chunk(request.text, "preview_doc")
    
    return {
        "total_chunks": len(chunks),
        "chunks": [
            {
                "id": c.id,
                "text": c.text,
                "token_count": c.token_count,
                "start_index": c.start_index,
                "end_index": c.end_index
            }
            for c in chunks
        ]
    }


@router.post("/ingest")
async def ingest_documents(
    request: IngestionRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_admin_user)
):
    import uuid
    from app.workers.job_manager import job_manager
    from app.workers.tasks import ingest_documents_task
    
    db = MongoDatabase.get_db()
    job_id = str(uuid.uuid4())
    
    job_doc = RAGIngestionJob(
        index_name=request.index_name,
        source_type="api",
        source_path="direct_upload",
        namespace=request.namespace,
        created_by=str(admin.id)
    )
    result = await db.rag_jobs.insert_one(job_doc.model_dump(by_alias=True))
    db_job_id = str(result.inserted_id)
    
    await job_manager.create_job(
        job_id=job_id,
        index_name=request.index_name,
        source_type="api",
        total_documents=len(request.documents)
    )
    
    if request.use_celery:
        ingest_documents_task.delay(
            job_id=job_id,
            index_name=request.index_name,
            documents=request.documents,
            namespace=request.namespace,
            embedding_provider=request.embedding_provider,
            vector_store_provider=request.vector_store_provider,
            chunker_strategy=request.chunker_strategy,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap
        )
        
        return {
            "job_id": job_id,
            "db_job_id": db_job_id,
            "status": "queued",
            "message": f"Ingestion job queued for {len(request.documents)} documents",
            "websocket_url": f"/admin/rag/ws/jobs/{job_id}"
        }
    else:
        embedding = RAGFactory.create_embedding_provider(EmbeddingConfig(
            provider=EmbeddingProviderType(request.embedding_provider)
        ))
        vector_store = RAGFactory.create_vector_store(VectorStoreConfig(
            provider=VectorStoreType(request.vector_store_provider)
        ))
        chunker = RAGFactory.create_chunker(ChunkerConfig(
            strategy=ChunkerType(request.chunker_strategy),
            target_tokens=request.chunk_size,
            overlap_tokens=request.chunk_overlap
        ))
        
        orchestrator = RAGOrchestrator(
            embedding_provider=embedding,
            vector_store=vector_store,
            chunker=chunker
        )
        
        job = orchestrator.create_job(
            IngestionJobConfig(
                source_type="api",
                source_path="direct_upload",
                index_name=request.index_name,
                namespace=request.namespace
            ),
            created_by=str(admin.id)
        )
        
        async def run_ingestion():
            try:
                await db.rag_jobs.update_one(
                    {"_id": ObjectId(db_job_id)},
                    {"$set": {"status": RAGIngestionJobStatus.RUNNING, "started_at": datetime.utcnow()}}
                )
                
                job_result = await orchestrator.run_ingestion(job.id, request.documents)
                
                await db.rag_jobs.update_one(
                    {"_id": ObjectId(db_job_id)},
                    {"$set": {
                        "status": job_result.status,
                        "total_documents": job_result.total_documents,
                        "total_chunks": job_result.total_chunks,
                        "upserted_chunks": job_result.successful_upserts,
                        "failed_chunks": job_result.failed_upserts,
                        "completed_at": datetime.utcnow(),
                        "error_message": job_result.errors[0] if job_result.errors else None
                    }}
                )
                
            except Exception as e:
                await db.rag_jobs.update_one(
                    {"_id": ObjectId(db_job_id)},
                    {"$set": {
                        "status": RAGIngestionJobStatus.FAILED,
                        "error_message": str(e),
                        "completed_at": datetime.utcnow()
                    }}
                )
        
        background_tasks.add_task(run_ingestion)
        
        return {
            "job_id": job_id,
            "db_job_id": db_job_id,
            "status": "started",
            "message": f"Ingestion job started for {len(request.documents)} documents"
        }


@router.post("/ingest-from-loader")
async def ingest_from_loader(
    request: LoaderIngestionRequest,
    admin: User = Depends(get_admin_user)
):
    import uuid
    from app.workers.job_manager import job_manager
    from app.workers.tasks import ingest_from_loader_task
    
    db = MongoDatabase.get_db()
    job_id = str(uuid.uuid4())
    
    job_doc = RAGIngestionJob(
        index_name=request.index_name,
        source_type=request.loader_type,
        source_path=request.source_path,
        namespace=request.namespace,
        created_by=str(admin.id)
    )
    await db.rag_jobs.insert_one(job_doc.model_dump(by_alias=True))
    
    await job_manager.create_job(
        job_id=job_id,
        index_name=request.index_name,
        source_type=request.loader_type
    )
    
    ingest_from_loader_task.delay(
        job_id=job_id,
        index_name=request.index_name,
        loader_type=request.loader_type,
        source_path=request.source_path,
        namespace=request.namespace,
        loader_config=request.loader_config,
        embedding_provider=request.embedding_provider,
        vector_store_provider=request.vector_store_provider,
        chunker_strategy=request.chunker_strategy,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap
    )
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Loader ingestion job queued for {request.source_path}",
        "websocket_url": f"/admin/rag/ws/jobs/{job_id}"
    }


@router.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str, admin: User = Depends(get_admin_user)):
    from app.workers.job_manager import job_manager
    
    progress = await job_manager.get_progress(job_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return progress.model_dump()


@router.get("/jobs")
async def list_jobs(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    db = MongoDatabase.get_db()
    
    tenant = None
    query: Dict[str, Any] = {}
    if tenant_slug:
        tenant_doc = await db.tenants.find_one({"slug": tenant_slug})
        if tenant_doc:
            tenant = Tenant(**tenant_doc)
            query["tenant_id"] = tenant.id
    
    if current_user.role != "admin" and not tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    
    if status:
        query["status"] = status
    
    cursor = db.rag_jobs.find(query).sort("created_at", -1).skip(skip).limit(limit)
    jobs = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        if doc.get("tenant_id"):
            doc["tenant_id"] = str(doc["tenant_id"])
        if doc.get("owner_id"):
            doc["owner_id"] = str(doc["owner_id"])
        jobs.append(doc)
    
    total = await db.rag_jobs.count_documents(query)
    
    return {
        "items": jobs,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, admin: User = Depends(get_admin_user)):
    db = MongoDatabase.get_db()
    
    try:
        doc = await db.rag_jobs.find_one({"_id": ObjectId(job_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Job not found")
        
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        return doc
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/pipelines")
async def list_pipelines(admin: User = Depends(get_admin_user)):
    db = MongoDatabase.get_db()
    
    cursor = db.rag_pipelines.find({}).sort("created_at", -1)
    pipelines = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        pipelines.append(doc)
    
    return {"pipelines": pipelines}


@router.post("/pipelines")
async def create_pipeline(
    request: PipelineConfigRequest,
    admin: User = Depends(get_admin_user)
):
    db = MongoDatabase.get_db()
    
    if request.is_default:
        await db.rag_pipelines.update_many({}, {"$set": {"is_default": False}})
    
    pipeline = RAGPipelineConfig(
        name=request.name,
        description=request.description,
        embedding_provider=request.embedding_provider,
        vector_store_provider=request.vector_store_provider,
        chunker_strategy=request.chunker_strategy,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        is_default=request.is_default
    )
    
    result = await db.rag_pipelines.insert_one(pipeline.model_dump(by_alias=True))
    
    return {"id": str(result.inserted_id), "status": "created"}
