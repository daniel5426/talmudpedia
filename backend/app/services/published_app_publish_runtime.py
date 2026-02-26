from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import tarfile
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, select

from app.api.routers.published_apps_admin_shared import _build_published_url
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppStatus,
)
from app.db.postgres.session import sessionmaker
from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
from app.services.published_app_bundle_storage import PublishedAppBundleStorage
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientError,
)
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay


logger = logging.getLogger(__name__)

_RUNNING_SANDBOX_PUBLISH_TASKS: set[asyncio.Task[Any]] = set()
_NPM_INSTALL_COMMAND = ["npm", "install", "--no-audit", "--no-fund"]
_NPM_CI_COMMAND = ["npm", "ci"]


@dataclass(frozen=True)
class _PublishSnapshot:
    files: Dict[str, str]
    publish_workspace_path: str
    live_workspace_path: str
    revision_token: str | None


def sandbox_publish_enabled() -> bool:
    raw = (os.getenv("APPS_PUBLISH_USE_SANDBOX_BUILD") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def dispatch_sandbox_publish_job(*, job_id: UUID | str) -> Optional[str]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        return f"No running event loop is available for sandbox publish dispatch: {exc}"

    async def _runner() -> None:
        try:
            await run_sandbox_publish_job(job_id=str(job_id))
        except Exception:
            logger.exception("sandbox publish job crashed", extra={"publish_job_id": str(job_id)})

    task = loop.create_task(_runner())
    _RUNNING_SANDBOX_PUBLISH_TASKS.add(task)
    task.add_done_callback(lambda t: _RUNNING_SANDBOX_PUBLISH_TASKS.discard(t))
    return None


async def run_sandbox_publish_job(*, job_id: str) -> None:
    job_uuid = UUID(str(job_id))
    async with sessionmaker() as db:
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        job, app = await _load_job_and_app_or_fail(db=db, job_id=job_uuid)
        if job is None or app is None:
            return
        if not job.requested_by:
            await _fail_job(db, job, "Sandbox publish requires a user-scoped publish request")
            return

        session = await runtime_service.get_publish_ready_session(app_id=app.id, user_id=job.requested_by)
        if session is None:
            await _fail_job(
                db,
                job,
                "Active draft-dev session is required for publish",
                code="DRAFT_DEV_SESSION_REQUIRED_FOR_PUBLISH",
            )
            return

        await _set_job_running(db, job, stage="snapshot")

    try:
        snapshot = await _prepare_publish_snapshot(job_id=job_uuid)
        checkpoint_revision_id = await _create_checkpoint_from_snapshot(
            job_id=job_uuid,
            snapshot=snapshot,
        )
        await _build_upload_and_finalize(
            job_id=job_uuid,
            snapshot=snapshot,
            checkpoint_revision_id=checkpoint_revision_id,
        )
    except Exception as exc:
        async with sessionmaker() as db:
            result = await db.execute(
                select(PublishedAppPublishJob).where(PublishedAppPublishJob.id == job_uuid).limit(1)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return
            await _fail_job(db, job, _truncate_error(str(exc) or repr(exc)))


async def _load_job_and_app_or_fail(
    *,
    db,
    job_id: UUID,
) -> tuple[PublishedAppPublishJob | None, PublishedApp | None]:
    result = await db.execute(
        select(PublishedAppPublishJob).where(PublishedAppPublishJob.id == job_id).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None, None
    app_result = await db.execute(select(PublishedApp).where(PublishedApp.id == job.published_app_id).limit(1))
    app = app_result.scalar_one_or_none()
    if app is None:
        await _fail_job(db, job, "Published app not found")
        return None, None
    return job, app


async def _prepare_publish_snapshot(*, job_id: UUID) -> _PublishSnapshot:
    async with sessionmaker() as db:
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        job, app = await _load_job_and_app_or_fail(db=db, job_id=job_id)
        if job is None or app is None:
            raise RuntimeError("Publish job or app not found")
        if not job.requested_by:
            raise RuntimeError("Publish job requested_by is required")

        session = await runtime_service.get_publish_ready_session(app_id=app.id, user_id=job.requested_by)
        if session is None:
            raise RuntimeError("Active draft-dev session is required for publish")

        await _heartbeat_publish_scope(db=db, job=job, session=session, runtime_service=runtime_service, stage="snapshot")
        payload = await runtime_service.client.prepare_publish_workspace(sandbox_id=str(session.sandbox_id))
        files = {
            str(path): str(content if isinstance(content, str) else str(content))
            for path, content in dict(payload.get("files") or {}).items()
        }
        publish_workspace_path = str(payload.get("publish_workspace_path") or payload.get("workspace_path") or "").strip()
        live_workspace_path = str(payload.get("live_workspace_path") or "").strip()
        if not publish_workspace_path:
            raise RuntimeError("Sandbox publish workspace path is missing")
        if not isinstance(files, dict):
            raise RuntimeError("Sandbox publish snapshot files are missing")
        return _PublishSnapshot(
            files=files,
            publish_workspace_path=publish_workspace_path,
            live_workspace_path=live_workspace_path,
            revision_token=str(payload.get("revision_token") or "").strip() or None,
        )


async def _create_checkpoint_from_snapshot(*, job_id: UUID, snapshot: _PublishSnapshot) -> UUID:
    async with sessionmaker() as db:
        job, app = await _load_job_and_app_or_fail(db=db, job_id=job_id)
        if job is None or app is None:
            raise RuntimeError("Publish job or app not found")

        current_draft = None
        if app.current_draft_revision_id:
            result = await db.execute(
                select(PublishedAppRevision)
                .where(PublishedAppRevision.id == app.current_draft_revision_id)
                .limit(1)
            )
            current_draft = result.scalar_one_or_none()
        if current_draft is None:
            raise RuntimeError("Current draft revision is required before sandbox publish")

        entry_file = _extract_requested_entry_file(job) or str(current_draft.entry_file or "src/main.tsx")
        revision_store = PublishedAppRevisionStore(db)
        manifest_json, bundle_hash = await revision_store.build_manifest_and_store_blobs(snapshot.files)
        checkpoint = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key or current_draft.template_key or "chat-classic",
            entry_file=entry_file,
            files=dict(snapshot.files),
            manifest_json=manifest_json,
            build_status=PublishedAppRevisionBuildStatus.queued,
            build_seq=int(current_draft.build_seq or 0) + 1,
            build_error=None,
            build_started_at=None,
            build_finished_at=None,
            dist_storage_prefix=None,
            dist_manifest=None,
            template_runtime="vite_static",
            compiled_bundle=None,
            bundle_hash=bundle_hash,
            source_revision_id=current_draft.id,
            created_by=job.requested_by,
        )
        db.add(checkpoint)
        await db.flush()
        app.current_draft_revision_id = checkpoint.id
        job.source_revision_id = checkpoint.id
        job.saved_draft_revision_id = checkpoint.id
        await _set_job_stage(job=job, stage="install")
        await db.commit()
        return checkpoint.id


async def _build_upload_and_finalize(
    *,
    job_id: UUID,
    snapshot: _PublishSnapshot,
    checkpoint_revision_id: UUID,
) -> None:
    published_revision_uuid = uuid4()
    dist_manifest: Optional[Dict[str, Any]] = None
    dist_storage_prefix: Optional[str] = None
    build_started_at = datetime.now(timezone.utc)
    build_finished_at: Optional[datetime] = None

    async with sessionmaker() as db:
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        job, app = await _load_job_and_app_or_fail(db=db, job_id=job_id)
        if job is None or app is None:
            raise RuntimeError("Publish job or app not found")
        if not job.requested_by:
            raise RuntimeError("Publish job requested_by is required")
        session = await runtime_service.get_publish_ready_session(app_id=app.id, user_id=job.requested_by)
        if session is None:
            raise RuntimeError("Active draft-dev session is required for publish")

        current_draft_result = await db.execute(
            select(PublishedAppRevision).where(PublishedAppRevision.id == checkpoint_revision_id).limit(1)
        )
        checkpoint_revision = current_draft_result.scalar_one_or_none()
        if checkpoint_revision is None:
            raise RuntimeError("Publish checkpoint revision was not found")

        build_files = apply_runtime_bootstrap_overlay(
            dict(snapshot.files),
            runtime_context=TemplateRuntimeContext(
                app_id=str(app.id),
                app_slug=str(app.slug or ""),
                agent_id=str(app.agent_id or ""),
            ),
        )
        diagnostics = validate_builder_dependency_policy(build_files)
        if diagnostics:
            raise RuntimeError("; ".join(item.get("message", "Build policy violation") for item in diagnostics))

        await _heartbeat_publish_scope(db=db, job=job, session=session, runtime_service=runtime_service, stage="install")
        await runtime_service.client.sync_workspace_files(
            sandbox_id=str(session.sandbox_id),
            workspace_path=snapshot.publish_workspace_path,
            files=build_files,
        )
        if _publish_mock_mode_enabled():
            dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                tenant_id=str(app.tenant_id),
                app_id=str(app.id),
                revision_id=str(published_revision_uuid),
            )
            dist_manifest = {
                "entry_html": "index.html",
                "assets": [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mock_publish_build": True,
                "source_entry_file": checkpoint_revision.entry_file,
            }
            build_finished_at = datetime.now(timezone.utc)
        else:
            npm_install_timeout = int(os.getenv("APPS_BUILD_NPM_INSTALL_TIMEOUT_SECONDS", "360"))
            npm_build_timeout = int(os.getenv("APPS_BUILD_NPM_BUILD_TIMEOUT_SECONDS", "300"))
            command_max_output = int(os.getenv("APPS_PUBLISH_SANDBOX_MAX_OUTPUT_BYTES", "30000"))

            dependency_prepare = {
                "status": "fallback_required",
                "strategy": "none",
                "reason": "prepare_publish_dependencies_not_attempted",
            }
            try:
                dependency_prepare = await runtime_service.client.prepare_publish_dependencies(
                    sandbox_id=str(session.sandbox_id),
                    workspace_path=snapshot.publish_workspace_path,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                dependency_prepare = {
                    "status": "fallback_required",
                    "strategy": "none",
                    "reason": f"dependency reuse prep failed: {exc}",
                }
                logger.warning(
                    "sandbox publish dependency reuse prep failed; falling back to install",
                    extra={"publish_job_id": str(job_id), "sandbox_id": str(session.sandbox_id)},
                )

            should_install = str(dependency_prepare.get("status") or "").strip().lower() != "reused"
            if should_install:
                install_command = _resolve_npm_install_command(build_files)
                install_result = await runtime_service.client.run_command(
                    sandbox_id=str(session.sandbox_id),
                    command=install_command,
                    timeout_seconds=npm_install_timeout,
                    max_output_bytes=command_max_output,
                    workspace_path=snapshot.publish_workspace_path,
                )
                install_code = _extract_command_exit_code(
                    install_result,
                    command_name=" ".join(install_command),
                )
                if install_code != 0:
                    raise RuntimeError(_format_command_failure(" ".join(install_command), install_result))

            await _heartbeat_publish_scope(db=db, job=job, session=session, runtime_service=runtime_service, stage="build")
            build_result = await runtime_service.client.run_command(
                sandbox_id=str(session.sandbox_id),
                command=["npm", "run", "build"],
                timeout_seconds=npm_build_timeout,
                max_output_bytes=command_max_output,
                workspace_path=snapshot.publish_workspace_path,
            )
            build_code = _extract_command_exit_code(build_result, command_name="npm run build")
            if build_code != 0:
                raise RuntimeError(_format_command_failure("npm run build", build_result))

            dist_workspace = f"{snapshot.publish_workspace_path.rstrip('/')}/dist"
            await _heartbeat_publish_scope(db=db, job=job, session=session, runtime_service=runtime_service, stage="upload")
            archive_response = await runtime_service.client.export_workspace_archive(
                sandbox_id=str(session.sandbox_id),
                workspace_path=dist_workspace,
                format="tar.gz",
            )
            archive_bytes = PublishedAppDraftDevRuntimeClient.decode_archive_payload(archive_response)

            with tempfile.TemporaryDirectory(prefix=f"apps-publish-dist-{str(job_id)[:8]}-") as temp_dir:
                extract_dir = Path(temp_dir) / "dist"
                extract_dir.mkdir(parents=True, exist_ok=True)
                archive_path = Path(temp_dir) / "dist.tar.gz"
                archive_path.write_bytes(archive_bytes)
                with tarfile.open(archive_path, mode="r:gz") as tar:
                    tar.extractall(path=extract_dir)
                dist_root = _normalize_extracted_dist_root(extract_dir)
                if not dist_root.exists() or not dist_root.is_dir():
                    raise RuntimeError("Build succeeded but dist directory was not produced")

                dist_manifest = _build_dist_manifest(dist_root)
                if str(checkpoint_revision.entry_file or "").strip().endswith(".tsx"):
                    dist_manifest["source_entry_file"] = checkpoint_revision.entry_file

                storage = PublishedAppBundleStorage.from_env()
                dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                    tenant_id=str(app.tenant_id),
                    app_id=str(app.id),
                    revision_id=str(published_revision_uuid),
                )
                uploaded = 0
                for file_path in sorted(dist_root.rglob("*")):
                    if not file_path.is_file():
                        continue
                    relative_path = file_path.relative_to(dist_root).as_posix()
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

        await _heartbeat_publish_scope(db=db, job=job, session=session, runtime_service=runtime_service, stage="finalize")
        published_revision = PublishedAppRevision(
            id=published_revision_uuid,
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.published,
            template_key=checkpoint_revision.template_key,
            entry_file=checkpoint_revision.entry_file,
            files=dict(checkpoint_revision.files or {}),
            manifest_json=dict(checkpoint_revision.manifest_json or {}),
            build_status=PublishedAppRevisionBuildStatus.succeeded,
            build_seq=int(checkpoint_revision.build_seq or 0) + 1,
            build_error=None,
            build_started_at=build_started_at,
            build_finished_at=build_finished_at or datetime.now(timezone.utc),
            dist_storage_prefix=dist_storage_prefix,
            dist_manifest=dist_manifest,
            template_runtime=checkpoint_revision.template_runtime or "vite_static",
            compiled_bundle=checkpoint_revision.compiled_bundle,
            bundle_hash=checkpoint_revision.bundle_hash,
            source_revision_id=checkpoint_revision.id,
            created_by=job.requested_by,
        )
        db.add(published_revision)
        await db.flush()

        app.current_published_revision_id = published_revision.id
        app.status = PublishedAppStatus.published
        app.published_at = datetime.now(timezone.utc)
        app.published_url = _build_published_url(app.slug)

        job.status = PublishedAppPublishJobStatus.succeeded
        job.stage = "finalize"
        job.error = None
        job.published_revision_id = published_revision.id
        job.finished_at = datetime.now(timezone.utc)
        job.last_heartbeat_at = datetime.now(timezone.utc)
        await db.commit()


async def _set_job_running(db, job: PublishedAppPublishJob, *, stage: str) -> None:
    now = datetime.now(timezone.utc)
    job.status = PublishedAppPublishJobStatus.running
    job.stage = str(stage or "running")
    job.started_at = now
    job.finished_at = None
    job.error = None
    job.last_heartbeat_at = now
    await db.commit()


async def _set_job_stage(*, job: PublishedAppPublishJob, stage: str) -> None:
    job.stage = str(stage or job.stage or "running")
    job.last_heartbeat_at = datetime.now(timezone.utc)


async def _heartbeat_publish_scope(
    *,
    db,
    job: PublishedAppPublishJob,
    session: PublishedAppDraftDevSession,
    runtime_service: PublishedAppDraftDevRuntimeService,
    stage: str,
) -> None:
    with suppress(Exception):
        await runtime_service.heartbeat_session(session=session)
    await _set_job_stage(job=job, stage=stage)
    await db.commit()


async def _fail_job(
    db,
    job: PublishedAppPublishJob,
    message: str,
    *,
    code: str | None = None,
) -> None:
    text = _truncate_error(message or "Publish failed")
    job.status = PublishedAppPublishJobStatus.failed
    job.error = text
    job.finished_at = datetime.now(timezone.utc)
    job.last_heartbeat_at = datetime.now(timezone.utc)
    diagnostics = [item for item in list(job.diagnostics or []) if isinstance(item, dict)]
    entry: Dict[str, Any] = {"message": text}
    if code:
        entry["code"] = code
    diagnostics.append(entry)
    job.diagnostics = diagnostics
    await db.commit()


def _publish_mock_mode_enabled() -> bool:
    raw = (os.getenv("APPS_PUBLISH_MOCK_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _extract_requested_entry_file(job: PublishedAppPublishJob) -> str | None:
    for item in reversed(list(job.diagnostics or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "") != "publish_request":
            continue
        value = str(item.get("entry_file") or "").strip()
        if value:
            return value
    return None


def _truncate_error(raw: str, *, max_chars: int = 4000) -> str:
    text = str(raw or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def _format_command_failure(name: str, result: Dict[str, Any]) -> str:
    try:
        code = _extract_command_exit_code(result, command_name=name)
    except RuntimeError as exc:
        code = f"invalid ({exc})"
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    detail = stderr or stdout or "Command failed"
    return f"`{name}` failed with exit code {code}\n{detail}"


def _extract_command_exit_code(result: Dict[str, Any], *, command_name: str) -> int:
    if "code" not in result:
        raise RuntimeError(f"{command_name} command result is missing exit code")
    raw_code = result.get("code")
    try:
        return int(raw_code)
    except Exception as exc:
        raise RuntimeError(f"{command_name} command result has invalid exit code: {raw_code!r}") from exc


def _resolve_npm_install_command(files: Dict[str, str]) -> list[str]:
    if isinstance(files.get("package-lock.json"), str):
        return list(_NPM_CI_COMMAND)
    return list(_NPM_INSTALL_COMMAND)


def _build_dist_manifest(dist_dir: Path) -> Dict[str, Any]:
    assets: list[dict[str, Any]] = []
    entry_html = "index.html"
    for file_path in sorted(dist_dir.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(dist_dir).as_posix()
        if relative == "index.html":
            entry_html = "index.html"
        assets.append(
            {
                "path": relative,
                "size": int(file_path.stat().st_size),
                "content_type": mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
            }
        )
    return {
        "entry_html": entry_html,
        "assets": assets,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_extracted_dist_root(extract_dir: Path) -> Path:
    root = extract_dir
    dot_dir = extract_dir / "."
    if dot_dir.exists() and dot_dir.is_dir():
        root = dot_dir
    if not (root / "index.html").exists():
        # tar extraction can place files directly under extract_dir; keep extract_dir as fallback.
        root = extract_dir
    return root
