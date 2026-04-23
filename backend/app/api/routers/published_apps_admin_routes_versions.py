from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import (
    PublishedAppStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
)
from app.db.postgres.session import get_db
from app.services.published_app_draft_revision_materializer import (
    PublishedAppDraftRevisionMaterializerError,
    PublishedAppDraftRevisionMaterializerService,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_store import PublishedAppRevisionStore

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _ensure_current_draft_revision,
    _get_active_publish_job_for_app,
    _get_app_for_tenant,
    _get_revision_for_app,
    _resolve_organization_admin_context,
    _validate_agent,
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
from .published_apps_preview_auth import (
    PREVIEW_TARGET_REVISION,
    append_preview_runtime_token,
    create_preview_token,
    set_preview_cookie,
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
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)

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
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, version_id)
    if not app.agent_id:
        raise HTTPException(status_code=409, detail={"code": "APP_AGENT_REQUIRED", "message": "Publish requires an attached agent."})
    agent = await _validate_agent(db, app.organization_id, app.agent_id)
    agent_status = str(getattr(agent.status, "value", agent.status)).strip().lower()
    if agent_status != "published":
        raise HTTPException(status_code=409, detail={"code": "PUBLISH_DEPENDENCY_INCOMPATIBLE", "message": "Publish requires a published agent.", "dependencies": [{"kind": "agent", "id": str(agent.id), "status": agent_status, "reason": "agent_not_published"}]})
    return _revision_to_response(revision)


@router.post("/{app_id}/versions/draft", response_model=PublishedAppRevisionResponse)
async def create_draft_version(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.publish")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, payload, request, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "VERSIONS_DRAFT_ENDPOINT_REMOVED",
            "message": "Manual save moved to /admin/apps/{app_id}/builder/draft-dev/session/sync.",
        },
    )


@router.post("/{app_id}/versions/{version_id}/restore", response_model=PublishedAppRevisionResponse)
async def restore_version(
    app_id: UUID,
    version_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
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
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    if actor_id is not None:
        try:
            await runtime_service.sync_session(
                app=app,
                revision=current,
                user_id=actor_id,
                files=files,
                entry_file=target.entry_file,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            pass

    materializer = PublishedAppDraftRevisionMaterializerService(db)
    try:
        result = await materializer.materialize_live_workspace(
            app=app,
            entry_file=target.entry_file,
            source_revision_id=current.id,
            created_by=actor_id,
            origin_kind="restore",
            restored_from_revision_id=target.id,
        )
    except PublishedAppDraftRevisionMaterializerError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RESTORE_BUILD_FAILED",
                "message": "Selected version could not be restored into a built draft revision.",
                "reason": str(exc),
            },
        ) from exc

    if actor_id is not None:
        await runtime_service.bind_session_to_revision_without_sync(
            app_id=app.id,
            user_id=actor_id,
            revision=result.revision,
        )

    await db.commit()
    await db.refresh(result.revision)
    return _revision_to_response(result.revision)


@router.get("/{app_id}/versions/{version_id}/preview-runtime", response_model=VersionPreviewRuntimeResponse)
async def get_version_preview_runtime(
    app_id: UUID,
    version_id: UUID,
    request: Request,
    response: Response,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, version_id)
    if not app.agent_id:
        raise HTTPException(status_code=409, detail={"code": "APP_AGENT_REQUIRED", "message": "Publish requires an attached agent."})
    agent = await _validate_agent(db, app.organization_id, app.agent_id)
    agent_status = str(getattr(agent.status, "value", agent.status)).strip().lower()
    if agent_status != "published":
        raise HTTPException(status_code=409, detail={"code": "PUBLISH_DEPENDENCY_INCOMPATIBLE", "message": "Publish requires a published agent.", "dependencies": [{"kind": "agent", "id": str(agent.id), "status": agent_status, "reason": "agent_not_published"}]})
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

    runtime_api_base = str(request.base_url).rstrip("/")
    asset_base_url = f"{runtime_api_base}/public/apps/preview/revisions/{revision.id}/assets/"
    entry_html = "index.html"
    manifest = revision.dist_manifest or {}
    if isinstance(manifest, dict):
        manifest_entry = manifest.get("entry_html")
        if isinstance(manifest_entry, str) and manifest_entry.strip():
            entry_html = manifest_entry.lstrip("/")
    preview_token = create_preview_token(
        subject=str(ctx["user"].id if ctx.get("user") else principal.get("user_id") or "preview"),
        organization_id=str(app.organization_id),
        app_id=str(app.id),
        preview_target_type=PREVIEW_TARGET_REVISION,
        preview_target_id=str(revision.id),
        revision_id=str(revision.id),
    )
    set_preview_cookie(response=response, request=request, token=preview_token)
    preview_url = append_preview_runtime_token(f"{asset_base_url}{entry_html}", preview_token)
    return VersionPreviewRuntimeResponse(
        revision_id=str(revision.id),
        preview_url=preview_url,
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
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
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
    if not app.agent_id:
        raise HTTPException(status_code=409, detail={"code": "APP_AGENT_REQUIRED", "message": "Publish requires an attached agent."})
    agent = await _validate_agent(db, app.organization_id, app.agent_id)
    agent_status = str(getattr(agent.status, "value", agent.status)).strip().lower()
    if agent_status != "published":
        raise HTTPException(status_code=409, detail={"code": "PUBLISH_DEPENDENCY_INCOMPATIBLE", "message": "Publish requires a published agent.", "dependencies": [{"kind": "agent", "id": str(agent.id), "status": agent_status, "reason": "agent_not_published"}]})
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
        organization_id=app.organization_id,
        project_id=app.project_id,
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
    app.published_url = _build_published_url(app.public_id)
    await db.commit()
    await db.refresh(publish_job)

    return _publish_job_to_response(publish_job)
