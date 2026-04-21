from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    ensure_published_app_principal_access,
    get_current_published_app_principal,
    get_optional_published_app_principal,
)
from app.api.routers.published_apps_host_runtime import _user_payload
from app.api.routers.published_apps_public import (
    PublicAuthExchangeRequest,
    PublicAuthRequest,
    PublicChatStreamRequest,
    RuntimeBootstrapAuthResponse,
    RuntimeBootstrapResponse,
    _upload_published_app_attachments,
    _assert_published,
    _resolve_runtime_api_base_url,
    _stream_chat_for_app,
)
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.published_app_analytics import PublishedAppAnalyticsSurface
from app.db.postgres.session import get_db
from app.services.published_app_analytics_service import PublishedAppAnalyticsService
from app.services.published_app_auth_service import PublishedAppAuthError, PublishedAppAuthService
from app.services.runtime_attachment_service import RuntimeAttachmentOwner
from app.services.runtime_surface import (
    RuntimeEventView,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
    RuntimeThreadOptions,
)
from app.services.thread_detail_service import serialize_thread_summary


router = APIRouter(prefix="/public/external/apps", tags=["published-apps-external-runtime"])


def _build_external_runtime_bootstrap(*, request: Request, app: Any, revision: Any) -> RuntimeBootstrapResponse:
    runtime_api_base = _resolve_runtime_api_base_url(request)
    runtime_api_parsed = urlparse(runtime_api_base)
    api_base_path = runtime_api_parsed.path or ""
    stream_suffix = f"/public/external/apps/{app.public_id}/chat/stream"
    stream_path = f"{api_base_path}{stream_suffix}" if api_base_path else stream_suffix
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        public_id=app.public_id,
        revision_id=str(revision.id),
        mode="published-runtime",
        api_base_path=api_base_path or "/",
        api_base_url=runtime_api_base,
        chat_stream_path=stream_path,
        chat_stream_url=f"{runtime_api_base}{stream_suffix}",
        auth=RuntimeBootstrapAuthResponse(
            enabled=bool(app.auth_enabled),
            providers=list(app.auth_providers or []),
            exchange_enabled=bool(app.external_auth_oidc),
        ),
    )


def _published_app_principal(
    app: Any,
    principal: Optional[Dict[str, Any]],
    *,
    required_scopes: tuple[str, ...] = (),
    require_authenticated: bool = False,
) -> Optional[Dict[str, Any]]:
    return ensure_published_app_principal_access(
        principal,
        app_id=str(app.id),
        required_scopes=required_scopes,
        require_authenticated=require_authenticated,
    )


@router.get("/{app_public_id}/runtime/bootstrap", response_model=RuntimeBootstrapResponse)
async def get_external_runtime_bootstrap(
    app_public_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    matched_principal = _published_app_principal(app, principal, require_authenticated=False)
    revision = await _get_published_ui_revision(db, app)
    response = JSONResponse(_build_external_runtime_bootstrap(request=request, app=app, revision=revision).model_dump())
    await PublishedAppAnalyticsService(db).record_bootstrap(
        request=request,
        response=response,
        app=app,
        surface=PublishedAppAnalyticsSurface.external_runtime,
        app_account_id=UUID(str(matched_principal["app_account_id"])) if matched_principal and matched_principal.get("app_account_id") else None,
        session_id=UUID(str(matched_principal["session_id"])) if matched_principal and matched_principal.get("session_id") else None,
    )
    return response


@router.post("/{app_public_id}/auth/signup")
async def external_signup(
    app_public_id: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_public_id)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    if "password" not in set(app.auth_providers or []):
        raise HTTPException(status_code=400, detail="Password auth is disabled for this app")
    auth_service = PublishedAppAuthService(db)
    try:
        result = await auth_service.signup_with_password(
            app=app,
            email=payload.email.lower(),
            password=payload.password,
            full_name=payload.full_name,
        )
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"token": result.token, "token_type": "bearer", "user": _user_payload(result.account)}


@router.post("/{app_public_id}/auth/login")
async def external_login(
    app_public_id: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_public_id)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    if "password" not in set(app.auth_providers or []):
        raise HTTPException(status_code=400, detail="Password auth is disabled for this app")
    auth_service = PublishedAppAuthService(db)
    try:
        result = await auth_service.login_with_password(
            app=app,
            email=payload.email.lower(),
            password=payload.password,
        )
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"token": result.token, "token_type": "bearer", "user": _user_payload(result.account)}


@router.post("/{app_public_id}/auth/exchange")
async def external_exchange(
    app_public_id: str,
    payload: PublicAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_public_id)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    auth_service = PublishedAppAuthService(db)
    try:
        result = await auth_service.exchange_external_oidc(app=app, token=payload.token)
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"token": result.token, "token_type": "bearer", "user": _user_payload(result.account)}


@router.get("/{app_public_id}/auth/me")
async def external_auth_me(
    app_public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    _published_app_principal(app, principal, required_scopes=("public.auth",), require_authenticated=True)
    return _user_payload(principal["user"])


@router.post("/{app_public_id}/auth/logout")
async def external_auth_logout(
    app_public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    _published_app_principal(app, principal, required_scopes=("public.auth",), require_authenticated=True)
    service = PublishedAppAuthService(db)
    await service.revoke_session(
        session_id=UUID(principal["session_id"]),
        app_account_id=UUID(principal["app_account_id"]),
        app_id=UUID(principal["app_id"]),
    )
    return {"status": "logged_out"}


@router.post("/{app_public_id}/chat/stream")
async def external_chat_stream(
    app_public_id: str,
    payload: PublicChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    matched_principal = _published_app_principal(
        app,
        principal,
        required_scopes=("public.chat",) if app.auth_enabled else (),
        require_authenticated=False,
    )
    return await _stream_chat_for_app(
        app=app,
        payload=payload,
        db=db,
        principal=matched_principal,
        enforce_app_auth=bool(app.auth_enabled),
        allow_chat_persistence=True,
        request_user_id=str(matched_principal["app_account_id"]) if matched_principal else None,
        cleanup_transient_thread=not bool(app.auth_enabled),
    )


@router.post("/{app_public_id}/attachments/upload")
async def external_upload_attachments(
    app_public_id: str,
    files: list[UploadFile] = File(...),
    thread_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    matched_principal = _published_app_principal(
        app,
        principal,
        required_scopes=("public.chat",) if app.auth_enabled else (),
        require_authenticated=False,
    )
    if app.auth_enabled and matched_principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    owner = RuntimeAttachmentOwner(
        organization_id=app.organization_id,
        surface=AgentThreadSurface.published_host_runtime,
        app_account_id=UUID(str(matched_principal["app_account_id"])) if matched_principal else None,
        published_app_id=app.id,
        thread_id=thread_id,
    )
    return await _upload_published_app_attachments(app=app, owner=owner, files=files, db=db)


@router.get("/{app_public_id}/threads")
async def external_list_threads(
    app_public_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    _published_app_principal(app, principal, required_scopes=("public.chats.read",), require_authenticated=True)
    threads, total = await RuntimeSurfaceService(db).list_threads(
        scope=RuntimeSurfaceContext(
            organization_id=app.organization_id,
            surface=AgentThreadSurface.published_host_runtime,
            event_view=RuntimeEventView.public_safe,
            app_account_id=UUID(principal["app_account_id"]),
            published_app_id=app.id,
        ).thread_scope(),
        skip=skip,
        limit=limit,
    )
    return {
        "items": [serialize_thread_summary(thread) for thread in threads],
        "total": int(total),
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "pages": ((total + limit - 1) // limit) if limit > 0 else 1,
    }


@router.get("/{app_public_id}/threads/{thread_id}")
async def external_get_thread(
    app_public_id: str,
    thread_id: UUID,
    before_turn_index: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_subthreads: bool = Query(default=False),
    subthread_depth: int = Query(default=1, ge=1, le=5),
    subthread_turn_limit: int | None = Query(default=None, ge=1, le=100),
    subthread_child_limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_public_id)
    _published_app_principal(app, principal, required_scopes=("public.chats.read",), require_authenticated=True)
    return await RuntimeSurfaceService(db).get_thread_detail(
        scope=RuntimeSurfaceContext(
            organization_id=app.organization_id,
            surface=AgentThreadSurface.published_host_runtime,
            event_view=RuntimeEventView.public_safe,
            app_account_id=UUID(principal["app_account_id"]),
            published_app_id=app.id,
        ).thread_scope(),
        thread_id=thread_id,
        options=RuntimeThreadOptions(
            before_turn_index=before_turn_index,
            limit=limit,
            include_subthreads=include_subthreads,
            subthread_depth=subthread_depth,
            subthread_turn_limit=subthread_turn_limit,
            subthread_child_limit=subthread_child_limit,
        ),
        event_view=RuntimeEventView.public_safe,
    )


# Imported late to avoid widening the host-runtime import surface at module import time.
from app.api.routers.published_apps_public import _get_published_ui_revision
