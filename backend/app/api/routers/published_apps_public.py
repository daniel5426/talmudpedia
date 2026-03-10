import json
import os
import re
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.stream_contract_v2 import (
    build_stream_v2_event,
    normalize_filtered_event_to_v2,
)
from app.agent.execution.types import ExecutionMode
from app.api.dependencies import (
    get_current_published_app_preview_principal,
    get_current_published_app_principal,
    get_optional_published_app_principal,
)
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.agent_threads import AgentThreadTurn
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppStatus,
    PublishedAppVisibility,
)
from app.db.postgres.session import get_db
from app.services.thread_service import ThreadService
from app.services.published_app_bundle_storage import (
    PublishedAppBundleAssetNotFound,
    PublishedAppBundleStorage,
    PublishedAppBundleStorageError,
    PublishedAppBundleStorageNotConfigured,
)
from app.services.published_app_auth_service import PublishedAppAuthError, PublishedAppAuthService
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
    tenant_id: str
    agent_id: str
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    slug: str
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
    slug: str
    revision_id: str
    runtime_mode: str
    published_url: Optional[str] = None
    asset_base_url: Optional[str] = None
    api_base_path: str = "/api/py"


class PreviewAppRuntimeResponse(BaseModel):
    app_id: str
    slug: str
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
    slug: str
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
    messages: List[dict[str, Any]] = []
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


def _apps_url_scheme() -> str:
    configured = (os.getenv("APPS_URL_SCHEME") or "").strip().lower()
    if configured in {"http", "https"}:
        return configured
    return "https"


def _apps_url_port() -> str:
    configured = (os.getenv("APPS_URL_PORT") or "").strip()
    if configured:
        return configured if configured.startswith(":") else f":{configured}"
    return ""


def _build_published_url(slug: str) -> str:
    return f"{_apps_url_scheme()}://{slug}.{_apps_base_domain()}{_apps_url_port()}"


def _to_public_config(app: PublishedApp) -> PublicAppConfigResponse:
    return PublicAppConfigResponse(
        id=str(app.id),
        tenant_id=str(app.tenant_id),
        agent_id=str(app.agent_id),
        name=app.name,
        description=app.description,
        logo_url=app.logo_url,
        slug=app.slug,
        status=app.status.value if hasattr(app.status, "value") else str(app.status),
        visibility=app.visibility.value if hasattr(app.visibility, "value") else str(app.visibility or "public"),
        auth_enabled=bool(app.auth_enabled),
        auth_providers=list(app.auth_providers or []),
        auth_template_key=(app.auth_template_key or "auth-classic"),
        published_url=_build_published_url(app.slug) if app.status == PublishedAppStatus.published else None,
        has_custom_ui=bool(app.current_published_revision_id),
        published_revision_id=str(app.current_published_revision_id) if app.current_published_revision_id else None,
        ui_runtime_mode="custom_bundle" if app.current_published_revision_id else "legacy_template",
    )


def _assert_public_visibility(app: PublishedApp) -> None:
    visibility_value = app.visibility.value if hasattr(app.visibility, "value") else str(app.visibility or "public")
    if visibility_value == PublishedAppVisibility.private.value:
        raise HTTPException(status_code=404, detail="Published app is unavailable")


async def _get_app_by_slug(db: AsyncSession, app_slug: str) -> PublishedApp:
    result = await db.execute(select(PublishedApp).where(PublishedApp.slug == app_slug).limit(1))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    return app


async def _assert_published(db: AsyncSession, app_slug: str) -> PublishedApp:
    app = await _get_app_by_slug(db, app_slug)
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


def _normalize_return_to(request: Request, value: Optional[str], app_slug: str) -> str:
    if value:
        if value.startswith("/"):
            base = str(request.base_url).rstrip("/")
            return f"{base}{value}"
        return value
    base = str(request.base_url).rstrip("/")
    return f"{base}/published/{app_slug}/auth/callback"


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    updated = parsed._replace(query=urlencode(current))
    return urlunparse(updated)


def _resolve_runtime_api_base_url(request: Request) -> str:
    explicit = (os.getenv("APPS_DRAFT_DEV_RUNTIME_API_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    parsed = urlparse(str(request.base_url))
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    prefix_env = os.getenv("APPS_DRAFT_DEV_RUNTIME_API_PREFIX")
    if prefix_env is not None:
        api_prefix = (prefix_env or "").strip()
    else:
        api_prefix = str(request.scope.get("root_path") or "").strip()
        if not api_prefix:
            api_prefix = (request.headers.get("x-forwarded-prefix") or "").strip()
        if not api_prefix and str(request.url.path).startswith("/api/py/"):
            api_prefix = "/api/py"
    if not api_prefix:
        return origin
    if not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    return f"{origin}{api_prefix.rstrip('/')}"


def _build_published_bootstrap(
    *,
    request: Request,
    app: PublishedApp,
    revision: PublishedAppRevision,
) -> RuntimeBootstrapResponse:
    runtime_api_base = _resolve_runtime_api_base_url(request)
    runtime_api_parsed = urlparse(runtime_api_base)
    api_base_path = runtime_api_parsed.path or ""
    stream_suffix = f"/public/apps/{app.slug}/chat/stream"
    stream_path = f"{api_base_path}{stream_suffix}" if api_base_path else stream_suffix
    stream_url = f"{runtime_api_base}{stream_suffix}"
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        slug=app.slug,
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
        slug=app.slug,
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


def _turns_to_messages(turns: list[AgentThreadTurn]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for turn in sorted(turns, key=lambda item: int(item.turn_index or 0)):
        if turn.user_input_text:
            messages.append({"role": "user", "content": turn.user_input_text})
        if turn.assistant_output_text:
            messages.append({"role": "assistant", "content": turn.assistant_output_text})
    return messages


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
) -> Response:
    if enforce_app_auth:
        if app.auth_enabled and principal is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if principal is not None and principal["app_id"] != str(app.id):
            raise HTTPException(status_code=403, detail="Token does not belong to this app")

    user_uuid: Optional[UUID] = None
    app_account_uuid: Optional[UUID] = None
    run_messages: List[dict[str, Any]] = []
    can_persist_thread = (
        allow_chat_persistence
        and app.auth_enabled
        and principal is not None
        and bool(principal.get("app_account_id"))
    )
    if can_persist_thread:
        app_account_uuid = UUID(str(principal["app_account_id"]))

    if payload.thread_id:
        thread_service = ThreadService(db)
        existing_thread = await thread_service.get_thread_with_turns(
            tenant_id=app.tenant_id,
            thread_id=payload.thread_id,
            app_account_id=app_account_uuid,
            published_app_id=app.id,
        )
        if existing_thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        run_messages.extend(_turns_to_messages(list(existing_thread.turns or [])))

    run_messages.extend(payload.messages or [])
    if payload.input:
        run_messages.append({"role": "user", "content": payload.input})

    executor = AgentExecutorService(db=db)
    request_context = dict(payload.context or {})
    request_context.setdefault("tenant_id", str(app.tenant_id))
    request_context.setdefault(
        "user_id",
        str(user_uuid) if user_uuid else (None if principal is not None else _normalize_optional_user_id(request_user_id)),
    )
    request_context.setdefault("published_app_account_id", str(app_account_uuid) if app_account_uuid else None)
    request_context.setdefault("published_app_id", str(app.id))
    request_context.setdefault("published_app_slug", app.slug)
    request_context.setdefault("thread_id", str(payload.thread_id) if payload.thread_id else None)
    if extra_context:
        for key, value in extra_context.items():
            request_context.setdefault(key, value)

    run_id = payload.run_id
    resume_payload: Optional[dict[str, Any]] = None
    if run_id:
        resume_payload = dict(payload.context or {})
        if payload.input and "input" not in resume_payload:
            resume_payload["input"] = payload.input
        try:
            await executor.resume_run(run_id, resume_payload, background=False)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Cannot resume run {run_id}: {exc}")
    else:
        try:
            run_id = await executor.start_run(
                app.agent_id,
                {
                    "messages": run_messages,
                    "input": payload.input,
                    "thread_id": str(payload.thread_id) if payload.thread_id else None,
                    "context": request_context,
                },
                user_id=user_uuid,
                background=False,
                mode=ExecutionMode.PRODUCTION,
                thread_id=payload.thread_id,
            )
        except QuotaExceededError as exc:
            return JSONResponse(status_code=429, content=exc.to_payload())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    run_row = await db.get(AgentRun, run_id)
    thread_id_value = str(run_row.thread_id) if run_row and run_row.thread_id else None

    async def event_generator():
        raw_stream = executor.run_and_stream(run_id, db, resume_payload=resume_payload, mode=ExecutionMode.PRODUCTION)
        filtered_stream = StreamAdapter.filter_stream(raw_stream, ExecutionMode.PRODUCTION)
        seq = 1
        yield ": " + (" " * 2048) + "\n\n"
        if _stream_v2_enforced():
            accepted = build_stream_v2_event(
                seq=seq,
                run_id=str(run_id),
                event="run.accepted",
                stage="run",
                payload={"status": "running", "thread_id": thread_id_value},
            )
            seq += 1
            yield f"data: {json.dumps(accepted, default=str)}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'run_id', 'run_id': str(run_id)})}\n\n"

        try:
            async for event_dict in filtered_stream:
                if _stream_v2_enforced():
                    mapped_event, stage, payload_v2, diagnostics = normalize_filtered_event_to_v2(raw_event=event_dict)
                    envelope = build_stream_v2_event(
                        seq=seq,
                        run_id=str(run_id),
                        event=mapped_event,
                        stage=stage,
                        payload=payload_v2,
                        diagnostics=diagnostics,
                    )
                    seq += 1
                    yield f"data: {json.dumps(envelope, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps(event_dict, default=str)}\n\n"
        except Exception as exc:
            if _stream_v2_enforced():
                envelope = build_stream_v2_event(
                    seq=seq,
                    run_id=str(run_id),
                    event="run.failed",
                    stage="run",
                    payload={"error": str(exc)},
                    diagnostics=[{"message": str(exc)}],
                )
                yield f"data: {json.dumps(envelope, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    if thread_id_value:
        headers["X-Thread-ID"] = thread_id_value
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


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

    slug = host_value[: -(len(base_domain) + 1)]
    if not slug:
        raise HTTPException(status_code=404, detail="Could not resolve app slug")

    app = await _assert_published(db, slug)
    return {"app": _to_public_config(app)}


@router.get("/{app_slug}/config", response_model=PublicAppConfigResponse)
async def get_app_config(
    app_slug: str,
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app_by_slug(db, app_slug)
    if app.status == PublishedAppStatus.published:
        _assert_public_visibility(app)
    return _to_public_config(app)


@router.get("/{app_slug}/runtime", response_model=PublicAppRuntimeResponse)
async def get_published_runtime(
    app_slug: str,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/runtime/bootstrap", response_model=RuntimeBootstrapResponse)
async def get_published_runtime_bootstrap(
    app_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, request, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/assets/{asset_path:path}")
async def get_published_asset(
    request: Request,
    app_slug: str,
    asset_path: str,
    db: AsyncSession = Depends(get_db),
):
    _ = (request, app_slug, asset_path, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/ui")
async def get_published_ui(
    app_slug: str,
):
    _ = app_slug
    raise HTTPException(
        status_code=410,
        detail={
            "code": "UI_SOURCE_MODE_REMOVED",
            "message": "UI source mode is removed; use /public/apps/{slug}/runtime instead",
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
        slug=app.slug,
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


@router.post("/{app_slug}/auth/signup")
async def signup(
    app_slug: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, payload, db)
    raise _published_host_runtime_only_error()


@router.post("/{app_slug}/auth/login")
async def login(
    app_slug: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, payload, db)
    raise _published_host_runtime_only_error()


@router.post("/{app_slug}/auth/exchange")
async def exchange_auth_token(
    app_slug: str,
    payload: PublicAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, payload, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/auth/google/start")
async def google_start(
    app_slug: str,
    request: Request,
    return_to: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, request, return_to, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/auth/google/callback")
async def google_callback(
    app_slug: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, code, state, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/auth/me")
async def auth_me(
    app_slug: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    _ = (app_slug, principal)
    raise _published_host_runtime_only_error()


@router.post("/{app_slug}/auth/logout")
async def auth_logout(
    app_slug: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, principal, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/chats")
async def list_chats(
    app_slug: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, principal, db)
    raise _published_host_runtime_only_error()


@router.get("/{app_slug}/chats/{chat_id}")
async def get_chat(
    app_slug: str,
    chat_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, chat_id, principal, db)
    raise _published_host_runtime_only_error()


@router.post("/{app_slug}/chat/stream")
async def chat_stream(
    app_slug: str,
    payload: PublicChatStreamRequest,
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    _ = (app_slug, payload, principal, db)
    raise _published_host_runtime_only_error()
