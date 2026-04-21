import os
import re
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.api.dependencies import (
    get_current_published_app_preview_principal,
    get_current_published_app_principal,
    get_optional_published_app_principal,
)
from app.core.runtime_urls import (
    build_published_app_url,
    resolve_runtime_api_base_url as _resolve_runtime_api_base_url,
)
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.agent_threads import AgentThreadSurface, AgentThreadTurn
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.db.postgres.session import get_db
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.runtime_surface import (
    RuntimeChatRequest,
    RuntimeEventView,
    RuntimeStreamOptions,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
)
from app.services.published_app_bundle_storage import (
    PublishedAppBundleAssetNotFound,
    PublishedAppBundleStorage,
    PublishedAppBundleStorageError,
    PublishedAppBundleStorageNotConfigured,
)
from app.services.published_app_auth_service import PublishedAppAuthError, PublishedAppAuthService
from app.services.resource_policy_quota_service import ResourcePolicyQuotaExceeded
from app.services.usage_quota_service import QuotaExceededError


router = APIRouter(prefix="/public/apps", tags=["published-apps-public"])
PREVIEW_TOKEN_COOKIE_NAME = "published_app_public_preview_token"
_PREVIEW_ASSET_URL_ATTR_PATTERN = re.compile(r"""(?P<prefix>\b(?:src|href)=["'])(?P<path>/[^"'?#]+(?:[?#][^"']*)?)""")
_PREVIEW_RELATIVE_ASSET_URL_ATTR_PATTERN = re.compile(
    r"""(?P<prefix>\b(?:src|href)=["'])(?P<path>(?:\./)?assets/[^"'?#]+(?:[?#][^"']*)?)"""
)
_PREVIEW_ROOT_ASSET_PATTERN = re.compile(r"""(?P<quote>["'])(?P<path>/assets/[^"'?#]+(?:[?#][^"']*)?)(?P=quote)""")
_PREVIEW_REWRITABLE_TEXT_PREFIXES = ("text/html", "application/javascript", "text/javascript", "text/css")


class PublicAppConfigResponse(BaseModel):
    id: str
    organization_id: str
    agent_id: str
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    public_id: str
    status: str
    visibility: str
    auth_enabled: bool
    auth_providers: List[str]
    auth_template_key: str = "auth-classic"
    published_url: Optional[str] = None
    has_custom_ui: bool = False
    published_revision_id: Optional[str] = None
    ui_runtime_mode: str = "legacy_template"


class PublicAppRuntimeResponse(BaseModel):
    app_id: str
    public_id: str
    revision_id: str
    runtime_mode: str
    published_url: Optional[str] = None
    asset_base_url: Optional[str] = None
    api_base_path: str = "/api/py"


class PreviewAppRuntimeResponse(BaseModel):
    app_id: str
    public_id: str
    revision_id: str
    runtime_mode: str
    preview_url: str
    asset_base_url: str
    api_base_path: str = "/api/py"


class RuntimeBootstrapAuthResponse(BaseModel):
    enabled: bool
    providers: List[str]
    exchange_enabled: bool = False


class RuntimeBootstrapResponse(BaseModel):
    version: str = "runtime-bootstrap.v1"
    stream_contract_version: str = "run-stream.v2"
    request_contract_version: str = "thread.v1"
    app_id: str
    public_id: str
    revision_id: Optional[str] = None
    mode: str
    api_base_path: str
    api_base_url: str
    chat_stream_path: str
    chat_stream_url: str
    auth: RuntimeBootstrapAuthResponse


class PublicAuthRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class PublicAuthExchangeRequest(BaseModel):
    token: str


class PublicChatStreamRequest(BaseModel):
    input: Optional[str] = None
    messages: List[dict[str, Any]] = Field(default_factory=list)
    attachment_ids: List[UUID] = Field(default_factory=list)
    thread_id: Optional[UUID] = None
    run_id: Optional[UUID] = None
    context: Optional[dict[str, Any]] = None
    client: Optional[dict[str, Any]] = None


def _published_host_runtime_only_error() -> HTTPException:
    return HTTPException(
        status_code=410,
        detail={
            "code": "PUBLISHED_RUNTIME_PATH_MODE_REMOVED",
            "message": "Published app runtime/auth/chat path endpoints are removed; use the published app host with /_talmudpedia/* endpoints",
        },
    )


def _is_enabled(flag_name: str, default: str = "1") -> bool:
    return os.getenv(flag_name, default).strip().lower() not in {"0", "false", "off", "no"}


def _stream_v2_enforced() -> bool:
    return _is_enabled("STREAM_V2_ENFORCED", "1")


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost")


def _build_published_url(public_id: str) -> str:
    return build_published_app_url(public_id)


def _to_public_config(app: PublishedApp) -> PublicAppConfigResponse:
    return PublicAppConfigResponse(
        id=str(app.id),
        organization_id=str(app.organization_id),
        agent_id=str(app.agent_id),
        name=app.name,
        description=app.description,
        logo_url=app.logo_url,
        public_id=app.public_id,
        status=app.status.value if hasattr(app.status, "value") else str(app.status),
        visibility=app.visibility.value if hasattr(app.visibility, "value") else str(app.visibility or "public"),
        auth_enabled=bool(app.auth_enabled),
        auth_providers=list(app.auth_providers or []),
        auth_template_key=(app.auth_template_key or "auth-classic"),
        published_url=_build_published_url(app.public_id) if app.status == PublishedAppStatus.published else None,
        has_custom_ui=bool(app.current_published_revision_id),
        published_revision_id=str(app.current_published_revision_id) if app.current_published_revision_id else None,
        ui_runtime_mode="custom_bundle" if app.current_published_revision_id else "legacy_template",
    )


def _assert_public_visibility(app: PublishedApp) -> None:
    visibility_value = app.visibility.value if hasattr(app.visibility, "value") else str(app.visibility or "public")
    if visibility_value == PublishedAppVisibility.private.value:
        raise HTTPException(status_code=404, detail="Published app is unavailable")


async def _get_app_by_public_id(db: AsyncSession, app_public_id: str) -> PublishedApp:
    result = await db.execute(select(PublishedApp).where(PublishedApp.public_id == app_public_id).limit(1))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    return app


async def _assert_published(db: AsyncSession, app_public_id: str) -> PublishedApp:
    app = await _get_app_by_public_id(db, app_public_id)
    if app.status != PublishedAppStatus.published:
        raise HTTPException(status_code=404, detail="Published app is unavailable")
    _assert_public_visibility(app)
    return app


async def _get_published_ui_revision(db: AsyncSession, app: PublishedApp) -> PublishedAppRevision:
    if not app.current_published_revision_id:
        raise HTTPException(status_code=404, detail="Published app UI snapshot not found")
    result = await db.execute(
        select(PublishedAppRevision).where(
            and_(
                PublishedAppRevision.id == app.current_published_revision_id,
                PublishedAppRevision.published_app_id == app.id,
            )
        ).limit(1)
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(status_code=404, detail="Published app UI snapshot not found")
    return revision


def _is_probable_asset_path(path: str) -> bool:
    normalized = (path or "").strip().strip("/")
    if not normalized:
        return False
    return bool(PurePosixPath(normalized).suffix)


async def _get_preview_revision_for_principal(
    *,
    db: AsyncSession,
    revision_id: UUID,
    principal: Dict[str, Any],
) -> tuple[PublishedApp, PublishedAppRevision]:
    app_id = UUID(principal["app_id"])
    if str(principal["revision_id"]) != str(revision_id):
        raise HTTPException(status_code=403, detail="Preview token does not match requested revision")

    app_result = await db.execute(select(PublishedApp).where(PublishedApp.id == app_id).limit(1))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")

    revision_result = await db.execute(
        select(PublishedAppRevision).where(
            and_(
                PublishedAppRevision.id == revision_id,
                PublishedAppRevision.published_app_id == app.id,
            )
        ).limit(1)
    )
    revision = revision_result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(status_code=404, detail="Preview revision not found")
    return app, revision


def _normalize_return_to(request: Request, value: Optional[str], app_public_id: str) -> str:
    if value:
        if value.startswith("/"):
            base = str(request.base_url).rstrip("/")
            return f"{base}{value}"
        return value
    base = str(request.base_url).rstrip("/")
    return f"{base}/published/{app_public_id}/auth/callback"


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    updated = parsed._replace(query=urlencode(current))
    return urlunparse(updated)


def _build_published_bootstrap(
    *,
    request: Request,
    app: PublishedApp,
    revision: PublishedAppRevision,
) -> RuntimeBootstrapResponse:
    runtime_api_base = _resolve_runtime_api_base_url(request)
    runtime_api_parsed = urlparse(runtime_api_base)
    api_base_path = runtime_api_parsed.path or ""
    stream_suffix = f"/public/apps/{app.public_id}/chat/stream"
    stream_path = f"{api_base_path}{stream_suffix}" if api_base_path else stream_suffix
    stream_url = f"{runtime_api_base}{stream_suffix}"
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        public_id=app.public_id,
        revision_id=str(revision.id),
        mode="published-runtime",
        api_base_path=api_base_path or "/",
        api_base_url=runtime_api_base,
        chat_stream_path=stream_path,
        chat_stream_url=stream_url,
        auth=RuntimeBootstrapAuthResponse(
            enabled=bool(app.auth_enabled),
            providers=list(app.auth_providers or []),
            exchange_enabled=bool(app.external_auth_oidc),
        ),
    )


def _build_preview_bootstrap(
    *,
    request: Request,
    app: PublishedApp,
    revision: PublishedAppRevision,
) -> RuntimeBootstrapResponse:
    runtime_api_base = _resolve_runtime_api_base_url(request)
    runtime_api_parsed = urlparse(runtime_api_base)
    api_base_path = runtime_api_parsed.path or ""
    stream_suffix = f"/public/apps/preview/revisions/{revision.id}/chat/stream"
    stream_path = f"{api_base_path}{stream_suffix}" if api_base_path else stream_suffix
    stream_url = f"{runtime_api_base}{stream_suffix}"
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        public_id=app.public_id,
        revision_id=str(revision.id),
        mode="builder-preview",
        api_base_path=api_base_path or "/",
        api_base_url=runtime_api_base,
        chat_stream_path=stream_path,
        chat_stream_url=stream_url,
        auth=RuntimeBootstrapAuthResponse(
            enabled=bool(app.auth_enabled),
            providers=list(app.auth_providers or []),
            exchange_enabled=False,
        ),
    )


def _inject_runtime_context_into_html(html: str, context: RuntimeBootstrapResponse) -> str:
    if not html:
        return html

    context_json = context.model_dump_json(exclude_none=True)
    script = f'<script>window.__APP_RUNTIME_CONTEXT={context_json};</script>'
    lowered = html.lower()
    head_idx = lowered.find("</head>")
    if head_idx >= 0:
        return f"{html[:head_idx]}{script}{html[head_idx:]}"
    return f"{script}{html}"


def _preview_asset_base_path(*, revision_id: UUID) -> str:
    return f"/public/apps/preview/revisions/{revision_id}/assets"


def _rewrite_preview_asset_text(*, revision_id: UUID, content_type: str, content: bytes) -> tuple[bytes, bool]:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if not normalized_content_type.startswith(_PREVIEW_REWRITABLE_TEXT_PREFIXES):
        return content, False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content, False

    asset_base_path = _preview_asset_base_path(revision_id=revision_id)

    def _rewrite_root_asset_path(path: str) -> str:
        original = str(path or "")
        if original.startswith("//") or not original.startswith("/assets/"):
            return original
        return f"{asset_base_path}{original}"

    def _rewrite_relative_asset_path(path: str) -> str:
        original = str(path or "")
        normalized = original[2:] if original.startswith("./") else original
        if not normalized.startswith("assets/"):
            return original
        return f"{asset_base_path}/{normalized}"

    if normalized_content_type == "text/html":
        def _replace_attr(match: re.Match[str]) -> str:
            original = str(match.group("path") or "")
            rewritten = _rewrite_root_asset_path(original)
            return f"{match.group('prefix')}{rewritten}"

        rewritten_text = _PREVIEW_ASSET_URL_ATTR_PATTERN.sub(_replace_attr, text)
        rewritten_text = _PREVIEW_RELATIVE_ASSET_URL_ATTR_PATTERN.sub(
            lambda match: f"{match.group('prefix')}{_rewrite_relative_asset_path(str(match.group('path') or ''))}",
            rewritten_text,
        )
    else:
        def _replace_root_asset(match: re.Match[str]) -> str:
            quote = str(match.group("quote") or '"')
            original = str(match.group("path") or "")
            return f"{quote}{_rewrite_root_asset_path(original)}{quote}"

        rewritten_text = _PREVIEW_ROOT_ASSET_PATTERN.sub(_replace_root_asset, text)

    rewritten = rewritten_text.encode("utf-8")
    return rewritten, rewritten != content


def _set_preview_auth_cookie(
    *,
    response: Response,
    request: Request,
    revision_id: UUID,
    auth_token: Optional[str],
) -> None:
    token = (auth_token or "").strip()
    if not token:
        return
    response.set_cookie(
        key=PREVIEW_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path=f"/public/apps/preview/revisions/{revision_id}",
    )


def _normalize_optional_user_id(raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    return text


async def _stream_chat_for_app(
    *,
    app: PublishedApp,
    payload: PublicChatStreamRequest,
    db: AsyncSession,
    principal: Optional[Dict[str, Any]],
    enforce_app_auth: bool,
    allow_chat_persistence: bool,
    request_user_id: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
    cleanup_transient_thread: bool = False,
) -> Response:
    if enforce_app_auth:
        if app.auth_enabled and principal is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if principal is not None and principal["app_id"] != str(app.id):
            raise HTTPException(status_code=403, detail="Token does not belong to this app")

    app_account_uuid: Optional[UUID] = None
    can_persist_thread = (
        allow_chat_persistence
        and app.auth_enabled
        and principal is not None
        and bool(principal.get("app_account_id"))
    )
    if can_persist_thread:
        app_account_uuid = UUID(str(principal["app_account_id"]))
    request_context = dict(payload.context or {})
    if extra_context:
        for key, value in extra_context.items():
            request_context.setdefault(key, value)
    try:
        return await RuntimeSurfaceService(db=db, executor_cls=AgentExecutorService).stream_chat(
            agent_id=app.agent_id,
            surface_context=RuntimeSurfaceContext(
                organization_id=app.organization_id,
                surface=(
                    AgentThreadSurface.preview_runtime
                    if bool(request_context.get("published_app_preview"))
                    else AgentThreadSurface.published_host_runtime
                ),
                event_view=RuntimeEventView.public_safe,
                app_account_id=app_account_uuid,
                published_app_id=app.id,
                request_user_id=None if principal is not None else _normalize_optional_user_id(request_user_id),
                context_defaults={
                    "published_app_account_id": str(app_account_uuid) if app_account_uuid else None,
                    "published_app_id": str(app.id),
                    "published_app_public_id": app.public_id,
                    **request_context,
                },
            ),
            request=RuntimeChatRequest(
                input=payload.input,
                messages=list(payload.messages or []),
                attachment_ids=[str(item) for item in payload.attachment_ids],
                context=dict(payload.context or {}),
                client=dict(payload.client or {}),
                thread_id=payload.thread_id,
                run_id=payload.run_id,
            ),
            options=RuntimeStreamOptions(
                execution_mode=ExecutionMode.PRODUCTION,
                preload_thread_messages=True,
                cleanup_transient_thread=cleanup_transient_thread,
                stream_v2_enforced=_stream_v2_enforced(),
                padding_bytes=2048,
                include_thread_header=not cleanup_transient_thread,
            ),
        )
    except (QuotaExceededError, ResourcePolicyQuotaExceeded) as exc:
        return JSONResponse(status_code=429, content=exc.to_payload())


def _optional_uuid(value: Any) -> UUID | None:
    if value in {None, "", "null", "None"}:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


async def _upload_published_app_attachments(
    *,
    app: PublishedApp,
    owner: RuntimeAttachmentOwner,
    files: list[UploadFile],
    db: AsyncSession,
) -> dict[str, Any]:
    attachment_service = RuntimeAttachmentService(db)
    if owner.thread_id is not None:
        thread = await attachment_service.get_accessible_thread(owner=owner, thread_id=owner.thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
    attachments = await attachment_service.upload_files(owner=owner, files=files)
    payload = {"items": [RuntimeAttachmentService.serialize_attachment(item) for item in attachments]}
    await db.commit()
    return payload


@router.get("/resolve")
async def resolve_app_by_host(
    request: Request,
    host: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    host_value = (host or request.headers.get("host") or "").split(":")[0].strip().lower()
    if not host_value:
        raise HTTPException(status_code=400, detail="Host is required")

    base_domain = _apps_base_domain().strip().lower()
    if not host_value.endswith(f".{base_domain}"):
        raise HTTPException(status_code=404, detail="Host is not mapped to published apps")

    public_id = host_value[: -(len(base_domain) + 1)]
    if not public_id:
        raise HTTPException(status_code=404, detail="Could not resolve app public id")

    app = await _assert_published(db, public_id)
    return {"app": _to_public_config(app)}


@router.get("/{app_public_id}/config", response_model=PublicAppConfigResponse)
async def get_app_config(
    app_public_id: str,
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app_by_public_id(db, app_public_id)
    if app.status == PublishedAppStatus.published:
        _assert_public_visibility(app)
    return _to_public_config(app)


@router.get("/{app_public_id}/runtime", response_model=PublicAppRuntimeResponse)
async def get_published_runtime(
    app_public_id: str,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/runtime/bootstrap", response_model=RuntimeBootstrapResponse)
async def get_published_runtime_bootstrap(
    app_public_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, request, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/assets/{asset_path:path}")
async def get_published_asset(
    request: Request,
    app_public_id: str,
    asset_path: str,
    db: AsyncSession = Depends(get_db),
):
    _ = (request, app_public_id, asset_path, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/ui")
async def get_published_ui(
    app_public_id: str,
):
    _ = app_public_id
    raise HTTPException(
        status_code=410,
        detail={
            "code": "UI_SOURCE_MODE_REMOVED",
            "message": "UI source mode is removed; use /public/apps/{public_id}/runtime instead",
        },
    )


@router.get("/preview/ui/{revision_id}")
async def get_preview_ui(
    revision_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
):
    _ = (revision_id, principal)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "UI_SOURCE_MODE_REMOVED",
            "message": "Preview UI source mode is removed; use /public/apps/preview/revisions/{revision_id}/runtime instead",
        },
    )


@router.get("/preview/revisions/{revision_id}/assets/{asset_path:path}")
async def get_preview_asset(
    request: Request,
    revision_id: UUID,
    asset_path: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    app, revision = await _get_preview_revision_for_principal(
        db=db,
        revision_id=revision_id,
        principal=principal,
    )
    dist_prefix = (revision.dist_storage_prefix or "").strip()
    if not dist_prefix:
        raise HTTPException(status_code=404, detail="Preview assets are unavailable for this revision")

    try:
        storage = PublishedAppBundleStorage.from_env()
        payload, content_type = storage.read_asset_bytes(
            dist_storage_prefix=dist_prefix,
            asset_path=asset_path,
        )
    except PublishedAppBundleAssetNotFound:
        raise HTTPException(status_code=404, detail="Preview asset not found")
    except PublishedAppBundleStorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PublishedAppBundleStorageError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load preview asset: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if content_type.startswith("text/html"):
        try:
            html = payload.decode("utf-8")
            bootstrap = _build_preview_bootstrap(
                request=request,
                app=app,
                revision=revision,
            )
            html = _inject_runtime_context_into_html(html, bootstrap)
            payload = html.encode("utf-8")
        except Exception:
            pass

    payload, content_rewritten = _rewrite_preview_asset_text(
        revision_id=revision_id,
        content_type=content_type,
        content=payload,
    )

    response = Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "no-store" if content_rewritten else "no-store"},
    )
    _set_preview_auth_cookie(
        response=response,
        request=request,
        revision_id=revision_id,
        auth_token=principal.get("auth_token"),
    )
    return response


@router.get("/preview/revisions/{revision_id}/runtime", response_model=PreviewAppRuntimeResponse)
async def get_preview_runtime(
    request: Request,
    response: Response,
    revision_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    app, revision = await _get_preview_revision_for_principal(
        db=db,
        revision_id=revision_id,
        principal=principal,
    )

    base_url = str(request.base_url).rstrip("/")
    request_path = request.url.path
    runtime_suffix = f"/preview/revisions/{revision_id}/runtime"
    if request_path.endswith(runtime_suffix):
        asset_base_path = f"{request_path[: -len('/runtime')]}/assets/"
    else:
        asset_base_path = f"/public/apps/preview/revisions/{revision_id}/assets/"
    asset_base_url = f"{base_url}{asset_base_path}"
    entry_html = "index.html"
    manifest = revision.dist_manifest or {}
    if isinstance(manifest, dict):
        manifest_entry = manifest.get("entry_html")
        if isinstance(manifest_entry, str) and manifest_entry.strip():
            entry_html = manifest_entry.lstrip("/")
    preview_url = f"{asset_base_url}{entry_html}"
    _set_preview_auth_cookie(
        response=response,
        request=request,
        revision_id=revision_id,
        auth_token=principal.get("auth_token"),
    )
    return PreviewAppRuntimeResponse(
        app_id=str(app.id),
        public_id=app.public_id,
        revision_id=str(revision.id),
        runtime_mode=revision.template_runtime or "vite_static",
        preview_url=preview_url,
        asset_base_url=asset_base_url,
        api_base_path="/api/py",
    )


@router.get("/preview/revisions/{revision_id}/runtime/bootstrap", response_model=RuntimeBootstrapResponse)
async def get_preview_runtime_bootstrap(
    request: Request,
    response: Response,
    revision_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    app, revision = await _get_preview_revision_for_principal(
        db=db,
        revision_id=revision_id,
        principal=principal,
    )
    _set_preview_auth_cookie(
        response=response,
        request=request,
        revision_id=revision_id,
        auth_token=principal.get("auth_token"),
    )
    return _build_preview_bootstrap(
        request=request,
        app=app,
        revision=revision,
    )


@router.post("/preview/revisions/{revision_id}/chat/stream")
async def preview_chat_stream(
    revision_id: UUID,
    payload: PublicChatStreamRequest,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    if not _is_enabled("PUBLISHED_APPS_ENABLED", "1"):
        raise HTTPException(status_code=404, detail="Published apps are disabled")

    app, _ = await _get_preview_revision_for_principal(
        db=db,
        revision_id=revision_id,
        principal=principal,
    )
    return await _stream_chat_for_app(
        app=app,
        payload=payload,
        db=db,
        principal=None,
        enforce_app_auth=False,
        allow_chat_persistence=False,
        request_user_id=_normalize_optional_user_id(principal.get("user_id")),
        extra_context={
            "published_app_preview_revision_id": str(revision_id),
            "published_app_preview": True,
        },
    )


@router.post("/preview/revisions/{revision_id}/attachments/upload")
async def upload_preview_attachments(
    revision_id: UUID,
    files: list[UploadFile] = File(...),
    thread_id: UUID | None = Form(default=None),
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    app, _ = await _get_preview_revision_for_principal(
        db=db,
        revision_id=revision_id,
        principal=principal,
    )
    owner = RuntimeAttachmentOwner(
        organization_id=app.organization_id,
        surface=AgentThreadSurface.published_host_runtime,
        user_id=_optional_uuid(principal.get("user_id")),
        published_app_id=app.id,
        thread_id=thread_id,
    )
    return await _upload_published_app_attachments(app=app, owner=owner, files=files, db=db)


@router.post("/{app_public_id}/auth/signup")
async def signup(
    app_public_id: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, payload, db)
    raise _published_host_runtime_only_error()


@router.post("/{app_public_id}/auth/login")
async def login(
    app_public_id: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, payload, db)
    raise _published_host_runtime_only_error()


@router.post("/{app_public_id}/auth/exchange")
async def exchange_auth_token(
    app_public_id: str,
    payload: PublicAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, payload, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/auth/google/start")
async def google_start(
    app_public_id: str,
    request: Request,
    return_to: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, request, return_to, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/auth/google/callback")
async def google_callback(
    app_public_id: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, code, state, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/auth/me")
async def auth_me(
    app_public_id: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    _ = (app_public_id, principal)
    raise _published_host_runtime_only_error()


@router.post("/{app_public_id}/auth/logout")
async def auth_logout(
    app_public_id: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, principal, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/chats")
async def list_chats(
    app_public_id: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, principal, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_public_id}/chats/{chat_id}")
async def get_chat(
    app_public_id: str,
    chat_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, chat_id, principal, db)
    raise _published_host_runtime_only_error()


@router.post("/{app_public_id}/chat/stream")
async def chat_stream(
    app_public_id: str,
    payload: PublicChatStreamRequest,
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_public_id, payload, principal, db)
    raise _published_host_runtime_only_error()
