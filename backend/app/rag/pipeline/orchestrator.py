import asyncio
from typing import List, Optional, Callable, Awaitable
from datetime import datetime
import uuid

from app.rag.interfaces import (
    EmbeddingProvider,
    VectorStoreProvider,
    ChunkerStrategy,
    Chunk,
    VectorDocument,
)
from app.rag.pipeline.job import (
    IngestionJob,
    JobStatus,
    JobProgress,
    JobResult,
    IngestionJobConfig,
    JobType,
)


class RAGOrchestrator:
    
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStoreProvider,
        chunker: ChunkerStrategy,
        batch_size: int = 50,
        on_progress: Optional[Callable[[JobProgress], Awaitable[None]]] = None
    ):
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._chunker = chunker
        self._batch_size = batch_size
        self._on_progress = on_progress
        self._jobs: dict[str, IngestionJob] = {}
    
    def create_job(
        self,
        config: IngestionJobConfig,
        created_by: Optional[str] = None
    ) -> IngestionJob:
        job = IngestionJob(
            id=str(uuid.uuid4()),
            config=config,
            created_by=created_by
        )
        self._jobs[job.id] = job
        return job
    
    def get_job(self, job_id: str) -> Optional[IngestionJob]:
        return self._jobs.get(job_id)
    
    def list_jobs(self) -> List[IngestionJob]:
        return list(self._jobs.values())
    
    async def run_ingestion(
        self,
        job_id: str,
        documents: List[dict],
    ) -> JobResult:
        job = self._jobs.get(job_id)
        if not job:
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                total_documents=0,
                total_chunks=0,
                successful_upserts=0,
                failed_upserts=0,
                duration_seconds=0,
                errors=["Job not found"]
            )
        
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.progress.total_documents = len(documents)
        job.progress.current_stage = "chunking"
        
        start_time = datetime.utcnow()
        errors: List[str] = []
        all_chunks: List[Chunk] = []
        
        try:
            for i, doc in enumerate(documents):
                doc_id = doc.get("id", f"doc_{i}")
                text = doc.get("text", doc.get("content", ""))
                metadata = doc.get("metadata", {})
                
                chunks = self._chunker.chunk(text, doc_id, metadata)
                all_chunks.extend(chunks)
                
                job.progress.processed_documents = i + 1
                job.progress.total_chunks = len(all_chunks)
                
                if self._on_progress:
                    await self._on_progress(job.progress)
            
            job.progress.current_stage = "embedding"
            
            successful_upserts = 0
            failed_upserts = 0
            
            for i in range(0, len(all_chunks), self._batch_size):
                batch = all_chunks[i:i + self._batch_size]
                texts = [c.text for c in batch]
                
                embeddings = await self._embedding.embed_batch(texts)
                
                job.progress.current_stage = "upserting"
                
                vector_docs: List[VectorDocument] = []
                for chunk, emb in zip(batch, embeddings):
                    if not emb.values:
                        failed_upserts += 1
                        errors.append(f"Failed to embed chunk: {chunk.id}")
                        continue
                    
                    vector_docs.append(VectorDocument(
                        id=chunk.id,
                        values=emb.values,
                        metadata={
                            "text": chunk.text,
                            **chunk.metadata
                        }
                    ))
                
                if vector_docs:
                    count = await self._vector_store.upsert(
                        index_name=job.config.index_name,
                        documents=vector_docs,
                        namespace=job.config.namespace
                    )
                    successful_upserts += count
                
                job.progress.upserted_chunks = successful_upserts
                job.progress.failed_chunks = failed_upserts
                
                if self._on_progress:
                    await self._on_progress(job.progress)
            
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            errors.append(str(e))
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return JobResult(
            job_id=job_id,
            status=job.status,
            total_documents=job.progress.processed_documents,
            total_chunks=job.progress.total_chunks,
            successful_upserts=job.progress.upserted_chunks,
            failed_upserts=job.progress.failed_chunks,
            duration_seconds=duration,
            errors=errors
        )
    
    async def delete_from_index(
        self,
        index_name: str,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> bool:
        return await self._vector_store.delete(index_name, ids, namespace)
