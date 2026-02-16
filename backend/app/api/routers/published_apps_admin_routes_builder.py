import json
from hashlib import sha256
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.core.security import create_published_app_preview_token
from app.db.postgres.models.published_apps import (
    BuilderCheckpointType,
    BuilderConversationTurnStatus,
    PublishedAppBuilderConversationTurn,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.db.postgres.session import get_db
from app.services.published_app_draft_dev_runtime import (
    PublishedAppDraftDevRuntimeDisabled,
    PublishedAppDraftDevRuntimeService,
)
from app.services.published_app_templates import build_template_files, get_template, list_templates

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _get_draft_dev_session_for_scope,
    _get_revision,
    _get_revision_for_app,
    _resolve_tenant_admin_context,
)
from .published_apps_admin_builder_core import (
    _builder_conversation_to_response,
    _builder_chat_sandbox_tools_enabled,
    _builder_checkpoint_to_response,
    _mark_revision_build_enqueue_failed,
    _next_build_seq,
    _persist_builder_conversation_turn,
    _enqueue_revision_build,
    _new_builder_request_id,
)
from .published_apps_admin_builder_patch import (
    _apply_patch_operations,
    _assert_builder_path_allowed,
    _coerce_files_payload,
    _normalize_builder_path,
    _validate_builder_project_or_raise,
)
from .published_apps_admin_builder_tools import _create_draft_revision_from_files
from .published_apps_admin_shared import (
    BUILDER_CHECKPOINT_LIST_LIMIT,
    BuilderCheckpointResponse,
    BuilderConversationTurnResponse,
    BuilderRevertFileRequest,
    BuilderRevertFileResponse,
    BuilderStateResponse,
    BuilderUndoRequest,
    BuilderUndoResponse,
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

@router.get("/{app_id}/builder/state", response_model=BuilderStateResponse)
async def get_builder_state(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None

    draft = await _ensure_current_draft_revision(db, app, actor_id)
    published = await _get_revision(db, app.current_published_revision_id)
    draft_dev_session: Optional[PublishedAppDraftDevSession] = None
    if actor_id:
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        await runtime_service.expire_idle_sessions(app_id=app.id, user_id=actor_id)
        draft_dev_session = await _get_draft_dev_session_for_scope(
            db,
            app_id=app.id,
            user_id=actor_id,
        )
    await db.commit()
    await db.refresh(app)

    preview_token: Optional[str] = None
    if actor_id and draft:
        preview_token = create_published_app_preview_token(
            subject=str(actor_id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            revision_id=str(draft.id),
            scopes=["apps.preview"],
        )

    return BuilderStateResponse(
        app=_app_to_response(app),
        templates=[_template_to_response(template) for template in list_templates()],
        current_draft_revision=_revision_to_response(draft) if draft else None,
        current_published_revision=_revision_to_response(published) if published else None,
        preview_token=preview_token,
        draft_dev=_draft_dev_session_to_response(draft_dev_session) if draft_dev_session else None,
    )


@router.post("/{app_id}/builder/revisions/{revision_id}/preview-token")
async def create_revision_preview_token(
    app_id: UUID,
    revision_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, revision_id)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Preview token issuance requires a user principal")
    token = create_published_app_preview_token(
        subject=str(actor.id),
        tenant_id=str(app.tenant_id),
        app_id=str(app.id),
        revision_id=str(revision.id),
        scopes=["apps.preview"],
    )
    return {"revision_id": str(revision.id), "preview_token": token}


@router.post("/{app_id}/builder/revisions", response_model=PublishedAppRevisionResponse)
async def create_builder_revision(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
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
        _validate_builder_project_or_raise(next_files, next_entry)
    else:
        next_files, next_entry = _apply_patch_operations(
            dict(current.files or {}),
            payload.entry_file or current.entry_file,
            payload.operations,
        )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=next_entry,
        files=next_files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(next_files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()

    app.current_draft_revision_id = revision.id
    await db.commit()
    await db.refresh(app)
    await db.refresh(revision)
    return _revision_to_response(revision)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
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
    return _draft_dev_session_to_response(session)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    draft = await _ensure_current_draft_revision(db, app, actor.id)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.ensure_session(
            app=app,
            revision=draft,
            user_id=actor.id,
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    return _draft_dev_session_to_response(session)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    draft = await _ensure_current_draft_revision(db, app, actor.id)
    files = _coerce_files_payload(payload.files)
    entry_file = _normalize_builder_path(payload.entry_file or draft.entry_file)
    _assert_builder_path_allowed(entry_file, field="entry_file")
    _validate_builder_project_or_raise(files, entry_file)

    runtime_service = PublishedAppDraftDevRuntimeService(db)
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

    await db.commit()
    return _draft_dev_session_to_response(session)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.heartbeat_session(session=session)
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    return _draft_dev_session_to_response(session)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    await runtime_service.stop_session(
        session=session,
        reason=PublishedAppDraftDevSessionStatus.stopped,
    )
    await db.commit()
    return _draft_dev_session_to_response(session)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, revision_id)
    return _revision_build_status_to_response(revision)


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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, revision_id)

    revision.build_status = PublishedAppRevisionBuildStatus.queued
    revision.build_seq = int(revision.build_seq or 0) + 1
    revision.build_error = None
    revision.build_started_at = None
    revision.build_finished_at = None
    revision.dist_storage_prefix = None
    revision.dist_manifest = None
    revision.template_runtime = revision.template_runtime or "vite_static"
    enqueue_error = _enqueue_revision_build(
        revision=revision,
        app=app,
        build_kind=revision.kind.value if hasattr(revision.kind, "value") else str(revision.kind),
    )
    if enqueue_error:
        _mark_revision_build_enqueue_failed(revision=revision, reason=enqueue_error)
    await db.commit()
    await db.refresh(revision)
    return _revision_build_status_to_response(revision)


@router.post("/{app_id}/builder/validate", response_model=BuilderValidationResponse)
async def validate_builder_revision(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
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
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None
    current = await _ensure_current_draft_revision(db, app, actor_id)

    template_key = _validate_template_key(payload.template_key)
    template = get_template(template_key)
    files = build_template_files(template_key)
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=template_key,
        entry_file=template.entry_file,
        files=files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()

    app.template_key = template_key
    app.current_draft_revision_id = revision.id

    await db.commit()
    await db.refresh(revision)
    return _revision_to_response(revision)


@router.get("/{app_id}/builder/conversations", response_model=List[BuilderConversationTurnResponse])
async def list_builder_conversations(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(limit)
    )
    return [_builder_conversation_to_response(turn) for turn in result.scalars().all()]


@router.get("/{app_id}/builder/checkpoints", response_model=List[BuilderCheckpointResponse])
async def list_builder_checkpoints(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    fetch_limit = min(max(1, limit), BUILDER_CHECKPOINT_LIST_LIMIT)
    result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .where(PublishedAppBuilderConversationTurn.status == BuilderConversationTurnStatus.succeeded)
        .where(PublishedAppBuilderConversationTurn.result_revision_id.is_not(None))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(fetch_limit)
    )
    turns = result.scalars().all()
    checkpoints: List[BuilderCheckpointResponse] = []
    for turn in turns:
        if turn.result_revision_id:
            checkpoints.append(_builder_checkpoint_to_response(turn))
    return checkpoints


@router.post("/{app_id}/builder/undo", response_model=BuilderUndoResponse)
async def undo_builder_last_run(
    app_id: UUID,
    payload: BuilderUndoRequest,
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

    turn_result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .where(PublishedAppBuilderConversationTurn.status == BuilderConversationTurnStatus.succeeded)
        .where(PublishedAppBuilderConversationTurn.checkpoint_type == BuilderCheckpointType.auto_run)
        .where(PublishedAppBuilderConversationTurn.result_revision_id.is_not(None))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(1)
    )
    checkpoint_turn = turn_result.scalar_one_or_none()
    if checkpoint_turn is None or checkpoint_turn.result_revision_id is None:
        raise HTTPException(status_code=404, detail="No automatic checkpoint found to undo")

    checkpoint_revision = await _get_revision_for_app(db, app.id, checkpoint_turn.result_revision_id)
    if checkpoint_revision.source_revision_id is None:
        raise HTTPException(status_code=409, detail="Checkpoint has no source revision to restore")
    restore_revision = await _get_revision_for_app(db, app.id, checkpoint_revision.source_revision_id)

    restored_files = dict(restore_revision.files or {})
    restored_entry = restore_revision.entry_file
    new_revision = await _create_draft_revision_from_files(
        db,
        app=app,
        current=current,
        actor_id=actor_id,
        files=restored_files,
        entry_file=restored_entry,
    )

    if actor and _builder_chat_sandbox_tools_enabled():
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        try:
            await runtime_service.sync_session(
                app=app,
                revision=new_revision,
                user_id=actor.id,
                files=restored_files,
                entry_file=restored_entry,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            pass

    request_id = _new_builder_request_id()
    await _persist_builder_conversation_turn(
        db,
        app_id=app.id,
        revision_id=current.id,
        result_revision_id=new_revision.id,
        actor_id=actor_id,
        request_id=request_id,
        user_prompt="Undo last run",
        status=BuilderConversationTurnStatus.succeeded,
        trace_events=[],
        checkpoint_type=BuilderCheckpointType.undo,
        checkpoint_label=f"Undo to {restore_revision.id}",
    )
    await db.commit()
    await db.refresh(new_revision)
    return BuilderUndoResponse(
        revision=_revision_to_response(new_revision),
        restored_from_revision_id=str(restore_revision.id),
        checkpoint_turn_id=str(checkpoint_turn.id),
        request_id=request_id,
    )


@router.post("/{app_id}/builder/revert-file", response_model=BuilderRevertFileResponse)
async def revert_builder_file(
    app_id: UUID,
    payload: BuilderRevertFileRequest,
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

    normalized_path = _normalize_builder_path(payload.path)
    _assert_builder_path_allowed(normalized_path, field="path")
    from_revision = await _get_revision_for_app(db, app.id, payload.from_revision_id)

    next_files = dict(current.files or {})
    if normalized_path in (from_revision.files or {}):
        next_files[normalized_path] = str((from_revision.files or {})[normalized_path])
    else:
        next_files.pop(normalized_path, None)

    next_entry = current.entry_file
    if normalized_path == current.entry_file and normalized_path not in next_files:
        raise HTTPException(status_code=409, detail="Cannot remove the current entry file")

    new_revision = await _create_draft_revision_from_files(
        db,
        app=app,
        current=current,
        actor_id=actor_id,
        files=next_files,
        entry_file=next_entry,
    )

    if actor and _builder_chat_sandbox_tools_enabled():
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        try:
            await runtime_service.sync_session(
                app=app,
                revision=new_revision,
                user_id=actor.id,
                files=next_files,
                entry_file=next_entry,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            pass

    request_id = _new_builder_request_id()
    await _persist_builder_conversation_turn(
        db,
        app_id=app.id,
        revision_id=current.id,
        result_revision_id=new_revision.id,
        actor_id=actor_id,
        request_id=request_id,
        user_prompt=f"Revert file: {normalized_path}",
        status=BuilderConversationTurnStatus.succeeded,
        trace_events=[],
        checkpoint_type=BuilderCheckpointType.file_revert,
        checkpoint_label=f"Revert {normalized_path}",
    )
    await db.commit()
    await db.refresh(new_revision)
    return BuilderRevertFileResponse(
        revision=_revision_to_response(new_revision),
        reverted_path=normalized_path,
        from_revision_id=str(from_revision.id),
        request_id=request_id,
    )
