from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.core.runtime_urls import resolve_runtime_api_base_url as _resolve_runtime_api_base_url
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppBuilderConversationTurn,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
)
from app.db.postgres.session import get_db
from app.services.published_app_agent_integration_contract import (
    build_published_app_agent_integration_contract,
)
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_draft_revision_materializer import (
    PublishedAppDraftRevisionMaterializerError,
    PublishedAppDraftRevisionMaterializerService,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError
from app.services.published_app_live_preview import build_live_preview_overlay_workspace_fingerprint
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.services.published_app_templates import TemplateRuntimeContext, build_template_files, get_template, list_templates

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _count_active_coding_runs_for_scope,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _get_draft_dev_session_for_scope,
    _get_active_publish_job_for_app,
    _get_revision,
    _get_revision_for_app,
    _resolve_organization_admin_context,
)
from .published_apps_admin_builder_core import (
    _builder_conversation_to_response,
)
from .published_apps_admin_files import (
    _apply_patch_operations,
    _assert_builder_path_allowed,
    _coerce_files_payload,
    _normalize_builder_path,
    _validate_builder_project_or_raise,
)
from .published_apps_admin_shared import (
    BuilderConversationTurnResponse,
    BuilderStateResponse,
    BuilderValidationResponse,
    CreateBuilderRevisionRequest,
    DraftDevSessionResponse,
    DraftDevSyncRequest,
    PublishedAppRevisionResponse,
    RevisionBuildStatusResponse,
    TemplateResetRequest,
    _app_to_response,
    _draft_dev_session_to_response,
    _revision_build_status_to_response,
    _revision_to_response,
    _template_to_response,
    _validate_template_key,
    router,
)

async def _decorate_draft_dev_session_response(
    *,
    db: AsyncSession,
    request: Request,
    session: PublishedAppDraftDevSession,
    app: PublishedApp,
    actor_id: UUID | None,
    revision_id: UUID | None,
) -> DraftDevSessionResponse:
    active_coding_run_count = await _count_active_coding_runs_for_scope(
        db,
        app_id=app.id,
        user_id=actor_id,
    )

    response = _draft_dev_session_to_response(
        session,
        active_coding_run_count=active_coding_run_count,
    )
    if actor_id is None:
        return response
    preview_url = (response.preview_url or "").strip()
    if not preview_url:
        return response
    if preview_url.startswith("/"):
        preview_url = f"{_resolve_runtime_api_base_url(request)}{preview_url}"

    effective_revision_id = revision_id or session.revision_id
    if effective_revision_id is None:
        return response

    response.preview_url = preview_url
    return response


async def _delete_runtime_file_if_present(
    *,
    runtime_service: PublishedAppDraftDevRuntimeService,
    sandbox_id: str,
    path: str,
    session: PublishedAppDraftDevSession,
    app: PublishedApp,
) -> Dict[str, Any]:
    try:
        return await runtime_service.client.delete_file(
            sandbox_id=sandbox_id,
            path=path,
        )
    except PublishedAppDraftDevRuntimeClientError as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        snapshot_error: str | None = None
        live_files: dict[str, Any] = {}
        revision_token: str | None = None
        try:
            snapshot = await runtime_service.client.snapshot_files(sandbox_id=sandbox_id)
            live_files = dict(snapshot.get("files") or {}) if isinstance(snapshot.get("files"), dict) else {}
            revision_token = str(snapshot.get("revision_token") or "").strip() or None
        except PublishedAppDraftDevRuntimeClientError as snapshot_exc:
            snapshot_error = str(snapshot_exc).strip() or snapshot_exc.__class__.__name__

        if path not in live_files:
            apps_builder_trace(
                "draft_dev.sync.delete_absent_ignored",
                domain="draft_dev.api",
                app_id=str(app.id),
                session_id=str(session.id),
                sandbox_id=sandbox_id,
                path=path,
                delete_error=detail,
                snapshot_error=snapshot_error,
            )
            return {
                "sandbox_id": sandbox_id,
                "path": path,
                "status": "deleted_missing",
                "revision_token": revision_token,
            }

        apps_builder_trace(
            "draft_dev.sync.delete_failed",
            domain="draft_dev.api",
            app_id=str(app.id),
            session_id=str(session.id),
            sandbox_id=sandbox_id,
            path=path,
            delete_error=detail,
            snapshot_error=snapshot_error,
        )
        if snapshot_error:
            detail = f"{detail} (snapshot fallback failed: {snapshot_error})"
        raise HTTPException(
            status_code=502,
            detail=f"Failed to delete live sandbox file `{path}`: {detail}",
        ) from exc


async def _assert_no_active_coding_run_for_scope(
    *,
    db: AsyncSession,
    app_id: UUID,
    user_id: UUID | None,
) -> None:
    active_count = await _count_active_coding_runs_for_scope(
        db,
        app_id=app_id,
        user_id=user_id,
    )
    if active_count <= 0:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "CODING_AGENT_RUN_ACTIVE",
            "message": "Builder edits are locked while a coding-agent run is active for this app.",
            "active_coding_run_count": active_count,
        },
    )


@router.get("/{app_id}/builder/state", response_model=BuilderStateResponse)
async def get_builder_state(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None

    draft = await _get_revision(db, app.current_draft_revision_id)
    published = await _get_revision(db, app.current_published_revision_id)
    draft_dev_session: Optional[PublishedAppDraftDevSession] = None
    if actor_id:
        draft_dev_session = await _get_draft_dev_session_for_scope(
            db,
            app_id=app.id,
            user_id=actor_id,
        )
        if draft_dev_session is not None:
            session_status = str(getattr(draft_dev_session.status, "value", draft_dev_session.status) or "").strip().lower()
            if session_status in {
                PublishedAppDraftDevSessionStatus.starting.value,
                PublishedAppDraftDevSessionStatus.building.value,
                PublishedAppDraftDevSessionStatus.serving.value,
                PublishedAppDraftDevSessionStatus.degraded.value,
                PublishedAppDraftDevSessionStatus.running.value,
                PublishedAppDraftDevSessionStatus.stopping.value,
            }:
                runtime_service = PublishedAppDraftDevRuntimeService(db)
                try:
                    draft_dev_session = await runtime_service.heartbeat_session(session=draft_dev_session)
                    await db.commit()
                    await db.refresh(app)
                    draft = await _get_revision(db, app.current_draft_revision_id)
                    published = await _get_revision(db, app.current_published_revision_id)
                    apps_builder_trace(
                        "builder.state.draft_dev_refreshed",
                        domain="draft_dev.api",
                        app_id=str(app.id),
                        user_id=str(actor_id),
                        session_id=str(draft_dev_session.id),
                        status=str(getattr(draft_dev_session.status, "value", draft_dev_session.status) or ""),
                        sandbox_id=str(draft_dev_session.sandbox_id or "") or None,
                    )
                except PublishedAppDraftDevRuntimeDisabled:
                    apps_builder_trace(
                        "builder.state.draft_dev_refresh_skipped",
                        domain="draft_dev.api",
                        app_id=str(app.id),
                        user_id=str(actor_id),
                        session_id=str(draft_dev_session.id),
                        reason="runtime_disabled",
                    )

    return BuilderStateResponse(
        app=_app_to_response(app),
        templates=[_template_to_response(template) for template in list_templates()],
        current_draft_revision=_revision_to_response(draft) if draft else None,
        current_published_revision=_revision_to_response(published) if published else None,
        draft_dev=(
            await _decorate_draft_dev_session_response(
                db=db,
                request=request,
                session=draft_dev_session,
                app=app,
                actor_id=actor_id,
                revision_id=draft_dev_session.revision_id if draft_dev_session else None,
            )
            if draft_dev_session
            else None
        ),
    )


@router.get("/{app_id}/builder/agent-contract")
async def get_builder_agent_contract(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    try:
        return await build_published_app_agent_integration_contract(db=db, app=app)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{app_id}/builder/revisions/{revision_id}/preview-token")
async def create_revision_preview_token(
    app_id: UUID,
    revision_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, revision_id, request, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "BUILDER_REVISIONS_ENDPOINT_REMOVED",
            "message": "Revision preview-token API was removed. Use /admin/apps/{app_id}/versions/{version_id}.",
        },
    )


@router.post("/{app_id}/builder/revisions", response_model=PublishedAppRevisionResponse)
async def create_builder_revision(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, payload, request, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "BUILDER_REVISIONS_ENDPOINT_REMOVED",
            "message": "Builder revisions API was removed. Use /admin/apps/{app_id}/builder/draft-dev/session/sync.",
        },
    )


@router.get(
    "/{app_id}/builder/draft-dev/session",
    response_model=DraftDevSessionResponse,
)
async def get_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    await runtime_service.expire_idle_sessions(app_id=app.id, user_id=actor.id)
    session = await _get_draft_dev_session_for_scope(
        db,
        app_id=app.id,
        user_id=actor.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    await db.commit()
    return await _decorate_draft_dev_session_response(
        db=db,
        request=request,
        session=session,
        app=app,
        actor_id=actor.id,
        revision_id=session.revision_id,
    )


@router.post(
    "/{app_id}/builder/draft-dev/session/ensure",
    response_model=DraftDevSessionResponse,
)
async def ensure_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    await _assert_no_active_coding_run_for_scope(db=db, app_id=app_id, user_id=actor.id)

    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    draft = await _ensure_current_draft_revision(db, app, actor.id)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.ensure_active_session(
            app=app,
            revision=draft,
            user_id=actor.id,
            prefer_live_workspace=True,
            trace_source="builder.ensure_route",
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    return await _decorate_draft_dev_session_response(
        db=db,
        request=request,
        session=session,
        app=app,
        actor_id=actor.id,
        revision_id=draft.id,
    )


@router.patch(
    "/{app_id}/builder/draft-dev/session/sync",
    response_model=DraftDevSessionResponse,
)
async def sync_builder_draft_dev_session(
    app_id: UUID,
    payload: DraftDevSyncRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")

    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    await _assert_no_active_coding_run_for_scope(db=db, app_id=app.id, user_id=actor.id)
    draft = await _ensure_current_draft_revision(db, app, actor.id)

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    runtime_context = TemplateRuntimeContext(
        app_id=str(app.id),
        app_public_id=str(app.public_id or ""),
        agent_id=str(app.agent_id or ""),
    )

    if payload.operations:
        sandbox_id = str(session.sandbox_id or "").strip()
        if not sandbox_id:
            raise HTTPException(status_code=409, detail="Draft dev session sandbox is unavailable")
        revision_token = None
        existing_metadata = dict(session.backend_metadata or {}) if isinstance(session.backend_metadata, dict) else {}
        existing_snapshot = (
            dict(existing_metadata.get("live_workspace_snapshot") or {})
            if isinstance(existing_metadata.get("live_workspace_snapshot"), dict)
            else {}
        )
        next_files = {
            str(path): str(content if isinstance(content, str) else str(content))
            for path, content in dict(existing_snapshot.get("files") or draft.files or {}).items()
        }
        next_entry_file = str(existing_snapshot.get("entry_file") or draft.entry_file or "").strip() or draft.entry_file
        next_files, next_entry_file = _apply_patch_operations(
            next_files,
            next_entry_file,
            payload.operations,
        )
        workspace_metadata = (
            dict(existing_metadata.get("workspace") or {})
            if isinstance(existing_metadata.get("workspace"), dict)
            else {}
        )
        workspace_path = str(workspace_metadata.get("live_workspace_path") or "").strip()
        if not workspace_path:
            workspace_path = str(
                await runtime_service.client.resolve_local_workspace_path(sandbox_id=sandbox_id) or ""
            ).strip()
        if not workspace_path:
            raise HTTPException(status_code=409, detail="Draft dev session workspace path is unavailable")
        result = await runtime_service.client.sync_workspace_files(
            sandbox_id=sandbox_id,
            workspace_path=workspace_path,
            files=next_files,
        )
        revision_token = str(result.get("revision_token") or "").strip() or revision_token

        workspace_fingerprint = build_live_preview_overlay_workspace_fingerprint(
            entry_file=next_entry_file,
            files=next_files,
            runtime_context=runtime_context,
        )

        await runtime_service.record_workspace_live_snapshot(
            app_id=app.id,
            revision_id=session.revision_id or draft.id,
            entry_file=next_entry_file,
            files=next_files,
            revision_token=revision_token,
            workspace_fingerprint=workspace_fingerprint,
        )
        session = await runtime_service.record_live_workspace_revision_token(
            session=session,
            revision_token=revision_token,
        )
    else:
        files = _coerce_files_payload(payload.files or {})
        entry_file = _normalize_builder_path(payload.entry_file or draft.entry_file)
        _assert_builder_path_allowed(entry_file, field="entry_file")
        _validate_builder_project_or_raise(files, entry_file)
        try:
            session = await runtime_service.sync_session(
                app=app,
                revision=draft,
                user_id=actor.id,
                files=files,
                entry_file=entry_file,
            )
        except PublishedAppDraftDevRuntimeDisabled as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        backend_metadata = dict(session.backend_metadata or {}) if isinstance(session.backend_metadata, dict) else {}
        preview_runtime = (
            dict(backend_metadata.get("preview_runtime") or {})
            if isinstance(backend_metadata.get("preview_runtime"), dict)
            else {}
        )
        workspace_metadata = (
            dict(backend_metadata.get("workspace") or {})
            if isinstance(backend_metadata.get("workspace"), dict)
            else {}
        )
        revision_token = (
            str(preview_runtime.get("workspace_revision_token") or workspace_metadata.get("revision_token") or "").strip()
            or None
        )
        workspace_fingerprint = build_live_preview_overlay_workspace_fingerprint(
            entry_file=entry_file,
            files=files,
            runtime_context=runtime_context,
        )
        await runtime_service.record_workspace_live_snapshot(
            app_id=app.id,
            revision_id=session.revision_id or draft.id,
            entry_file=entry_file,
            files=files,
            revision_token=revision_token,
            workspace_fingerprint=workspace_fingerprint,
        )

    await runtime_service.record_live_workspace_materialization_request(
        app_id=app.id,
        origin_kind="manual_save",
        source_revision_id=draft.id,
        created_by=actor.id,
    )

    await db.commit()
    return await _decorate_draft_dev_session_response(
        db=db,
        request=request,
        session=session,
        app=app,
        actor_id=actor.id,
        revision_id=draft.id,
    )


@router.post(
    "/{app_id}/builder/draft-dev/session/heartbeat",
    response_model=DraftDevSessionResponse,
)
async def heartbeat_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    apps_builder_trace(
        "session.heartbeat.requested",
        domain="draft_dev.api",
        app_id=str(app.id),
        user_id=str(actor.id),
    )
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        apps_builder_trace(
            "session.heartbeat.missing_session",
            domain="draft_dev.api",
            app_id=str(app.id),
            user_id=str(actor.id),
        )
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    active_publish = await _get_active_publish_job_for_app(db, app_id=app.id)
    if active_publish is not None:
        apps_builder_trace(
            "session.heartbeat.publish_locked",
            domain="draft_dev.api",
            app_id=str(app.id),
            user_id=str(actor.id),
            active_publish_job_id=str(active_publish.id),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PUBLISH_ACTIVE_SESSION_LOCKED",
                "active_publish_job_id": str(active_publish.id),
                "message": "Cannot stop the draft preview session while publish is running.",
            },
        )

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.heartbeat_session(session=session)
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    apps_builder_trace(
        "session.heartbeat.completed",
        domain="draft_dev.api",
        app_id=str(app.id),
        user_id=str(actor.id),
        session_id=str(session.id),
        status=str(getattr(session.status, "value", session.status) or ""),
        sandbox_id=str(session.sandbox_id or "") or None,
    )
    return await _decorate_draft_dev_session_response(
        db=db,
        request=request,
        session=session,
        app=app,
        actor_id=actor.id,
        revision_id=session.revision_id,
    )


@router.delete(
    "/{app_id}/builder/draft-dev/session",
    response_model=DraftDevSessionResponse,
)
async def delete_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    await runtime_service.stop_session(
        session=session,
        reason=PublishedAppDraftDevSessionStatus.stopped,
    )
    await db.commit()
    return await _decorate_draft_dev_session_response(
        db=db,
        request=request,
        session=session,
        app=app,
        actor_id=actor.id,
        revision_id=session.revision_id,
    )


@router.get(
    "/{app_id}/builder/revisions/{revision_id}/build",
    response_model=RevisionBuildStatusResponse,
)
async def get_builder_revision_build_status(
    app_id: UUID,
    revision_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, revision_id, request, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "BUILDER_REVISIONS_ENDPOINT_REMOVED",
            "message": "Revision build-status API was removed.",
        },
    )


@router.post(
    "/{app_id}/builder/revisions/{revision_id}/build/retry",
    response_model=RevisionBuildStatusResponse,
)
async def retry_builder_revision_build(
    app_id: UUID,
    revision_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_id, revision_id, request, principal, db)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "BUILDER_REVISIONS_ENDPOINT_REMOVED",
            "message": "Revision build-retry API was removed.",
        },
    )


@router.post("/{app_id}/builder/validate", response_model=BuilderValidationResponse)
async def validate_builder_revision(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None
    current = await _ensure_current_draft_revision(db, app, actor_id)

    if payload.base_revision_id and str(payload.base_revision_id) != str(current.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current.id),
                "latest_updated_at": current.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    if payload.files is not None:
        next_files = _coerce_files_payload(payload.files)
        next_entry = _normalize_builder_path(payload.entry_file or current.entry_file)
        _assert_builder_path_allowed(next_entry, field="entry_file")
    else:
        next_files, next_entry = _apply_patch_operations(
            dict(current.files or {}),
            payload.entry_file or current.entry_file,
            payload.operations,
        )

    diagnostics = _validate_builder_project_or_raise(next_files, next_entry)
    return BuilderValidationResponse(
        ok=True,
        entry_file=next_entry,
        file_count=len(next_files),
        diagnostics=diagnostics,
    )


@router.post("/{app_id}/builder/template-reset", response_model=PublishedAppRevisionResponse)
async def reset_builder_template(
    app_id: UUID,
    payload: TemplateResetRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None
    await _assert_no_active_coding_run_for_scope(db=db, app_id=app.id, user_id=actor_id)
    current = await _ensure_current_draft_revision(db, app, actor_id)

    template_key = _validate_template_key(payload.template_key)
    template = get_template(template_key)
    files = build_template_files(
        template_key,
        runtime_context={
            "app_id": str(app.id),
            "app_public_id": app.public_id,
            "agent_id": str(app.agent_id),
        },
    )
    app.template_key = template_key
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        await runtime_service.sync_session(
            app=app,
            revision=current,
            user_id=actor_id,
            files=files,
            entry_file=template.entry_file,
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    materializer = PublishedAppDraftRevisionMaterializerService(db)
    try:
        result = await materializer.materialize_live_workspace(
            app=app,
            entry_file=template.entry_file,
            source_revision_id=current.id,
            created_by=actor_id,
            origin_kind="template_reset",
        )
    except PublishedAppDraftRevisionMaterializerError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TEMPLATE_RESET_BUILD_FAILED",
                "message": "Template reset could not materialize a durable draft revision from watcher output.",
                "reason": str(exc),
            },
        ) from exc

    await db.commit()
    await db.refresh(result.revision)
    return _revision_to_response(result.revision)


@router.get("/{app_id}/builder/conversations", response_model=List[BuilderConversationTurnResponse])
async def list_builder_conversations(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_organization_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["organization_id"], app_id)

    result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(limit)
    )
    return [_builder_conversation_to_response(turn) for turn in result.scalars().all()]
