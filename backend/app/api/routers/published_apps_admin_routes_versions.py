from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.core.security import (
    PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES,
    create_published_app_preview_token,
)
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import (
    PublishedAppStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.db.postgres.session import get_db
from app.services.published_app_draft_revision_materializer import (
    PublishedAppDraftRevisionMaterializerError,
    PublishedAppDraftRevisionMaterializerService,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_build_dispatch import (
    enqueue_revision_build,
    mark_revision_build_enqueue_failed,
)
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.services.published_app_versioning import create_app_version

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _count_active_coding_runs_for_scope,
    _ensure_current_draft_revision,
    _get_active_publish_job_for_app,
    _get_app_for_tenant,
    _get_revision_for_app,
    _resolve_tenant_admin_context,
)
from .published_apps_admin_builder_core import _next_build_seq
from .published_apps_admin_files import (
    _apply_patch_operations,
    _assert_builder_path_allowed,
    _coerce_files_payload,
    _normalize_builder_path,
    _validate_builder_project_or_raise,
)
from .published_apps_admin_shared import (
    CreateBuilderRevisionRequest,
    PublishJobResponse,
    PublishedAppRevisionResponse,
    _build_published_url,
    _publish_job_to_response,
    _revision_to_response,
    router,
)


class VersionListItemResponse(PublishedAppRevisionResponse):
    files: Dict[str, str] = Field(default_factory=dict)
    is_current_draft: bool = False
    is_current_published: bool = False
    origin_run_id: Optional[str] = None
    restored_from_revision_id: Optional[str] = None
    run_status: Optional[str] = None
    run_prompt_preview: Optional[str] = None


class VersionPreviewRuntimeResponse(BaseModel):
    revision_id: str
    preview_url: str
    runtime_token: str
    expires_at: datetime

def _revision_has_dist_assets(revision: PublishedAppRevision) -> bool:
    return bool(str(revision.dist_storage_prefix or "").strip()) and bool(revision.dist_manifest)


@router.get("/{app_id}/versions", response_model=List[VersionListItemResponse])
async def list_versions(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    before_version_seq: Optional[int] = Query(default=None, ge=1),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    stmt = (
        select(PublishedAppRevision)
        .where(PublishedAppRevision.published_app_id == app.id)
        .order_by(PublishedAppRevision.version_seq.desc(), PublishedAppRevision.created_at.desc())
        .limit(limit)
    )
    if before_version_seq is not None:
        stmt = stmt.where(PublishedAppRevision.version_seq < int(before_version_seq))

    rows = list((await db.execute(stmt)).scalars().all())
    run_ids = [row.origin_run_id for row in rows if row.origin_run_id is not None]
    runs_by_id: dict[str, AgentRun] = {}
    if run_ids:
        run_rows = list((await db.execute(select(AgentRun).where(AgentRun.id.in_(run_ids)))).scalars().all())
        runs_by_id = {str(item.id): item for item in run_rows}

    payload: list[VersionListItemResponse] = []
    for row in rows:
        base_payload = _revision_to_response(row).model_dump()
        base_payload["files"] = {}
        run = runs_by_id.get(str(row.origin_run_id)) if row.origin_run_id else None
        run_status = None
        run_prompt_preview = None
        if run is not None:
            run_status = run.status.value if hasattr(run.status, "value") else str(run.status)
            input_params = run.input_params if isinstance(run.input_params, dict) else {}
            text = str(input_params.get("input") or "").strip()
            if text:
                run_prompt_preview = text[:140]

        payload.append(
            VersionListItemResponse(
                **base_payload,
                is_current_draft=str(app.current_draft_revision_id or "") == str(row.id),
                is_current_published=str(app.current_published_revision_id or "") == str(row.id),
                run_status=run_status,
                run_prompt_preview=run_prompt_preview,
            )
        )
    return payload


@router.get("/{app_id}/versions/{version_id}", response_model=PublishedAppRevisionResponse)
async def get_version(
    app_id: UUID,
    version_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, version_id)
    return _revision_to_response(revision)


@router.post("/{app_id}/versions/draft", response_model=PublishedAppRevisionResponse)
async def create_draft_version(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Manual save requires a user principal")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    active_count = await _count_active_coding_runs_for_scope(
        db,
        app_id=app.id,
        user_id=actor.id,
    )
    if active_count > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CODING_AGENT_RUN_ACTIVE",
                "message": "Builder edits are locked while a coding-agent run is active for this app.",
                "active_coding_run_count": active_count,
            },
        )
    current = await _ensure_current_draft_revision(db, app, actor.id)

    files = _coerce_files_payload(payload.files if payload.files is not None else dict(current.files or {}))
    entry_file = _normalize_builder_path(payload.entry_file or current.entry_file)
    _assert_builder_path_allowed(entry_file, field="entry_file")
    _validate_builder_project_or_raise(files, entry_file)

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        await runtime_service.sync_session(
            app=app,
            revision=current,
            user_id=actor.id,
            files=files,
            entry_file=entry_file,
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    materializer = PublishedAppDraftRevisionMaterializerService(db)
    try:
        result = await materializer.materialize_live_workspace(
            app=app,
            entry_file=entry_file,
            source_revision_id=current.id,
            created_by=actor.id,
            origin_kind="manual_edit",
        )
    except PublishedAppDraftRevisionMaterializerError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MANUAL_SAVE_BUILD_FAILED",
                "message": "Manual save could not materialize a draft version from the current workspace.",
                "reason": str(exc),
            },
        ) from exc

    await runtime_service.bind_session_to_revision_without_sync(
        app_id=app.id,
        user_id=actor.id,
        revision=result.revision,
    )
    await db.commit()
    await db.refresh(result.revision)
    return _revision_to_response(result.revision)


@router.post("/{app_id}/versions/{version_id}/restore", response_model=PublishedAppRevisionResponse)
async def restore_version(
    app_id: UUID,
    version_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    target = await _get_revision_for_app(db, app.id, version_id)
    current = await _ensure_current_draft_revision(db, app, actor_id)

    revision_store = PublishedAppRevisionStore(db)
    try:
        files = await revision_store.materialize_revision_files(target)
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "VERSION_SOURCE_UNAVAILABLE",
                "version_id": str(target.id),
                "message": "Selected version files are unavailable and cannot be restored.",
                "reason": str(exc),
            },
        ) from exc
    restored = await create_app_version(
        db,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=target.template_key,
        entry_file=target.entry_file,
        files=files,
        created_by=actor_id,
        source_revision_id=current.id,
        origin_kind="restore",
        restored_from_revision_id=target.id,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        template_runtime=target.template_runtime or "vite_static",
    )
    app.current_draft_revision_id = restored.id

    if actor_id is not None:
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        try:
            await runtime_service.sync_session(
                app=app,
                revision=restored,
                user_id=actor_id,
                files=dict(restored.files or {}),
                entry_file=restored.entry_file,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            pass

    await db.commit()
    await db.refresh(restored)
    return _revision_to_response(restored)


@router.get("/{app_id}/versions/{version_id}/preview-runtime", response_model=VersionPreviewRuntimeResponse)
async def get_version_preview_runtime(
    app_id: UUID,
    version_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, version_id)
    if not _revision_has_dist_assets(revision):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "VERSION_BUILD_NOT_READY",
                "version_id": str(revision.id),
                "build_status": revision.build_status.value if hasattr(revision.build_status, "value") else str(revision.build_status),
                "build_error": revision.build_error,
                "message": "Selected version preview is unavailable until build artifacts are ready.",
            },
        )

    preview_subject = str(ctx.get("user").id) if ctx.get("user") else str(ctx.get("membership").user_id)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES)
    runtime_token = create_published_app_preview_token(
        subject=preview_subject,
        tenant_id=str(app.tenant_id),
        app_id=str(app.id),
        revision_id=str(revision.id),
        scopes=["apps.preview"],
        expires_delta=timedelta(minutes=PUBLISHED_APP_PREVIEW_TOKEN_EXPIRE_MINUTES),
    )

    runtime_api_base = str(request.base_url).rstrip("/")
    asset_base_url = f"{runtime_api_base}/public/apps/preview/revisions/{revision.id}/assets/"
    entry_html = "index.html"
    manifest = revision.dist_manifest or {}
    if isinstance(manifest, dict):
        manifest_entry = manifest.get("entry_html")
        if isinstance(manifest_entry, str) and manifest_entry.strip():
            entry_html = manifest_entry.lstrip("/")
    preview_url = f"{asset_base_url}{entry_html}"
    return VersionPreviewRuntimeResponse(
        revision_id=str(revision.id),
        preview_url=preview_url,
        runtime_token=runtime_token,
        expires_at=expires_at,
    )


@router.post("/{app_id}/versions/{version_id}/publish", response_model=PublishJobResponse)
async def publish_version(
    app_id: UUID,
    version_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx.get("user") else None
    if actor_id is None:
        raise HTTPException(status_code=403, detail="Publish requires a user principal")

    active_publish = await _get_active_publish_job_for_app(db, app_id=app.id)
    if active_publish is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PUBLISH_JOB_ACTIVE",
                "active_publish_job_id": str(active_publish.id),
                "message": "A publish job is already running for this app.",
            },
        )

    revision = await _get_revision_for_app(db, app.id, version_id)
    if not _revision_has_dist_assets(revision):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_NOT_MATERIALIZED",
                "message": "Publish requires a materialized revision with durable build output.",
                "version_id": str(revision.id),
            },
        )

    now = datetime.now(timezone.utc)
    publish_job = PublishedAppPublishJob(
        published_app_id=app.id,
        tenant_id=app.tenant_id,
        requested_by=actor_id,
        source_revision_id=revision.id,
        saved_draft_revision_id=revision.id,
        published_revision_id=revision.id,
        status=PublishedAppPublishJobStatus.succeeded,
        stage="completed",
        error=None,
        diagnostics=[
            {
                "kind": "revision_publish",
                "version_id": str(revision.id),
                "pointer_only": "true",
            }
        ],
        last_heartbeat_at=now,
        started_at=now,
        finished_at=now,
    )
    db.add(publish_job)
    await db.flush()
    app.current_published_revision_id = revision.id
    app.status = PublishedAppStatus.published
    app.published_at = now
    app.published_url = _build_published_url(app.slug)
    await db.commit()
    await db.refresh(publish_job)

    return _publish_job_to_response(publish_job)
