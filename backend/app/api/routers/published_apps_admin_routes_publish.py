from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSessionStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.db.postgres.session import get_db
from app.services.published_app_draft_dev_runtime import (
    PublishedAppDraftDevRuntimeDisabled,
    PublishedAppDraftDevRuntimeService,
)
from app.services.published_app_publish_runtime import sandbox_publish_enabled

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _count_active_coding_runs_for_scope,
    _create_draft_revision_snapshot,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _get_active_publish_job_for_app,
    _get_draft_dev_session_for_scope,
    _get_publish_job_for_app,
    _resolve_tenant_admin_context,
    _validate_agent,
)
from .published_apps_admin_builder_core import _enqueue_publish_job, _publish_full_build_enabled
from .published_apps_admin_files import (
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
    _validate_allowed_origins,
    _validate_external_auth_oidc,
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
    if payload.allowed_origins is not None:
        app.allowed_origins = _validate_allowed_origins(payload.allowed_origins)
    if payload.external_auth_oidc is not None:
        app.external_auth_oidc = _validate_external_auth_oidc(payload.external_auth_oidc)
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
    _ = (app_id, request, payload, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "PUBLISH_ENDPOINT_REMOVED",
            "message": "Current-head publish endpoint was removed. Use /admin/apps/{app_id}/versions/{version_id}/publish.",
        },
    )


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
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    await runtime_service.destroy_workspace_for_app(app_id=app.id)
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
