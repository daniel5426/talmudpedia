import asyncio
import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import and_, select

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


def _truncate_error(raw: str, *, max_chars: int = 4000) -> str:
    text = (raw or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [truncated]"


def _sanitize_project_path(path: str) -> Path:
    candidate = PurePosixPath((path or "").replace("\\", "/").strip())
    if candidate.is_absolute():
        raise ValueError(f"Absolute path is not allowed: {path}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError(f"Invalid project file path: {path}")
    return Path(*candidate.parts)


def _materialize_project_files(project_dir: Path, files: Dict[str, str]) -> None:
    for file_path, content in (files or {}).items():
        relative_path = _sanitize_project_path(file_path)
        full_path = project_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content if isinstance(content, str) else str(content), encoding="utf-8")


async def _run_subprocess(command: List[str], *, cwd: Path, timeout_seconds: int) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return 124, "", f"Command timed out after {timeout_seconds}s: {' '.join(command)}"
    return process.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


def _build_dist_manifest(dist_dir: Path) -> Dict[str, Any]:
    assets: List[Dict[str, Any]] = []
    entry_html: Optional[str] = None

    for path in sorted(dist_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(dist_dir).as_posix()
        payload = path.read_bytes()
        sha = hashlib.sha256(payload).hexdigest()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if entry_html is None and relative.endswith(".html"):
            entry_html = relative
        assets.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": sha,
                "content_type": content_type,
            }
        )

    if not assets:
        raise ValueError("Build completed without dist assets")

    return {
        "entry_html": entry_html or "index.html",
        "assets": assets,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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


@celery_app.task(bind=True, name="app.workers.tasks.build_published_app_revision_task")
def build_published_app_revision_task(
    self,
    revision_id: str,
    tenant_id: str,
    app_id: str,
    slug: str,
    build_kind: str,
):
    async def _run():
        from app.db.postgres.models.published_apps import (
            PublishedAppRevision,
            PublishedAppRevisionBuildStatus,
        )
        from app.db.postgres.session import sessionmaker
        from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
        from app.services.published_app_bundle_storage import (
            PublishedAppBundleStorage,
        )

        revision_uuid = UUID(str(revision_id))
        app_uuid = UUID(str(app_id))
        requested_seq = 0
        source_files: Dict[str, str] = {}
        project_entry_file = "src/main.tsx"
        now = datetime.now(timezone.utc)

        async with sessionmaker() as db:
            result = await db.execute(
                select(PublishedAppRevision).where(
                    and_(
                        PublishedAppRevision.id == revision_uuid,
                        PublishedAppRevision.published_app_id == app_uuid,
                    )
                ).limit(1)
            )
            revision = result.scalar_one_or_none()
            if revision is None:
                logger.warning("build task ignored: revision not found", extra={"revision_id": revision_id, "app_id": app_id})
                return {
                    "status": "missing",
                    "revision_id": revision_id,
                    "app_id": app_id,
                }

            requested_seq = int(revision.build_seq or 0)
            source_files = dict(revision.files or {})
            project_entry_file = revision.entry_file or "src/main.tsx"
            revision.build_status = PublishedAppRevisionBuildStatus.running
            revision.build_started_at = now
            revision.build_finished_at = None
            revision.build_error = None
            await db.commit()

        dist_storage_prefix: Optional[str] = None
        dist_manifest: Optional[Dict[str, Any]] = None

        try:
            diagnostics = validate_builder_dependency_policy(source_files)
            if diagnostics:
                raise ValueError("; ".join(item.get("message", "Build policy violation") for item in diagnostics))

            npm_ci_timeout = int(os.getenv("APPS_BUILD_NPM_CI_TIMEOUT_SECONDS", "300"))
            npm_build_timeout = int(os.getenv("APPS_BUILD_NPM_BUILD_TIMEOUT_SECONDS", "300"))

            with tempfile.TemporaryDirectory(prefix=f"apps-build-{revision_id[:8]}-") as temp_dir:
                project_dir = Path(temp_dir)
                _materialize_project_files(project_dir, source_files)

                has_lockfile = (project_dir / "package-lock.json").exists()
                install_command = ["npm", "ci"] if has_lockfile else ["npm", "install", "--no-audit", "--no-fund"]
                install_code, install_stdout, install_stderr = await _run_subprocess(
                    install_command,
                    cwd=project_dir,
                    timeout_seconds=npm_ci_timeout,
                )
                if install_code != 0:
                    install_name = "npm ci" if has_lockfile else "npm install"
                    raise RuntimeError(
                        f"`{install_name}` failed with exit code {install_code}\n{install_stderr or install_stdout}"
                    )

                npm_build_code, npm_build_stdout, npm_build_stderr = await _run_subprocess(
                    ["npm", "run", "build"],
                    cwd=project_dir,
                    timeout_seconds=npm_build_timeout,
                )
                if npm_build_code != 0:
                    raise RuntimeError(
                        f"`npm run build` failed with exit code {npm_build_code}\n{npm_build_stderr or npm_build_stdout}"
                    )

                dist_dir = project_dir / "dist"
                if not dist_dir.exists() or not dist_dir.is_dir():
                    raise RuntimeError("Build succeeded but dist directory was not produced")

                dist_manifest = _build_dist_manifest(dist_dir)
                if str(project_entry_file).strip() and str(project_entry_file).endswith(".tsx"):
                    dist_manifest["source_entry_file"] = project_entry_file

                storage = PublishedAppBundleStorage.from_env()
                dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                    tenant_id=str(tenant_id),
                    app_id=str(app_id),
                    revision_id=str(revision_id),
                )

                uploaded = 0
                for file_path in sorted(dist_dir.rglob("*")):
                    if not file_path.is_file():
                        continue
                    relative_path = file_path.relative_to(dist_dir).as_posix()
                    cache_control = "public, max-age=31536000, immutable"
                    if relative_path.endswith(".html"):
                        cache_control = "no-store"
                    storage.write_asset_bytes(
                        dist_storage_prefix=dist_storage_prefix,
                        asset_path=relative_path,
                        payload=file_path.read_bytes(),
                        content_type=mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
                        cache_control=cache_control,
                    )
                    uploaded += 1

                dist_manifest["uploaded_assets"] = uploaded

        except Exception as exc:
            failure_message = _truncate_error(str(exc) or repr(exc))
            async with sessionmaker() as db:
                result = await db.execute(
                    select(PublishedAppRevision).where(
                        and_(
                            PublishedAppRevision.id == revision_uuid,
                            PublishedAppRevision.published_app_id == app_uuid,
                        )
                    ).limit(1)
                )
                revision = result.scalar_one_or_none()
                if revision is None:
                    return {
                        "status": "missing_after_failure",
                        "revision_id": revision_id,
                        "app_id": app_id,
                    }
                if int(revision.build_seq or 0) != requested_seq:
                    return {
                        "status": "stale",
                        "revision_id": revision_id,
                        "requested_seq": requested_seq,
                        "current_seq": int(revision.build_seq or 0),
                    }
                revision.build_status = PublishedAppRevisionBuildStatus.failed
                revision.build_error = failure_message
                revision.build_finished_at = datetime.now(timezone.utc)
                await db.commit()

            logger.error(
                "published app build failed",
                extra={"revision_id": revision_id, "app_id": app_id, "error": failure_message},
            )
            return {
                "status": "failed",
                "revision_id": revision_id,
                "tenant_id": tenant_id,
                "app_id": app_id,
                "slug": slug,
                "build_kind": build_kind,
                "error": failure_message,
            }

        async with sessionmaker() as db:
            result = await db.execute(
                select(PublishedAppRevision).where(
                    and_(
                        PublishedAppRevision.id == revision_uuid,
                        PublishedAppRevision.published_app_id == app_uuid,
                    )
                ).limit(1)
            )
            revision = result.scalar_one_or_none()
            if revision is None:
                return {
                    "status": "missing_after_start",
                    "revision_id": revision_id,
                    "app_id": app_id,
                }

            if int(revision.build_seq or 0) != requested_seq:
                logger.info(
                    "build task stale completion ignored",
                    extra={"revision_id": revision_id, "app_id": app_id, "requested_seq": requested_seq, "current_seq": revision.build_seq},
                )
                return {
                    "status": "stale",
                    "revision_id": revision_id,
                    "requested_seq": requested_seq,
                    "current_seq": int(revision.build_seq or 0),
                }

            revision.build_status = PublishedAppRevisionBuildStatus.succeeded
            revision.build_error = None
            revision.dist_storage_prefix = dist_storage_prefix
            revision.dist_manifest = dist_manifest
            revision.build_finished_at = datetime.now(timezone.utc)
            await db.commit()

        return {
            "status": "succeeded",
            "revision_id": revision_id,
            "tenant_id": tenant_id,
            "app_id": app_id,
            "slug": slug,
            "build_kind": build_kind,
            "dist_storage_prefix": dist_storage_prefix,
        }

    return run_async(_run())
