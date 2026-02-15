from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.db.postgres.session import get_db

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _create_draft_revision_snapshot,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _get_publish_job_for_app,
    _resolve_tenant_admin_context,
    _validate_agent,
)
from .published_apps_admin_builder_core import _enqueue_publish_job, _publish_full_build_enabled
from .published_apps_admin_builder_patch import (
    _assert_builder_path_allowed,
    _coerce_files_payload,
    _normalize_builder_path,
    _validate_builder_project_or_raise,
)
from .published_apps_admin_shared import (
    APP_SLUG_PATTERN,
    PublishJobResponse,
    PublishJobStatusResponse,
    PublishRequest,
    PublishedAppResponse,
    UpdatePublishedAppRequest,
    _app_to_response,
    _build_published_url,
    _publish_job_to_response,
    _validate_auth_template_key,
    _validate_providers,
    _validate_visibility,
    router,
)

@router.patch("/{app_id}", response_model=PublishedAppResponse)
async def update_published_app(
    app_id: UUID,
    payload: UpdatePublishedAppRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    if payload.name is not None:
        app.name = payload.name.strip()
    if payload.description is not None:
        app.description = payload.description.strip() or None
    if payload.logo_url is not None:
        app.logo_url = payload.logo_url.strip() or None
    if payload.slug is not None:
        next_slug = payload.slug.strip().lower()
        if not APP_SLUG_PATTERN.match(next_slug):
            raise HTTPException(status_code=400, detail="Slug must be lowercase, 3-64 chars, and contain only letters, numbers, hyphens")
        app.slug = next_slug
        if app.status == PublishedAppStatus.published:
            app.published_url = _build_published_url(next_slug)
    if payload.agent_id is not None:
        await _validate_agent(db, ctx["tenant_id"], payload.agent_id)
        app.agent_id = payload.agent_id
    if payload.visibility is not None:
        app.visibility = PublishedAppVisibility(_validate_visibility(payload.visibility))
    if payload.auth_enabled is not None:
        app.auth_enabled = payload.auth_enabled
    if payload.auth_providers is not None:
        app.auth_providers = _validate_providers(payload.auth_providers)
    if payload.auth_template_key is not None:
        app.auth_template_key = _validate_auth_template_key(payload.auth_template_key)
    if payload.status is not None:
        try:
            app.status = PublishedAppStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Published app slug or name already exists")
    await db.refresh(app)
    return _app_to_response(app)


@router.post("/{app_id}/publish", response_model=PublishJobResponse)
async def publish_published_app(
    app_id: UUID,
    request: Request,
    payload: Optional[PublishRequest] = None,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if not _publish_full_build_enabled():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PUBLISH_FULL_BUILD_DISABLED",
                "message": "Publish full-build mode is disabled (`APPS_PUBLISH_FULL_BUILD_ENABLED=0`).",
            },
        )

    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    await _validate_agent(db, ctx["tenant_id"], app.agent_id)
    actor_id = ctx["user"].id if ctx["user"] else None

    payload = payload or PublishRequest()
    current_draft = await _ensure_current_draft_revision(db, app, actor_id)
    if payload.base_revision_id and str(payload.base_revision_id) != str(current_draft.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current_draft.id),
                "latest_updated_at": current_draft.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    source_revision = current_draft
    saved_draft_revision_id: Optional[UUID] = None
    if payload.files is not None or payload.entry_file is not None:
        files = _coerce_files_payload(payload.files or dict(current_draft.files or {}))
        next_entry = _normalize_builder_path(payload.entry_file or current_draft.entry_file)
        _assert_builder_path_allowed(next_entry, field="entry_file")
        _validate_builder_project_or_raise(files, next_entry)
        source_revision = await _create_draft_revision_snapshot(
            db=db,
            app=app,
            current=current_draft,
            actor_id=actor_id,
            files=files,
            entry_file=next_entry,
        )
        saved_draft_revision_id = source_revision.id

    publish_job = PublishedAppPublishJob(
        published_app_id=app.id,
        tenant_id=app.tenant_id,
        requested_by=actor_id,
        source_revision_id=source_revision.id,
        saved_draft_revision_id=saved_draft_revision_id,
        published_revision_id=None,
        status=PublishedAppPublishJobStatus.queued,
        error=None,
        diagnostics=[],
        started_at=None,
        finished_at=None,
    )
    db.add(publish_job)
    await db.flush()
    await db.commit()
    await db.refresh(publish_job)

    enqueue_error = _enqueue_publish_job(job=publish_job)
    if enqueue_error:
        publish_job.status = PublishedAppPublishJobStatus.failed
        publish_job.error = enqueue_error
        publish_job.finished_at = datetime.now(timezone.utc)
        publish_job.diagnostics = [{"message": enqueue_error}]
        await db.commit()
        await db.refresh(publish_job)

    return _publish_job_to_response(publish_job)


@router.get("/{app_id}/publish/jobs/{job_id}", response_model=PublishJobStatusResponse)
async def get_publish_job_status(
    app_id: UUID,
    job_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    job = await _get_publish_job_for_app(db, app_id=app.id, job_id=job_id)
    return PublishJobStatusResponse(**_publish_job_to_response(job).model_dump())


@router.post("/{app_id}/unpublish", response_model=PublishedAppResponse)
async def unpublish_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    app.status = PublishedAppStatus.draft
    app.published_url = None
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.delete("/{app_id}")
async def delete_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    await db.delete(app)
    await db.commit()
    return {"status": "deleted", "id": str(app_id)}


@router.get("/{app_id}/runtime-preview")
async def runtime_preview(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    return {
        "app_id": str(app.id),
        "slug": app.slug,
        "status": app.status.value if hasattr(app.status, "value") else str(app.status),
        "runtime_url": app.published_url or _build_published_url(app.slug),
    }
