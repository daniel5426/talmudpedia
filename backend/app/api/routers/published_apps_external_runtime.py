from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_published_app_principal,
    get_optional_published_app_principal,
)
from app.api.routers.published_apps_host_runtime import (
    _serialize_thread_detail,
    _serialize_thread_summary,
    _user_payload,
)
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
from app.services.thread_service import ThreadService


router = APIRouter(prefix="/public/external/apps", tags=["published-apps-external-runtime"])


def _build_external_runtime_bootstrap(*, request: Request, app: Any, revision: Any) -> RuntimeBootstrapResponse:
    runtime_api_base = _resolve_runtime_api_base_url(request)
    runtime_api_parsed = urlparse(runtime_api_base)
    api_base_path = runtime_api_parsed.path or ""
    stream_suffix = f"/public/external/apps/{app.slug}/chat/stream"
    stream_path = f"{api_base_path}{stream_suffix}" if api_base_path else stream_suffix
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        slug=app.slug,
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


def _assert_principal_matches_app(app: Any, principal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if principal is None:
        return None
    if str(principal.get("app_id")) != str(app.id):
        raise HTTPException(status_code=403, detail="Token does not belong to this app")
    return principal


@router.get("/{app_slug}/runtime/bootstrap", response_model=RuntimeBootstrapResponse)
async def get_external_runtime_bootstrap(
    app_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    matched_principal = _assert_principal_matches_app(app, principal)
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


@router.post("/{app_slug}/auth/signup")
async def external_signup(
    app_slug: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
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


@router.post("/{app_slug}/auth/login")
async def external_login(
    app_slug: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
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


@router.post("/{app_slug}/auth/exchange")
async def external_exchange(
    app_slug: str,
    payload: PublicAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    auth_service = PublishedAppAuthService(db)
    try:
        result = await auth_service.exchange_external_oidc(app=app, token=payload.token)
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"token": result.token, "token_type": "bearer", "user": _user_payload(result.account)}


@router.get("/{app_slug}/auth/me")
async def external_auth_me(
    app_slug: str,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    _assert_principal_matches_app(app, principal)
    return _user_payload(principal["user"])


@router.post("/{app_slug}/auth/logout")
async def external_auth_logout(
    app_slug: str,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    _assert_principal_matches_app(app, principal)
    service = PublishedAppAuthService(db)
    await service.revoke_session(
        session_id=UUID(principal["session_id"]),
        app_account_id=UUID(principal["app_account_id"]),
        app_id=UUID(principal["app_id"]),
    )
    return {"status": "logged_out"}


@router.post("/{app_slug}/chat/stream")
async def external_chat_stream(
    app_slug: str,
    payload: PublicChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    matched_principal = _assert_principal_matches_app(app, principal)
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


@router.post("/{app_slug}/attachments/upload")
async def external_upload_attachments(
    app_slug: str,
    files: list[UploadFile] = File(...),
    thread_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    matched_principal = _assert_principal_matches_app(app, principal)
    if app.auth_enabled and matched_principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    owner = RuntimeAttachmentOwner(
        tenant_id=app.tenant_id,
        surface=AgentThreadSurface.published_host_runtime,
        app_account_id=UUID(str(matched_principal["app_account_id"])) if matched_principal else None,
        published_app_id=app.id,
        thread_id=thread_id,
    )
    return await _upload_published_app_attachments(app=app, owner=owner, files=files, db=db)


@router.get("/{app_slug}/threads")
async def external_list_threads(
    app_slug: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    _assert_principal_matches_app(app, principal)
    service = ThreadService(db)
    threads, total = await service.list_threads(
        tenant_id=app.tenant_id,
        app_account_id=UUID(principal["app_account_id"]),
        published_app_id=app.id,
        skip=skip,
        limit=limit,
    )
    return {
        "items": [_serialize_thread_summary(thread) for thread in threads],
        "total": int(total),
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "pages": ((total + limit - 1) // limit) if limit > 0 else 1,
    }


@router.get("/{app_slug}/threads/{thread_id}")
async def external_get_thread(
    app_slug: str,
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    app = await _assert_published(db, app_slug)
    _assert_principal_matches_app(app, principal)
    service = ThreadService(db)
    repaired = await service.repair_thread_turn_indices(thread_id=thread_id)
    if repaired:
        await db.commit()
    thread = await service.get_thread_with_turns(
        tenant_id=app.tenant_id,
        thread_id=thread_id,
        app_account_id=UUID(principal["app_account_id"]),
        published_app_id=app.id,
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _serialize_thread_detail(thread)


# Imported late to avoid widening the host-runtime import surface at module import time.
from app.api.routers.published_apps_public import _get_published_ui_revision
