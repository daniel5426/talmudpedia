import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.rag.factory import RAGFactory, VectorStoreConfig
from app.api.schemas.rag import RAGIndex, RAGStats
from app.db.postgres.models.rag import RAGPipeline, PipelineJob, PipelineJobStatus

class RAGAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Initialize with default vector store provider
        self.vector_store = RAGFactory.create_vector_store(VectorStoreConfig())

    async def list_indices(self) -> List[RAGIndex]:
        """List all indices from the vector store."""
        index_names = await self.vector_store.list_indices()
        indices = []
        for name in index_names:
            stats = await self.vector_store.get_index_stats(name)
            if stats:
                indices.append(RAGIndex(
                    name=name,
                    display_name=name,
                    dimension=stats.dimension,
                    total_vectors=stats.total_vector_count,
                    namespaces=stats.namespaces,
                    status="active",
                    synced=True
                ))
        return indices

    async def get_index(self, name: str) -> Optional[RAGIndex]:
        """Get details for a specific index."""
        stats = await self.vector_store.get_index_stats(name)
        if not stats:
            return None
        return RAGIndex(
            name=name,
            display_name=name,
            dimension=stats.dimension,
            total_vectors=stats.total_vector_count,
            namespaces=stats.namespaces,
            status="active",
            synced=True
        )

    async def create_index(self, name: str, dimension: int = 768) -> bool:
        """Create a new index in the vector store."""
        return await self.vector_store.create_index(name, dimension)

    async def delete_index(self, name: str) -> bool:
        """Delete an index from the vector store."""
        return await self.vector_store.delete_index(name)

    async def get_stats(self, tenant_id: Optional[uuid.UUID] = None) -> RAGStats:
        """Get aggregated RAG statistics."""
        # DB Stats
        pipe_stmt = select(func.count(RAGPipeline.id))
        job_stmt = select(func.count(PipelineJob.id))
        
        if tenant_id:
            pipe_stmt = pipe_stmt.where(RAGPipeline.tenant_id == tenant_id)
            job_stmt = job_stmt.where(PipelineJob.tenant_id == tenant_id)
            
        total_pipelines = (await self.db.execute(pipe_stmt)).scalar() or 0
        total_jobs = (await self.db.execute(job_stmt)).scalar() or 0
        
        # Job counts by status
        completed_stmt = job_stmt.where(PipelineJob.status == PipelineJobStatus.COMPLETED)
        failed_stmt = job_stmt.where(PipelineJob.status == PipelineJobStatus.FAILED)
        processing_stmt = job_stmt.where(PipelineJob.status == PipelineJobStatus.RUNNING)
        
        completed_jobs = (await self.db.execute(completed_stmt)).scalar() or 0
        failed_jobs = (await self.db.execute(failed_stmt)).scalar() or 0
        running_jobs = (await self.db.execute(processing_stmt)).scalar() or 0
        
        # Vector Store Stats
        indices = await self.list_indices()
        total_chunks = sum(idx.total_vectors for idx in indices)
        
        return RAGStats(
            total_indices=len(indices),
            live_indices=len(indices),
            total_chunks=total_chunks,
            total_jobs=total_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            running_jobs=running_jobs,
            total_pipelines=total_pipelines,
            available_providers=RAGFactory.get_available_providers()
        )
