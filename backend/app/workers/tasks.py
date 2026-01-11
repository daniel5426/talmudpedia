import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from celery import shared_task
from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app
from app.workers.job_manager import job_manager, JobStatus

logger = get_task_logger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="app.workers.tasks.ingest_documents_task")
def ingest_documents_task(
    self,
    job_id: str,
    index_name: str,
    documents: List[Dict[str, Any]],
    namespace: Optional[str] = None,
    embedding_provider: str = "gemini",
    vector_store_provider: str = "pinecone",
    chunker_strategy: str = "token_based",
    chunk_size: int = 650,
    chunk_overlap: int = 50
):
    async def _run():
        from app.rag.factory import (
            RAGFactory,
            EmbeddingConfig,
            VectorStoreConfig,
            ChunkerConfig,
            EmbeddingProviderType,
            VectorStoreType,
            ChunkerType,
        )
        from app.rag.interfaces import VectorDocument
        
        await job_manager.mark_started(job_id)
        
        try:
            embedding_config = EmbeddingConfig(
                provider=EmbeddingProviderType(embedding_provider)
            )
            vector_config = VectorStoreConfig(
                provider=VectorStoreType(vector_store_provider)
            )
            chunker_config = ChunkerConfig(
                strategy=ChunkerType(chunker_strategy),
                target_tokens=chunk_size,
                chunk_size=chunk_size,
                overlap_tokens=chunk_overlap
            )
            
            embedding = RAGFactory.create_embedding_provider(embedding_config)
            vector_store = RAGFactory.create_vector_store(vector_config)
            chunker = RAGFactory.create_chunker(chunker_config)
            
            await job_manager.update_progress(
                job_id,
                current_stage="chunking",
                total_documents=len(documents)
            )
            
            all_chunks = []
            for i, doc in enumerate(documents):
                doc_id = doc.get("id", f"doc_{i}")
                text = doc.get("text", doc.get("content", ""))
                metadata = doc.get("metadata", {})
                
                chunks = chunker.chunk(text, doc_id, metadata)
                all_chunks.extend(chunks)
                
                await job_manager.update_progress(
                    job_id,
                    current_stage="chunking",
                    processed_documents=i + 1,
                    total_chunks=len(all_chunks)
                )
            
            await job_manager.update_progress(
                job_id,
                current_stage="embedding",
                total_chunks=len(all_chunks)
            )
            
            batch_size = 50
            successful_upserts = 0
            failed_upserts = 0
            
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i:i + batch_size]
                texts = [c.text for c in batch]
                
                embeddings = await embedding.embed_batch(texts)
                
                await job_manager.update_progress(
                    job_id,
                    current_stage="upserting"
                )
                
                vector_docs = []
                for chunk, emb in zip(batch, embeddings):
                    if not emb.values:
                        failed_upserts += 1
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
                    count = await vector_store.upsert(
                        index_name=index_name,
                        documents=vector_docs,
                        namespace=namespace
                    )
                    successful_upserts += count
                
                await job_manager.update_progress(
                    job_id,
                    upserted_chunks=successful_upserts,
                    failed_chunks=failed_upserts
                )
            
            await job_manager.mark_completed(
                job_id,
                total_documents=len(documents),
                total_chunks=len(all_chunks),
                upserted_chunks=successful_upserts,
                failed_chunks=failed_upserts
            )
            
            return {
                "job_id": job_id,
                "status": "completed",
                "total_documents": len(documents),
                "total_chunks": len(all_chunks),
                "successful_upserts": successful_upserts,
                "failed_upserts": failed_upserts
            }
            
        except Exception as e:
            logger.error(f"Ingestion job {job_id} failed: {str(e)}")
            await job_manager.mark_failed(job_id, str(e))
            raise
    
    return run_async(_run())


@celery_app.task(bind=True, name="app.workers.tasks.ingest_from_loader_task")
def ingest_from_loader_task(
    self,
    job_id: str,
    index_name: str,
    loader_type: str,
    source_path: str,
    namespace: Optional[str] = None,
    loader_config: Optional[Dict[str, Any]] = None,
    embedding_provider: str = "gemini",
    vector_store_provider: str = "pinecone",
    chunker_strategy: str = "token_based",
    chunk_size: int = 650,
    chunk_overlap: int = 50
):
    async def _run():
        from app.rag.factory import (
            RAGFactory,
            EmbeddingConfig,
            VectorStoreConfig,
            ChunkerConfig,
            LoaderConfig,
            EmbeddingProviderType,
            VectorStoreType,
            ChunkerType,
            LoaderType,
        )
        from app.rag.interfaces import VectorDocument
        
        await job_manager.mark_started(job_id)
        
        try:
            loader_cfg = LoaderConfig(
                loader_type=LoaderType(loader_type),
                **(loader_config or {})
            )
            embedding_config = EmbeddingConfig(
                provider=EmbeddingProviderType(embedding_provider)
            )
            vector_config = VectorStoreConfig(
                provider=VectorStoreType(vector_store_provider)
            )
            chunker_config = ChunkerConfig(
                strategy=ChunkerType(chunker_strategy),
                target_tokens=chunk_size,
                chunk_size=chunk_size,
                overlap_tokens=chunk_overlap
            )
            
            loader = RAGFactory.create_loader(loader_cfg)
            embedding = RAGFactory.create_embedding_provider(embedding_config)
            vector_store = RAGFactory.create_vector_store(vector_config)
            chunker = RAGFactory.create_chunker(chunker_config)
            
            await job_manager.update_progress(
                job_id,
                current_stage="loading"
            )
            
            raw_documents = await loader.load(source_path)
            
            await job_manager.update_progress(
                job_id,
                current_stage="chunking",
                total_documents=len(raw_documents)
            )
            
            all_chunks = []
            for i, doc in enumerate(raw_documents):
                chunks = chunker.chunk(doc.content, doc.id, doc.metadata)
                all_chunks.extend(chunks)
                
                await job_manager.update_progress(
                    job_id,
                    current_stage="chunking",
                    processed_documents=i + 1,
                    total_chunks=len(all_chunks)
                )
            
            await job_manager.update_progress(
                job_id,
                current_stage="embedding",
                total_chunks=len(all_chunks)
            )
            
            batch_size = 50
            successful_upserts = 0
            failed_upserts = 0
            
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i:i + batch_size]
                texts = [c.text for c in batch]
                
                embeddings = await embedding.embed_batch(texts)
                
                await job_manager.update_progress(
                    job_id,
                    current_stage="upserting"
                )
                
                vector_docs = []
                for chunk, emb in zip(batch, embeddings):
                    if not emb.values:
                        failed_upserts += 1
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
                    count = await vector_store.upsert(
                        index_name=index_name,
                        documents=vector_docs,
                        namespace=namespace
                    )
                    successful_upserts += count
                
                await job_manager.update_progress(
                    job_id,
                    upserted_chunks=successful_upserts,
                    failed_chunks=failed_upserts
                )
            
            await job_manager.mark_completed(
                job_id,
                total_documents=len(raw_documents),
                total_chunks=len(all_chunks),
                upserted_chunks=successful_upserts,
                failed_chunks=failed_upserts
            )
            
            return {
                "job_id": job_id,
                "status": "completed",
                "total_documents": len(raw_documents),
                "total_chunks": len(all_chunks),
                "successful_upserts": successful_upserts,
                "failed_upserts": failed_upserts
            }
            
        except Exception as e:
            logger.error(f"Loader ingestion job {job_id} failed: {str(e)}")
            await job_manager.mark_failed(job_id, str(e))
            raise
    
    return run_async(_run())


@celery_app.task(name="app.workers.tasks.health_check")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
