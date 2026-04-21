from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.api.routers.published_apps_public import (
    PublicAuthExchangeRequest,
    PublicAuthRequest,
    PublicChatStreamRequest,
    RuntimeBootstrapAuthResponse,
    RuntimeBootstrapResponse,
    _upload_published_app_attachments,
    _get_published_ui_revision,
    _inject_runtime_context_into_html,
    _is_enabled,
    _stream_chat_for_app,
)
from app.api.dependencies import ensure_published_app_principal_access
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.core.security import decode_published_app_session_token
from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppAccount,
    PublishedAppAccountStatus,
    PublishedAppRevision,
    PublishedAppSession,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.db.postgres.session import get_db
from app.services.published_app_auth_service import (
    PublishedAppAuthError,
    PublishedAppAuthRateLimitError,
    PublishedAppAuthService,
)
from app.services.published_app_analytics_service import PublishedAppAnalyticsService
from app.db.postgres.models.published_app_analytics import PublishedAppAnalyticsSurface
from app.services.published_app_host_runtime_support import (
    _append_query,
    _normalize_return_to_for_host,
    _request_origin_from_base_url,
    _request_relative_url,
    _public_id_from_host,
)
from app.services.published_app_auth_shell_renderer import render_published_app_auth_shell
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.runtime_surface import (
    RuntimeEventView,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
    RuntimeThreadOptions,
)
from app.services.thread_detail_service import serialize_thread_summary
from app.services.published_app_bundle_storage import (
    PublishedAppBundleAssetNotFound,
    PublishedAppBundleStorage,
    PublishedAppBundleStorageError,
    PublishedAppBundleStorageNotConfigured,
)


router = APIRouter(tags=["published-apps-host-runtime"])

INTERNAL_PREFIX = "/_talmudpedia"
SESSION_COOKIE_NAME = os.getenv("PUBLISHED_APP_SESSION_COOKIE_NAME", "published_app_session").strip() or "published_app_session"
GOOGLE_OAUTH_STATE_COOKIE_NAME = (
    os.getenv("PUBLISHED_APP_GOOGLE_OAUTH_STATE_COOKIE_NAME", "published_app_google_oauth_state").strip()
    or "published_app_google_oauth_state"
)


def _is_app_host_request(request: Request) -> bool:
    return _public_id_from_host(request.headers.get("host")) is not None


def _set_session_cookie(*, response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(*, response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=request.url.scheme == "https",
        samesite="lax",
    )


def _set_google_oauth_state_cookie(*, response: Response, request: Request, nonce: str, cookie_name: str) -> None:
    response.set_cookie(
        key=cookie_name,
        value=nonce,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
        max_age=600,
    )


def _clear_google_oauth_state_cookie(*, response: Response, request: Request, cookie_name: str) -> None:
    response.delete_cookie(
        key=cookie_name,
        path="/",
        secure=request.url.scheme == "https",
        samesite="lax",
    )


def _entry_html_from_revision(revision: PublishedAppRevision) -> str:
    entry_html = "index.html"
    manifest = revision.dist_manifest or {}
    if isinstance(manifest, dict):
        manifest_entry = manifest.get("entry_html")
        if isinstance(manifest_entry, str) and manifest_entry.strip():
            entry_html = manifest_entry.lstrip("/")
    return entry_html


def _build_host_runtime_bootstrap(*, request: Request, app: PublishedApp, revision: PublishedAppRevision) -> RuntimeBootstrapResponse:
    origin = _request_origin_from_base_url(str(request.base_url))
    stream_path = f"{INTERNAL_PREFIX}/chat/stream"
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        public_id=app.public_id,
        revision_id=str(revision.id),
        mode="published-runtime",
        api_base_path="/",
        api_base_url=origin,
        chat_stream_path=stream_path,
        chat_stream_url=f"{origin}{stream_path}",
        auth=RuntimeBootstrapAuthResponse(
            enabled=bool(app.auth_enabled),
            providers=list(app.auth_providers or []),
            exchange_enabled=bool(app.external_auth_oidc),
        ),
    )


async def _read_published_asset_bytes(*, revision: PublishedAppRevision, asset_path: str) -> tuple[bytes, str]:
    dist_prefix = (revision.dist_storage_prefix or "").strip()
    if not dist_prefix:
        raise HTTPException(status_code=404, detail="Published assets are unavailable for this app")
    try:
        storage = PublishedAppBundleStorage.from_env()
        payload, content_type = storage.read_asset_bytes(
            dist_storage_prefix=dist_prefix,
            asset_path=asset_path,
        )
        return payload, content_type
    except PublishedAppBundleAssetNotFound:
        raise HTTPException(status_code=404, detail="Published asset not found")
    except PublishedAppBundleStorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PublishedAppBundleStorageError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load published asset: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def _resolve_app_for_host_or_none(db: AsyncSession, request: Request) -> Optional[PublishedApp]:
    public_id = _public_id_from_host(request.headers.get("host"))
    if not public_id:
        return None
    result = await db.execute(select(PublishedApp).where(PublishedApp.public_id == public_id).limit(1))
    app = result.scalar_one_or_none()
    if app is None:
        return None
    if app.status != PublishedAppStatus.published:
        return None
    visibility_value = app.visibility.value if hasattr(app.visibility, "value") else str(app.visibility or "public")
    if visibility_value == PublishedAppVisibility.private.value:
        return None
    return app


async def _resolve_host_app_or_404(db: AsyncSession, request: Request) -> PublishedApp:
    app = await _resolve_app_for_host_or_none(db, request)
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    return app


async def _resolve_optional_principal_from_cookie(
    *,
    db: AsyncSession,
    request: Request,
    expected_app: Optional[PublishedApp] = None,
) -> tuple[Optional[dict[str, Any]], bool]:
    token = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if not token:
        return None, False
    try:
        payload = decode_published_app_session_token(token)
        session_id = UUID(str(payload["session_id"]))
        app_id = UUID(str(payload["app_id"]))
        app_account_id = UUID(str(payload["app_account_id"]))
    except Exception:
        return None, True

    if expected_app is not None and str(expected_app.id) != str(app_id):
        return None, True

    result = await db.execute(select(PublishedAppSession).where(PublishedAppSession.id == session_id).limit(1))
    session = result.scalar_one_or_none()
    if session is None:
        return None, True
    if str(session.published_app_id) != str(app_id) or str(session.app_account_id) != str(app_account_id):
        return None, True
    if session.revoked_at is not None:
        return None, True
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        return None, True

    app: Optional[PublishedApp] = expected_app
    if app is None:
        app_result = await db.execute(select(PublishedApp).where(PublishedApp.id == app_id).limit(1))
        app = app_result.scalar_one_or_none()
    if app is None:
        return None, True

    account_result = await db.execute(
        select(PublishedAppAccount).where(
            and_(
                PublishedAppAccount.published_app_id == app_id,
                PublishedAppAccount.id == app_account_id,
            )
        ).limit(1)
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        return None, True
    if account.status == PublishedAppAccountStatus.blocked:
        return None, True

    return (
        {
            "type": "published_app_user",
            "organization_id": str(app.organization_id),
            "app_id": str(app.id),
            "app_public_id": app.public_id,
            "session_id": str(session.id),
            "app_account_id": str(account.id),
            "global_user_id": str(account.global_user_id) if account.global_user_id else None,
            "user": account,
            "provider": payload.get("provider", "password"),
            "account_status": account.status.value if hasattr(account.status, "value") else str(account.status),
            "scopes": payload.get("scope", []),
        },
        False,
    )


def _user_payload(account: PublishedAppAccount) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "email": account.email,
        "full_name": account.full_name,
        "avatar": account.avatar,
        "account_status": account.status.value if hasattr(account.status, "value") else str(account.status),
    }


async def _serve_auth_shell_response(
    *,
    request: Request,
    app: PublishedApp,
    stale_cookie: bool = False,
) -> Response:
    action = "signup" if request.query_params.get("auth_mode") == "signup" else "login"
    html_payload = render_published_app_auth_shell(
        app=app,
        return_to=_request_relative_url(request.url.path or "/", request.url.query or ""),
        action=action,
        error_message="Your session expired. Please sign in again." if stale_cookie else None,
    )
    response = Response(content=html_payload, media_type="text/html")
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


async def _serve_published_document_response(
    *,
    request: Request,
    db: AsyncSession,
    app: PublishedApp,
) -> Response:
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if app.auth_enabled and principal is None:
        return await _serve_auth_shell_response(request=request, app=app, stale_cookie=stale_cookie)

    revision = await _get_published_ui_revision(db, app)
    entry_html = _entry_html_from_revision(revision)
    payload, content_type = await _read_published_asset_bytes(revision=revision, asset_path=entry_html)
    if content_type.startswith("text/html"):
        try:
            html_text = payload.decode("utf-8")
            bootstrap = _build_host_runtime_bootstrap(request=request, app=app, revision=revision)
            html_text = _inject_runtime_context_into_html(html_text, bootstrap)
            payload = html_text.encode("utf-8")
        except Exception:
            pass

    response = Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "no-store" if app.auth_enabled else "public, max-age=60"},
    )
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


async def _serve_published_asset_response(
    *,
    request: Request,
    db: AsyncSession,
    app: PublishedApp,
    asset_path: str,
) -> Response:
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if app.auth_enabled and principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response

    revision = await _get_published_ui_revision(db, app)
    normalized_asset_path = (asset_path or "").strip().lstrip("/")
    if not normalized_asset_path:
        normalized_asset_path = _entry_html_from_revision(revision)
    payload, content_type = await _read_published_asset_bytes(revision=revision, asset_path=normalized_asset_path)
    response = Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=60" if app.auth_enabled else "public, max-age=60"},
    )
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


class PublishedAppsHostRuntimeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in {"GET", "HEAD"}:
            return await call_next(request)
        if not _is_app_host_request(request):
            return await call_next(request)
        if request.url.path.startswith(INTERNAL_PREFIX):
            return await call_next(request)

        async with sessionmaker() as db:
            app = await _resolve_app_for_host_or_none(db, request)
            if app is None:
                return JSONResponse(status_code=404, content={"detail": "Published app not found"})
            try:
                if request.url.path.startswith("/assets/"):
                    # Keep the "assets/" prefix because dist manifests and bundle storage
                    # keys are rooted at the dist folder (e.g. "assets/index-*.js").
                    asset_path = request.url.path.lstrip("/")
                    return await _serve_published_asset_response(
                        request=request,
                        db=db,
                        app=app,
                        asset_path=asset_path,
                    )
                return await _serve_published_document_response(request=request, db=db, app=app)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, (dict, list)) else {"detail": exc.detail}
                if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
                    return JSONResponse(status_code=exc.status_code, content=detail)
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def _host_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> tuple[PublishedApp, Optional[dict[str, Any]], bool]:
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    return app, principal, stale_cookie


def _host_runtime_principal(
    app: PublishedApp,
    principal: Optional[dict[str, Any]],
    *,
    required_scopes: tuple[str, ...] = (),
    require_authenticated: bool = True,
) -> Optional[dict[str, Any]]:
    return ensure_published_app_principal_access(
        principal,
        app_id=str(app.id),
        required_scopes=required_scopes,
        require_authenticated=require_authenticated,
    )


@router.get(f"{INTERNAL_PREFIX}/auth/state")
async def host_auth_state(
    request: Request,
    response: Response,
    ctx: tuple[PublishedApp, Optional[dict[str, Any]], bool] = Depends(_host_auth_context),
):
    app, principal, stale_cookie = ctx
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return {
        "authenticated": principal is not None,
        "auth_enabled": bool(app.auth_enabled),
        "providers": list(app.auth_providers or []),
        "app": {
            "id": str(app.id),
            "public_id": app.public_id,
            "name": app.name,
            "description": app.description,
            "logo_url": app.logo_url,
            "auth_template_key": app.auth_template_key or "auth-classic",
        },
        "user": _user_payload(principal["user"]) if principal is not None else None,
    }


@router.post(f"{INTERNAL_PREFIX}/auth/signup")
async def host_signup(
    request: Request,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
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
    response = JSONResponse({"status": "ok", "user": _user_payload(result.account)})
    _set_session_cookie(response=response, request=request, token=result.token)
    return response


@router.post(f"{INTERNAL_PREFIX}/auth/login")
async def host_login(
    request: Request,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
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
            client_ip=request.client.host if request.client else None,
        )
    except PublishedAppAuthRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response = JSONResponse({"status": "ok", "user": _user_payload(result.account)})
    _set_session_cookie(response=response, request=request, token=result.token)
    return response


@router.post(f"{INTERNAL_PREFIX}/auth/exchange")
async def host_exchange_auth_token(
    request: Request,
    payload: PublicAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    auth_service = PublishedAppAuthService(db)
    try:
        result = await auth_service.exchange_external_oidc(app=app, token=payload.token)
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response = JSONResponse({"status": "ok", "user": _user_payload(result.account)})
    _set_session_cookie(response=response, request=request, token=result.token)
    return response


@router.post(f"{INTERNAL_PREFIX}/auth/logout")
async def host_logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is not None:
        _host_runtime_principal(app, principal, required_scopes=("public.auth",), require_authenticated=True)
        service = PublishedAppAuthService(db)
        await service.revoke_session(
            session_id=UUID(principal["session_id"]),
            app_account_id=UUID(principal["app_account_id"]),
            app_id=UUID(principal["app_id"]),
        )
    response = JSONResponse({"status": "logged_out"})
    if principal is not None or stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


@router.get(f"{INTERNAL_PREFIX}/auth/google/start")
async def host_google_start(
    request: Request,
    return_to: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    if not _is_enabled("PUBLISHED_APPS_GOOGLE_AUTH_ENABLED", "1"):
        raise HTTPException(status_code=404, detail="Google auth is disabled")
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    if "google" not in set(app.auth_providers or []):
        raise HTTPException(status_code=400, detail="Google auth is disabled for this app")

    auth_service = PublishedAppAuthService(db)
    credential = await auth_service.get_google_credential(app.organization_id)
    if credential is None:
        raise HTTPException(status_code=400, detail="Organization Google OAuth credentials are missing")

    creds = credential.credentials or {}
    client_id = creds.get("client_id")
    redirect_uri = creds.get("redirect_uri")
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="Google OAuth credentials are incomplete")

    normalized_return = _normalize_return_to_for_host(str(request.base_url), return_to) or "/"
    target_abs = f"{_request_origin_from_base_url(str(request.base_url))}{normalized_return}"
    oauth_state_nonce = secrets.token_urlsafe(32)
    auth_url = auth_service.build_google_auth_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        app_public_id=app.public_id,
        return_to=target_abs,
        nonce=oauth_state_nonce,
    )
    response = RedirectResponse(url=auth_url, status_code=302)
    _set_google_oauth_state_cookie(
        response=response,
        request=request,
        nonce=oauth_state_nonce,
        cookie_name=GOOGLE_OAUTH_STATE_COOKIE_NAME,
    )
    return response


@router.get(f"{INTERNAL_PREFIX}/auth/google/callback")
async def host_google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    auth_service = PublishedAppAuthService(db)
    credential = await auth_service.get_google_credential(app.organization_id)
    if credential is None:
        raise HTTPException(status_code=400, detail="Organization Google OAuth credentials are missing")

    creds = credential.credentials or {}
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    redirect_uri = creds.get("redirect_uri")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=400, detail="Google OAuth credentials are incomplete")

    oauth_state_nonce = (request.cookies.get(GOOGLE_OAUTH_STATE_COOKIE_NAME) or "").strip()
    try:
        state_payload = auth_service.parse_google_state(state, expected_nonce=oauth_state_nonce)
        if state_payload.get("app_public_id") != app.public_id:
            raise PublishedAppAuthError("OAuth state app public id mismatch")
        token_response = auth_service.exchange_google_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        profile = auth_service.verify_google_id_token(
            token_value=token_response["id_token"],
            client_id=client_id,
        )
        account = await auth_service.get_or_create_google_account(
            app=app,
            email=str(profile.get("email", "")).lower(),
            google_id=str(profile.get("sub")),
            full_name=profile.get("name"),
            avatar=profile.get("picture"),
        )
        result = await auth_service.issue_auth_result(
            app=app,
            account=account,
            provider="google",
            metadata={"google_sub": str(profile.get("sub"))},
        )
    except PublishedAppAuthError as exc:
        response = JSONResponse(status_code=400, content={"detail": str(exc)})
        _clear_google_oauth_state_cookie(
            response=response,
            request=request,
            cookie_name=GOOGLE_OAUTH_STATE_COOKIE_NAME,
        )
        return response

    return_to = _normalize_return_to_for_host(str(request.base_url), state_payload.get("return_to"))  # type: ignore[name-defined]
    redirect = RedirectResponse(url=return_to or "/", status_code=302)
    _set_session_cookie(response=redirect, request=request, token=result.token)
    _clear_google_oauth_state_cookie(
        response=redirect,
        request=request,
        cookie_name=GOOGLE_OAUTH_STATE_COOKIE_NAME,
    )
    return redirect


@router.get(f"{INTERNAL_PREFIX}/runtime/bootstrap")
async def host_runtime_bootstrap(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    response: JSONResponse
    if app.auth_enabled and principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        await PublishedAppAnalyticsService(db).record_bootstrap(
            request=request,
            response=response,
            app=app,
            surface=PublishedAppAnalyticsSurface.host_runtime,
        )
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
    revision = await _get_published_ui_revision(db, app)
    bootstrap = _build_host_runtime_bootstrap(request=request, app=app, revision=revision)
    response = JSONResponse(bootstrap.model_dump())
    await PublishedAppAnalyticsService(db).record_bootstrap(
        request=request,
        response=response,
        app=app,
        surface=PublishedAppAnalyticsSurface.host_runtime,
        app_account_id=UUID(str(principal["app_account_id"])) if principal and principal.get("app_account_id") else None,
        session_id=UUID(str(principal["session_id"])) if principal and principal.get("session_id") else None,
    )
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


@router.post(f"{INTERNAL_PREFIX}/chat/stream")
async def host_chat_stream(
    request: Request,
    payload: PublicChatStreamRequest,
    db: AsyncSession = Depends(get_db),
):
    if not _is_enabled("PUBLISHED_APPS_ENABLED", "1"):
        raise HTTPException(status_code=404, detail="Published apps are disabled")
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is not None:
        principal = _host_runtime_principal(
            app,
            principal,
            required_scopes=("public.chat",),
            require_authenticated=True,
        )
    if app.auth_enabled and principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
    stream_response = await _stream_chat_for_app(
        app=app,
        payload=payload,
        db=db,
        principal=principal,
        enforce_app_auth=True,
        allow_chat_persistence=True,
        request_user_id=str(principal["app_account_id"]) if principal else None,
    )
    if stale_cookie:
        _clear_session_cookie(response=stream_response, request=request)
    return stream_response


@router.post(f"{INTERNAL_PREFIX}/attachments/upload")
async def host_upload_attachments(
    request: Request,
    files: list[UploadFile] = File(...),
    thread_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not _is_enabled("PUBLISHED_APPS_ENABLED", "1"):
        raise HTTPException(status_code=404, detail="Published apps are disabled")
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is not None:
        principal = _host_runtime_principal(
            app,
            principal,
            required_scopes=("public.chat",),
            require_authenticated=True,
        )
    if app.auth_enabled and principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response

    owner = RuntimeAttachmentOwner(
        organization_id=app.organization_id,
        project_id=app.project_id,
        surface=AgentThreadSurface.published_host_runtime,
        app_account_id=UUID(str(principal["app_account_id"])) if principal else None,
        published_app_id=app.id,
        thread_id=thread_id,
    )
    payload = await _upload_published_app_attachments(app=app, owner=owner, files=files, db=db)
    response = JSONResponse(payload)
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


@router.get(f"{INTERNAL_PREFIX}/threads")
async def host_list_threads(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
    principal = _host_runtime_principal(app, principal, required_scopes=("public.chats.read",), require_authenticated=True)

    threads, total = await RuntimeSurfaceService(db).list_threads(
        scope=RuntimeSurfaceContext(
            organization_id=app.organization_id,
            project_id=app.project_id,
            surface=AgentThreadSurface.published_host_runtime,
            event_view=RuntimeEventView.public_safe,
            app_account_id=UUID(principal["app_account_id"]),
            published_app_id=app.id,
        ).thread_scope(),
        skip=skip,
        limit=limit,
    )
    payload = {
        "items": [serialize_thread_summary(thread) for thread in threads],
        "total": int(total),
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "pages": ((total + limit - 1) // limit) if limit > 0 else 1,
    }
    response = JSONResponse(jsonable_encoder(payload))
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response


@router.get(f"{INTERNAL_PREFIX}/threads/{{thread_id}}")
async def host_get_thread(
    thread_id: UUID,
    request: Request,
    before_turn_index: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_subthreads: bool = Query(default=False),
    subthread_depth: int = Query(default=1, ge=1, le=5),
    subthread_turn_limit: int | None = Query(default=None, ge=1, le=100),
    subthread_child_limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    app = await _resolve_host_app_or_404(db, request)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
    principal = _host_runtime_principal(app, principal, required_scopes=("public.chats.read",), require_authenticated=True)
    response = JSONResponse(
        jsonable_encoder(
            await RuntimeSurfaceService(db).get_thread_detail(
                scope=RuntimeSurfaceContext(
                    organization_id=app.organization_id,
                    project_id=app.project_id,
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
        )
    )
    if stale_cookie:
        _clear_session_cookie(response=response, request=request)
    return response
