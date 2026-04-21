import asyncio
import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import and_, select

from app.workers.celery_app import celery_app
from app.workers.job_manager import job_manager, JobStatus
from app.workers.async_runner import run_async

logger = get_task_logger(__name__)


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


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost")


def _apps_url_scheme() -> str:
    from app.core.runtime_urls import resolve_apps_url_scheme

    return resolve_apps_url_scheme()


def _apps_url_port() -> str:
    from app.core.runtime_urls import resolve_apps_url_port

    return resolve_apps_url_port()


def _build_published_url(public_id: str) -> str:
    from app.core.runtime_urls import build_published_app_url

    return build_published_app_url(public_id)


def _publish_mock_mode_enabled() -> bool:
    raw = (os.getenv("APPS_PUBLISH_MOCK_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _agent_run_task_time_limit_seconds() -> int:
    raw = (os.getenv("AGENT_RUN_TASK_TIME_LIMIT_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else 8 * 60 * 60
    except Exception:
        value = 8 * 60 * 60
    return max(300, value)


def _agent_run_task_soft_time_limit_seconds() -> int:
    hard_limit = _agent_run_task_time_limit_seconds()
    raw = (os.getenv("AGENT_RUN_TASK_SOFT_TIME_LIMIT_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else hard_limit - 60
    except Exception:
        value = hard_limit - 60
    return max(240, min(value, hard_limit))


@celery_app.task(
    bind=True,
    name="app.workers.tasks.execute_agent_run_task",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=_agent_run_task_time_limit_seconds(),
    soft_time_limit=_agent_run_task_soft_time_limit_seconds(),
)
def execute_agent_run_task(self, run_id: str):
    async def _run() -> str:
        from app.agent.execution.service import AgentExecutorService

        return await AgentExecutorService.execute_worker_run_with_new_session(
            run_id=UUID(str(run_id)),
            owner_id=str(self.request.id or ""),
        )

    try:
        status = run_async(_run())
    except Exception as exc:
        logger.error("Generic agent worker task failed for run %s: %s", run_id, exc)
        raise

    if status == "busy":
        raise self.retry(countdown=5, max_retries=12)
    return status


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
    organization_id: str,
    app_id: str,
    public_id: str,
    build_kind: str,
):
    async def _run():
        from app.db.postgres.models.published_apps import (
            PublishedAppRevision,
            PublishedAppRevisionBuildStatus,
        )
        from app.db.postgres.session import sessionmaker
        from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
        from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay
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
            source_files = apply_runtime_bootstrap_overlay(
                dict(revision.files or {}),
                runtime_context=TemplateRuntimeContext(
                    app_id=str(app_id),
                    app_public_id=str(public_id or ""),
                ),
            )
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
                    organization_id=str(organization_id),
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
                "organization_id": organization_id,
                "app_id": app_id,
                "app_public_id": public_id,
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
            "organization_id": organization_id,
            "app_id": app_id,
            "app_public_id": public_id,
            "build_kind": build_kind,
            "dist_storage_prefix": dist_storage_prefix,
        }

    return run_async(_run())


@celery_app.task(bind=True, name="app.workers.tasks.publish_version_pointer_after_build_task")
def publish_version_pointer_after_build_task(
    self,
    job_id: str,
):
    async def _run():
        from app.db.postgres.models.published_apps import (
            PublishedApp,
            PublishedAppPublishJob,
            PublishedAppPublishJobStatus,
            PublishedAppRevision,
            PublishedAppRevisionBuildStatus,
            PublishedAppStatus,
        )
        from app.db.postgres.session import sessionmaker
        from app.services.published_app_publish_autofix import submit_publish_build_failure_autofix

        poll_interval_seconds = max(
            1,
            int(os.getenv("APPS_PUBLISH_WAIT_BUILD_POLL_SECONDS", "2") or 2),
        )
        timeout_seconds = max(
            30,
            int(os.getenv("APPS_PUBLISH_WAIT_BUILD_TIMEOUT_SECONDS", "900") or 900),
        )
        started_at = datetime.now(timezone.utc)
        deadline = started_at.timestamp() + float(timeout_seconds)
        job_uuid = UUID(str(job_id))

        async def _mark_failed(
            *,
            db,
            job: PublishedAppPublishJob,
            app: PublishedApp | None,
            revision: PublishedAppRevision | None,
            reason: str,
            build_related: bool,
        ) -> dict[str, Any]:
            message = _truncate_error(reason or "Publish failed while waiting for revision build")
            diagnostics = list(job.diagnostics or [])
            diagnostics.append(
                {
                    "kind": "publish_wait_build",
                    "build_wait_state": "failed",
                    "build_related": "true" if build_related else "false",
                    "message": message,
                }
            )
            job.status = PublishedAppPublishJobStatus.failed
            job.stage = "failed"
            job.error = message
            job.finished_at = datetime.now(timezone.utc)
            job.last_heartbeat_at = datetime.now(timezone.utc)
            job.diagnostics = diagnostics

            if build_related and app is not None and revision is not None:
                try:
                    autofix_result = await submit_publish_build_failure_autofix(
                        db=db,
                        app=app,
                        revision=revision,
                        requested_by=job.requested_by,
                        failure_reason=message,
                    )
                    next_diagnostics = list(job.diagnostics or [])
                    status = str(autofix_result.get("status") or "").strip().lower()
                    if status == "submitted":
                        next_diagnostics.append(
                            {
                                "kind": "auto_fix_submission",
                                "auto_fix_run_id": str(autofix_result.get("run_id") or ""),
                                "chat_session_id": str(autofix_result.get("chat_session_id") or ""),
                                "message": "Submitted automatic coding-agent fix request.",
                            }
                        )
                    else:
                        next_diagnostics.append(
                            {
                                "kind": "auto_fix_submission",
                                "auto_fix_skipped": "true",
                                "reason": str(autofix_result.get("reason") or "auto-fix was skipped"),
                                "active_run_id": str(autofix_result.get("active_run_id") or ""),
                            }
                        )
                    job.diagnostics = next_diagnostics
                except Exception as exc:
                    next_diagnostics = list(job.diagnostics or [])
                    next_diagnostics.append(
                        {
                            "kind": "auto_fix_submission",
                            "auto_fix_error": _truncate_error(str(exc) or repr(exc)),
                            "message": "Failed to auto-submit coding-agent fix request.",
                        }
                    )
                    job.diagnostics = next_diagnostics

            await db.commit()
            return {"status": "failed", "publish_job_id": str(job.id), "error": message}

        while True:
            async with sessionmaker() as db:
                job_result = await db.execute(
                    select(PublishedAppPublishJob).where(PublishedAppPublishJob.id == job_uuid).limit(1)
                )
                job = job_result.scalar_one_or_none()
                if job is None:
                    return {"status": "missing", "publish_job_id": job_id}

                app: PublishedApp | None = None
                source_revision: PublishedAppRevision | None = None
                if job.published_app_id:
                    app_result = await db.execute(
                        select(PublishedApp).where(PublishedApp.id == job.published_app_id).limit(1)
                    )
                    app = app_result.scalar_one_or_none()
                if app is None:
                    return await _mark_failed(
                        db=db,
                        job=job,
                        app=None,
                        revision=None,
                        reason="Published app not found while waiting for version build",
                        build_related=False,
                    )
                if not job.source_revision_id:
                    return await _mark_failed(
                        db=db,
                        job=job,
                        app=app,
                        revision=None,
                        reason="Publish source revision is missing",
                        build_related=False,
                    )
                revision_result = await db.execute(
                    select(PublishedAppRevision).where(
                        and_(
                            PublishedAppRevision.id == job.source_revision_id,
                            PublishedAppRevision.published_app_id == app.id,
                        )
                    ).limit(1)
                )
                source_revision = revision_result.scalar_one_or_none()
                if source_revision is None:
                    return await _mark_failed(
                        db=db,
                        job=job,
                        app=app,
                        revision=None,
                        reason="Publish source revision not found",
                        build_related=False,
                    )

                current_status = job.status.value if hasattr(job.status, "value") else str(job.status)
                if current_status not in {
                    PublishedAppPublishJobStatus.queued.value,
                    PublishedAppPublishJobStatus.running.value,
                }:
                    return {
                        "status": "noop",
                        "publish_job_id": str(job.id),
                        "job_status": current_status,
                    }

                if current_status == PublishedAppPublishJobStatus.queued.value:
                    job.status = PublishedAppPublishJobStatus.running
                job.stage = "waiting_for_build"
                job.started_at = job.started_at or started_at
                job.error = None
                job.last_heartbeat_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(job)
                await db.refresh(source_revision)

                build_status = (
                    source_revision.build_status.value
                    if hasattr(source_revision.build_status, "value")
                    else str(source_revision.build_status)
                )
                has_dist = bool(str(source_revision.dist_storage_prefix or "").strip()) and bool(source_revision.dist_manifest)
                if build_status == PublishedAppRevisionBuildStatus.succeeded.value and has_dist:
                    now = datetime.now(timezone.utc)
                    app.current_published_revision_id = source_revision.id
                    app.status = PublishedAppStatus.published
                    app.published_at = now
                    app.published_url = _build_published_url(app.public_id)
                    job.status = PublishedAppPublishJobStatus.succeeded
                    job.stage = "completed"
                    job.error = None
                    job.published_revision_id = source_revision.id
                    job.finished_at = now
                    job.last_heartbeat_at = now
                    diagnostics = list(job.diagnostics or [])
                    diagnostics.append(
                        {
                            "kind": "publish_wait_build",
                            "build_wait_state": "succeeded",
                            "version_id": str(source_revision.id),
                            "message": "Revision build succeeded; publish pointer updated.",
                        }
                    )
                    job.diagnostics = diagnostics
                    await db.commit()
                    return {
                        "status": "succeeded",
                        "publish_job_id": str(job.id),
                        "published_revision_id": str(source_revision.id),
                    }

                if build_status == PublishedAppRevisionBuildStatus.failed.value:
                    failure_reason = str(source_revision.build_error or "").strip() or "Revision build failed"
                    return await _mark_failed(
                        db=db,
                        job=job,
                        app=app,
                        revision=source_revision,
                        reason=failure_reason,
                        build_related=True,
                    )

                if datetime.now(timezone.utc).timestamp() >= deadline:
                    timeout_reason = (
                        f"Timed out after {timeout_seconds}s waiting for revision build "
                        f"(version={source_revision.id}, build_status={build_status})."
                    )
                    return await _mark_failed(
                        db=db,
                        job=job,
                        app=app,
                        revision=source_revision,
                        reason=timeout_reason,
                        build_related=True,
                    )

            await asyncio.sleep(float(poll_interval_seconds))

    return run_async(_run())


@celery_app.task(bind=True, name="app.workers.tasks.publish_published_app_task")
def publish_published_app_task(
    self,
    job_id: str,
):
    async def _run():
        from app.db.postgres.models.published_apps import (
            PublishedApp,
            PublishedAppPublishJob,
            PublishedAppPublishJobStatus,
            PublishedAppRevision,
            PublishedAppRevisionBuildStatus,
            PublishedAppRevisionKind,
            PublishedAppStatus,
        )
        from app.db.postgres.session import sessionmaker
        from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
        from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay
        from app.services.published_app_bundle_storage import PublishedAppBundleStorage
        from app.services.published_app_versioning import create_app_version

        job_uuid = UUID(str(job_id))
        source_files: Dict[str, str] = {}
        source_entry_file = "src/main.tsx"
        app_uuid: Optional[UUID] = None
        organization_uuid: Optional[UUID] = None
        slug = ""
        source_revision_uuid: Optional[UUID] = None
        published_revision_uuid = uuid4()
        dist_storage_prefix: Optional[str] = None
        dist_manifest: Optional[Dict[str, Any]] = None
        build_started_at = datetime.now(timezone.utc)
        build_finished_at: Optional[datetime] = None

        async with sessionmaker() as db:
            result = await db.execute(
                select(PublishedAppPublishJob).where(PublishedAppPublishJob.id == job_uuid).limit(1)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return {"status": "missing", "publish_job_id": job_id}

            app_result = await db.execute(
                select(PublishedApp).where(PublishedApp.id == job.published_app_id).limit(1)
            )
            app = app_result.scalar_one_or_none()
            if app is None:
                job.status = PublishedAppPublishJobStatus.failed
                job.error = "Published app not found"
                job.finished_at = datetime.now(timezone.utc)
                job.diagnostics = [{"message": "Published app not found"}]
                await db.commit()
                return {"status": "failed", "publish_job_id": job_id, "error": "Published app not found"}

            if not job.source_revision_id:
                job.status = PublishedAppPublishJobStatus.failed
                job.error = "Source draft revision is missing"
                job.finished_at = datetime.now(timezone.utc)
                job.diagnostics = [{"message": "Source draft revision is missing"}]
                await db.commit()
                return {"status": "failed", "publish_job_id": job_id, "error": "Source draft revision is missing"}

            revision_result = await db.execute(
                select(PublishedAppRevision).where(
                    and_(
                        PublishedAppRevision.id == job.source_revision_id,
                        PublishedAppRevision.published_app_id == app.id,
                    )
                ).limit(1)
            )
            source_revision = revision_result.scalar_one_or_none()
            if source_revision is None:
                job.status = PublishedAppPublishJobStatus.failed
                job.error = "Source draft revision not found"
                job.finished_at = datetime.now(timezone.utc)
                job.diagnostics = [{"message": "Source draft revision not found"}]
                await db.commit()
                return {"status": "failed", "publish_job_id": job_id, "error": "Source draft revision not found"}

            job.status = PublishedAppPublishJobStatus.running
            job.started_at = build_started_at
            job.finished_at = None
            job.error = None
            job.diagnostics = []
            await db.commit()

            source_files = apply_runtime_bootstrap_overlay(
                dict(source_revision.files or {}),
                runtime_context=TemplateRuntimeContext(
                    app_id=str(app.id),
                    app_public_id=str(app.public_id or ""),
                    agent_id=str(app.agent_id or ""),
                ),
            )
            source_entry_file = source_revision.entry_file or "src/main.tsx"
            app_uuid = app.id
            organization_uuid = app.organization_id
            public_id = app.public_id
            source_revision_uuid = source_revision.id

        try:
            diagnostics = validate_builder_dependency_policy(source_files)
            if diagnostics:
                raise ValueError("; ".join(item.get("message", "Build policy violation") for item in diagnostics))

            if _publish_mock_mode_enabled():
                dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                    organization_id=str(organization_uuid),
                    app_id=str(app_uuid),
                    revision_id=str(published_revision_uuid),
                )
                dist_manifest = {
                    "entry_html": "index.html",
                    "assets": [],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "mock_publish_build": True,
                }
                build_finished_at = datetime.now(timezone.utc)
            else:
                npm_install_timeout = int(os.getenv("APPS_BUILD_NPM_INSTALL_TIMEOUT_SECONDS", "360"))
                npm_build_timeout = int(os.getenv("APPS_BUILD_NPM_BUILD_TIMEOUT_SECONDS", "300"))

                with tempfile.TemporaryDirectory(prefix=f"apps-publish-{job_id[:8]}-") as temp_dir:
                    project_dir = Path(temp_dir)
                    _materialize_project_files(project_dir, source_files)

                    install_code, install_stdout, install_stderr = await _run_subprocess(
                        ["npm", "install", "--no-audit", "--no-fund"],
                        cwd=project_dir,
                        timeout_seconds=npm_install_timeout,
                    )
                    if install_code != 0:
                        raise RuntimeError(
                            f"`npm install` failed with exit code {install_code}\n{install_stderr or install_stdout}"
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
                    if str(source_entry_file).strip() and str(source_entry_file).endswith(".tsx"):
                        dist_manifest["source_entry_file"] = source_entry_file

                    storage = PublishedAppBundleStorage.from_env()
                    dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                        organization_id=str(organization_uuid),
                        app_id=str(app_uuid),
                        revision_id=str(published_revision_uuid),
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
                    build_finished_at = datetime.now(timezone.utc)

        except Exception as exc:
            failure_message = _truncate_error(str(exc) or repr(exc))
            async with sessionmaker() as db:
                result = await db.execute(
                    select(PublishedAppPublishJob).where(PublishedAppPublishJob.id == job_uuid).limit(1)
                )
                job = result.scalar_one_or_none()
                if job is None:
                    return {"status": "missing_after_failure", "publish_job_id": job_id}
                job.status = PublishedAppPublishJobStatus.failed
                job.error = failure_message
                job.finished_at = datetime.now(timezone.utc)
                job.diagnostics = [{"message": failure_message}]
                await db.commit()
            logger.error(
                "published app publish failed",
                extra={
                    "publish_job_id": job_id,
                    "app_id": str(app_uuid) if app_uuid else None,
                    "source_revision_id": str(source_revision_uuid) if source_revision_uuid else None,
                    "error": failure_message,
                },
            )
            return {"status": "failed", "publish_job_id": job_id, "error": failure_message}

        async with sessionmaker() as db:
            job_result = await db.execute(
                select(PublishedAppPublishJob).where(PublishedAppPublishJob.id == job_uuid).limit(1)
            )
            job = job_result.scalar_one_or_none()
            if job is None:
                return {"status": "missing_after_success", "publish_job_id": job_id}

            app_result = await db.execute(
                select(PublishedApp).where(PublishedApp.id == job.published_app_id).limit(1)
            )
            app = app_result.scalar_one_or_none()
            if app is None:
                job.status = PublishedAppPublishJobStatus.failed
                job.error = "Published app not found during finalize"
                job.finished_at = datetime.now(timezone.utc)
                job.diagnostics = [{"message": "Published app not found during finalize"}]
                await db.commit()
                return {"status": "failed", "publish_job_id": job_id, "error": "Published app not found during finalize"}

            source_revision_result = await db.execute(
                select(PublishedAppRevision).where(
                    and_(
                        PublishedAppRevision.id == job.source_revision_id,
                        PublishedAppRevision.published_app_id == app.id,
                    )
                ).limit(1)
            )
            source_revision = source_revision_result.scalar_one_or_none()
            if source_revision is None:
                job.status = PublishedAppPublishJobStatus.failed
                job.error = "Source draft revision disappeared before finalize"
                job.finished_at = datetime.now(timezone.utc)
                job.diagnostics = [{"message": "Source draft revision disappeared before finalize"}]
                await db.commit()
                return {
                    "status": "failed",
                    "publish_job_id": job_id,
                    "error": "Source draft revision disappeared before finalize",
                }

            published_revision = await create_app_version(
                db,
                revision_id=published_revision_uuid,
                app=app,
                kind=PublishedAppRevisionKind.published,
                template_key=source_revision.template_key,
                entry_file=source_revision.entry_file,
                files=dict(source_revision.files or {}),
                created_by=job.requested_by,
                source_revision_id=source_revision.id,
                origin_kind="publish_output",
                build_status=PublishedAppRevisionBuildStatus.succeeded,
                build_seq=int(source_revision.build_seq or 0) + 1,
                build_error=None,
                build_started_at=build_started_at,
                build_finished_at=build_finished_at or datetime.now(timezone.utc),
                dist_storage_prefix=dist_storage_prefix,
                dist_manifest=dist_manifest,
                template_runtime=source_revision.template_runtime or "vite_static",
                compiled_bundle=source_revision.compiled_bundle,
            )

            app.current_published_revision_id = published_revision.id
            app.status = PublishedAppStatus.published
            app.published_at = datetime.now(timezone.utc)
            app.published_url = _build_published_url(app.public_id)

            job.status = PublishedAppPublishJobStatus.succeeded
            job.error = None
            job.diagnostics = []
            job.published_revision_id = published_revision.id
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()

        return {
            "status": "succeeded",
            "publish_job_id": job_id,
            "app_id": str(app_uuid) if app_uuid else None,
            "source_revision_id": str(source_revision_uuid) if source_revision_uuid else None,
            "published_revision_id": str(published_revision_uuid),
            "dist_storage_prefix": dist_storage_prefix,
            "app_public_id": public_id,
        }

    return run_async(_run())


@celery_app.task(name="app.workers.tasks.reap_published_app_draft_dev_sessions_task")
def reap_published_app_draft_dev_sessions_task():
    async def _run():
        from app.db.postgres.session import sessionmaker
        from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService

        async with sessionmaker() as db:
            service = PublishedAppDraftDevRuntimeService(db)
            expired = await service.expire_idle_sessions()
            await db.commit()
        return {"status": "ok", "expired_sessions": expired}

    return run_async(_run())


@celery_app.task(name="app.workers.tasks.expire_usage_quota_reservations_task")
def expire_usage_quota_reservations_task():
    async def _run():
        from app.db.postgres.engine import sessionmaker
        from app.services.usage_quota_service import UsageQuotaService

        older_than_minutes = int(os.getenv("QUOTA_RESERVATION_EXPIRE_MINUTES", "30"))
        async with sessionmaker() as db:
            service = UsageQuotaService(db)
            released = await service.expire_stale_reservations(older_than_minutes=older_than_minutes)
            await db.commit()
        return {"status": "ok", "expired_reservations": released, "older_than_minutes": older_than_minutes}

    return run_async(_run())


@celery_app.task(name="app.workers.tasks.reconcile_usage_quota_counters_task")
def reconcile_usage_quota_counters_task():
    async def _run():
        from app.db.postgres.engine import sessionmaker
        from app.db.postgres.models.usage_quota import UsageQuotaPolicy, UsageQuotaScopeType
        from app.services.usage_quota_service import UsageQuotaService

        async with sessionmaker() as db:
            service = UsageQuotaService(db)
            result = await db.execute(
                select(UsageQuotaPolicy).where(UsageQuotaPolicy.is_active.is_(True))
            )
            policies = result.scalars().all()
            now_utc = datetime.now(timezone.utc)
            scope_keys: set[tuple[str, str, datetime, datetime]] = set()
            for policy in policies:
                scope_type = (
                    UsageQuotaScopeType.organization
                    if policy.scope_type == UsageQuotaScopeType.organization
                    else UsageQuotaScopeType.user
                )
                scope_id = policy.organization_id if scope_type == UsageQuotaScopeType.organization else policy.user_id
                if scope_id is None:
                    continue
                period_start, period_end = service._month_bounds_utc(
                    tz_name=str(policy.timezone or "UTC"),
                    now_utc=now_utc,
                )
                scope_keys.add((scope_type.value, str(scope_id), period_start, period_end))

            reconciled = 0
            for scope_type_raw, scope_id_raw, period_start, period_end in scope_keys:
                scope_type = UsageQuotaScopeType(scope_type_raw)
                used = await service.reconcile_counter_from_ledger(
                    scope_type=scope_type,
                    scope_id=UUID(scope_id_raw),
                    period_start=period_start,
                    period_end=period_end,
                )
                _ = used
                reconciled += 1
            await db.commit()

        return {"status": "ok", "reconciled_scopes": reconciled}

    return run_async(_run())
