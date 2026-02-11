import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.api.dependencies import (
    get_current_published_app_preview_principal,
    get_current_published_app_principal,
    get_optional_published_app_principal,
)
from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision, PublishedAppStatus
from app.db.postgres.session import get_db
from app.services.published_app_bundle_storage import (
    PublishedAppBundleAssetNotFound,
    PublishedAppBundleStorage,
    PublishedAppBundleStorageError,
    PublishedAppBundleStorageNotConfigured,
)
from app.services.published_app_auth_service import PublishedAppAuthError, PublishedAppAuthService


router = APIRouter(prefix="/public/apps", tags=["published-apps-public"])


class PublicAppConfigResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    name: str
    slug: str
    status: str
    auth_enabled: bool
    auth_providers: List[str]
    published_url: Optional[str] = None
    has_custom_ui: bool = False
    published_revision_id: Optional[str] = None
    ui_runtime_mode: str = "legacy_template"


class PublicAppUIResponse(BaseModel):
    app_id: str
    revision_id: str
    template_key: str
    entry_file: str
    files: Dict[str, str]
    compiled_bundle: Optional[str] = None


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


class PublicAuthRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class PublicChatStreamRequest(BaseModel):
    input: Optional[str] = None
    messages: List[dict[str, Any]] = []
    chat_id: Optional[UUID] = None
    context: Optional[dict[str, Any]] = None


def _is_enabled(flag_name: str, default: str = "1") -> bool:
    return os.getenv(flag_name, default).strip().lower() not in {"0", "false", "off", "no"}


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost")


def _apps_runtime_mode() -> str:
    value = (os.getenv("APPS_RUNTIME_MODE") or "legacy").strip().lower()
    return value if value in {"legacy", "static"} else "legacy"


def _to_public_config(app: PublishedApp) -> PublicAppConfigResponse:
    return PublicAppConfigResponse(
        id=str(app.id),
        tenant_id=str(app.tenant_id),
        agent_id=str(app.agent_id),
        name=app.name,
        slug=app.slug,
        status=app.status.value if hasattr(app.status, "value") else str(app.status),
        auth_enabled=bool(app.auth_enabled),
        auth_providers=list(app.auth_providers or []),
        published_url=app.published_url,
        has_custom_ui=bool(app.current_published_revision_id),
        published_revision_id=str(app.current_published_revision_id) if app.current_published_revision_id else None,
        ui_runtime_mode="custom_bundle" if app.current_published_revision_id else "legacy_template",
    )


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


def _chat_message_to_payload(message: Message) -> dict[str, Any]:
    return {
        "role": message.role.value if hasattr(message.role, "value") else str(message.role),
        "content": message.content,
        "created_at": message.created_at,
        "tool_calls": message.tool_calls,
        "token_count": message.token_count,
    }


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
    return _to_public_config(app)


@router.get("/{app_slug}/runtime", response_model=PublicAppRuntimeResponse)
async def get_published_runtime(
    app_slug: str,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    revision = await _get_published_ui_revision(db, app)
    published_url = app.published_url
    return PublicAppRuntimeResponse(
        app_id=str(app.id),
        slug=app.slug,
        revision_id=str(revision.id),
        runtime_mode=revision.template_runtime or "vite_static",
        published_url=published_url,
        asset_base_url=published_url,
        api_base_path="/api/py",
    )


@router.get("/{app_slug}/ui", response_model=PublicAppUIResponse)
async def get_published_ui(
    app_slug: str,
    db: AsyncSession = Depends(get_db),
):
    if _apps_runtime_mode() == "static":
        raise HTTPException(
            status_code=410,
            detail={
                "code": "UI_SOURCE_MODE_REMOVED",
                "message": "UI source mode is disabled in static runtime mode",
            },
        )

    app = await _assert_published(db, app_slug)
    revision = await _get_published_ui_revision(db, app)
    return PublicAppUIResponse(
        app_id=str(app.id),
        revision_id=str(revision.id),
        template_key=revision.template_key,
        entry_file=revision.entry_file,
        files=dict(revision.files or {}),
        compiled_bundle=revision.compiled_bundle,
    )


@router.get("/preview/ui/{revision_id}", response_model=PublicAppUIResponse)
async def get_preview_ui(
    revision_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    app, revision = await _get_preview_revision_for_principal(
        db=db,
        revision_id=revision_id,
        principal=principal,
    )

    return PublicAppUIResponse(
        app_id=str(app.id),
        revision_id=str(revision.id),
        template_key=revision.template_key,
        entry_file=revision.entry_file,
        files=dict(revision.files or {}),
        compiled_bundle=revision.compiled_bundle,
    )


@router.get("/preview/revisions/{revision_id}/assets/{asset_path:path}")
async def get_preview_asset(
    revision_id: UUID,
    asset_path: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_preview_principal),
    db: AsyncSession = Depends(get_db),
):
    _, revision = await _get_preview_revision_for_principal(
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

    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/preview/revisions/{revision_id}/runtime", response_model=PreviewAppRuntimeResponse)
async def get_preview_runtime(
    request: Request,
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
    preview_url = f"{base_url}/api/py/public/apps/preview/revisions/{revision_id}/assets/"
    return PreviewAppRuntimeResponse(
        app_id=str(app.id),
        slug=app.slug,
        revision_id=str(revision.id),
        runtime_mode=revision.template_runtime or "vite_static",
        preview_url=preview_url,
        asset_base_url=preview_url,
        api_base_path="/api/py",
    )


@router.post("/{app_slug}/auth/signup")
async def signup(
    app_slug: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    providers = set(app.auth_providers or [])
    if "password" not in providers:
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
    return {
        "token": result.token,
        "token_type": "bearer",
        "user": {
            "id": str(result.user.id),
            "email": result.user.email,
            "full_name": result.user.full_name,
            "avatar": result.user.avatar,
        },
    }


@router.post("/{app_slug}/auth/login")
async def login(
    app_slug: str,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    providers = set(app.auth_providers or [])
    if "password" not in providers:
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
    return {
        "token": result.token,
        "token_type": "bearer",
        "user": {
            "id": str(result.user.id),
            "email": result.user.email,
            "full_name": result.user.full_name,
            "avatar": result.user.avatar,
        },
    }


@router.get("/{app_slug}/auth/google/start")
async def google_start(
    app_slug: str,
    request: Request,
    return_to: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not _is_enabled("PUBLISHED_APPS_GOOGLE_AUTH_ENABLED", "1"):
        raise HTTPException(status_code=404, detail="Google auth is disabled")

    app = await _assert_published(db, app_slug)
    if not app.auth_enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled for this app")
    providers = set(app.auth_providers or [])
    if "google" not in providers:
        raise HTTPException(status_code=400, detail="Google auth is disabled for this app")

    auth_service = PublishedAppAuthService(db)
    credential = await auth_service.get_google_credential(app.tenant_id)
    if credential is None:
        raise HTTPException(status_code=400, detail="Tenant Google OAuth credentials are missing")

    creds = credential.credentials or {}
    client_id = creds.get("client_id")
    redirect_uri = creds.get("redirect_uri")
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="Google OAuth credentials are incomplete")

    target = _normalize_return_to(request, return_to, app_slug)
    auth_url = auth_service.build_google_auth_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        app_slug=app_slug,
        return_to=target,
    )
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/{app_slug}/auth/google/callback")
async def google_callback(
    app_slug: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    auth_service = PublishedAppAuthService(db)

    credential = await auth_service.get_google_credential(app.tenant_id)
    if credential is None:
        raise HTTPException(status_code=400, detail="Tenant Google OAuth credentials are missing")

    creds = credential.credentials or {}
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    redirect_uri = creds.get("redirect_uri")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=400, detail="Google OAuth credentials are incomplete")

    try:
        state_payload = auth_service.parse_google_state(state)
        if state_payload.get("app_slug") != app_slug:
            raise PublishedAppAuthError("OAuth state app slug mismatch")
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
        user = await auth_service.get_or_create_google_user(
            email=str(profile.get("email", "")).lower(),
            google_id=str(profile.get("sub")),
            full_name=profile.get("name"),
            avatar=profile.get("picture"),
        )
        result = await auth_service.issue_auth_result(
            app=app,
            user=user,
            provider="google",
            metadata={"google_sub": str(profile.get("sub"))},
        )
    except PublishedAppAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    callback_url = _append_query(
        state_payload["return_to"],
        {"token": result.token, "appSlug": app.slug},
    )
    return RedirectResponse(url=callback_url, status_code=302)


@router.get("/{app_slug}/auth/me")
async def auth_me(
    app_slug: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
):
    if principal["app_slug"] != app_slug:
        raise HTTPException(status_code=403, detail="Token does not belong to this app")
    user = principal["user"]
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "avatar": user.avatar,
        "app_id": principal["app_id"],
        "app_slug": principal["app_slug"],
    }


@router.post("/{app_slug}/auth/logout")
async def auth_logout(
    app_slug: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal["app_slug"] != app_slug:
        raise HTTPException(status_code=403, detail="Token does not belong to this app")
    service = PublishedAppAuthService(db)
    await service.revoke_session(
        session_id=UUID(principal["session_id"]),
        user_id=UUID(principal["user_id"]),
        app_id=UUID(principal["app_id"]),
    )
    return {"status": "logged_out"}


@router.get("/{app_slug}/chats")
async def list_chats(
    app_slug: str,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    if principal["app_id"] != str(app.id):
        raise HTTPException(status_code=403, detail="Token does not belong to this app")
    user_id = UUID(principal["user_id"])
    result = await db.execute(
        select(Chat)
        .where(
            and_(
                Chat.published_app_id == app.id,
                Chat.user_id == user_id,
            )
        )
        .order_by(Chat.updated_at.desc())
        .limit(50)
    )
    chats = result.scalars().all()
    return {
        "items": [
            {
                "id": str(chat.id),
                "title": chat.title,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
                "is_archived": chat.is_archived,
            }
            for chat in chats
        ]
    }


@router.get("/{app_slug}/chats/{chat_id}")
async def get_chat(
    app_slug: str,
    chat_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    app = await _assert_published(db, app_slug)
    if principal["app_id"] != str(app.id):
        raise HTTPException(status_code=403, detail="Token does not belong to this app")
    user_id = UUID(principal["user_id"])
    result = await db.execute(
        select(Chat).where(
            and_(
                Chat.id == chat_id,
                Chat.published_app_id == app.id,
                Chat.user_id == user_id,
            )
        ).limit(1)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    msg_result = await db.execute(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.index.asc())
    )
    messages = msg_result.scalars().all()
    return {
        "id": str(chat.id),
        "title": chat.title,
        "messages": [_chat_message_to_payload(message) for message in messages],
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
    }


@router.post("/{app_slug}/chat/stream")
async def chat_stream(
    app_slug: str,
    payload: PublicChatStreamRequest,
    principal: Optional[Dict[str, Any]] = Depends(get_optional_published_app_principal),
    db: AsyncSession = Depends(get_db),
):
    if not _is_enabled("PUBLISHED_APPS_ENABLED", "1"):
        raise HTTPException(status_code=404, detail="Published apps are disabled")

    app = await _assert_published(db, app_slug)
    if app.auth_enabled and principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if principal is not None and principal["app_id"] != str(app.id):
        raise HTTPException(status_code=403, detail="Token does not belong to this app")

    user_uuid: Optional[UUID] = None
    chat: Optional[Chat] = None
    existing_count = 0
    run_messages: List[dict[str, Any]] = []

    if app.auth_enabled and principal is not None:
        user_uuid = UUID(principal["user_id"])
        if payload.chat_id:
            chat_result = await db.execute(
                select(Chat).where(
                    and_(
                        Chat.id == payload.chat_id,
                        Chat.published_app_id == app.id,
                        Chat.user_id == user_uuid,
                    )
                ).limit(1)
            )
            chat = chat_result.scalar_one_or_none()
            if chat is None:
                raise HTTPException(status_code=404, detail="Chat not found")
            message_result = await db.execute(
                select(Message).where(Message.chat_id == chat.id).order_by(Message.index.asc())
            )
            existing_messages = message_result.scalars().all()
            existing_count = len(existing_messages)
            run_messages.extend(
                [{"role": m.role.value if hasattr(m.role, "value") else str(m.role), "content": m.content} for m in existing_messages]
            )
        else:
            title_source = payload.input or (payload.messages[0].get("content") if payload.messages else "New chat")
            chat = Chat(
                tenant_id=app.tenant_id,
                user_id=user_uuid,
                published_app_id=app.id,
                title=(title_source or "New chat")[:60],
            )
            db.add(chat)
            await db.flush()

        if payload.messages:
            run_messages.extend(payload.messages)
        if payload.input:
            run_messages.append({"role": "user", "content": payload.input})
            user_message = Message(
                chat_id=chat.id,  # type: ignore[arg-type]
                role=MessageRole.USER,
                content=payload.input,
                index=existing_count,
            )
            db.add(user_message)
            chat.updated_at = datetime.now(timezone.utc)  # type: ignore[union-attr]
            await db.commit()
    else:
        run_messages.extend(payload.messages or [])
        if payload.input:
            run_messages.append({"role": "user", "content": payload.input})

    executor = AgentExecutorService(db=db)
    request_context = dict(payload.context or {})
    request_context.setdefault("tenant_id", str(app.tenant_id))
    request_context.setdefault("user_id", str(user_uuid) if user_uuid else None)
    request_context.setdefault("published_app_id", str(app.id))
    request_context.setdefault("published_app_slug", app.slug)

    run_id = await executor.start_run(
        app.agent_id,
        {
            "messages": run_messages,
            "input": payload.input,
            "context": request_context,
        },
        user_id=user_uuid,
        background=False,
        mode=ExecutionMode.PRODUCTION,
    )

    async def event_generator():
        assistant_text_parts: List[str] = []
        raw_stream = executor.run_and_stream(run_id, db, mode=ExecutionMode.PRODUCTION)
        filtered_stream = StreamAdapter.filter_stream(raw_stream, ExecutionMode.PRODUCTION)
        yield ": " + (" " * 2048) + "\n\n"
        yield f"data: {json.dumps({'event': 'run_id', 'run_id': str(run_id)})}\n\n"

        try:
            async for event_dict in filtered_stream:
                if (
                    event_dict.get("event") == "token"
                    and isinstance(event_dict.get("data"), dict)
                    and event_dict["data"].get("content")
                ):
                    assistant_text_parts.append(str(event_dict["data"]["content"]))
                elif event_dict.get("type") == "token" and event_dict.get("content"):
                    assistant_text_parts.append(str(event_dict["content"]))
                yield f"data: {json.dumps(event_dict, default=str)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            if app.auth_enabled and chat is not None:
                assistant_text = "".join(assistant_text_parts).strip()
                if assistant_text:
                    count_result = await db.execute(
                        select(Message).where(Message.chat_id == chat.id).order_by(Message.index.desc()).limit(1)
                    )
                    last = count_result.scalar_one_or_none()
                    next_index = (last.index + 1) if last is not None else 0
                    db.add(
                        Message(
                            chat_id=chat.id,
                            role=MessageRole.ASSISTANT,
                            content=assistant_text,
                            index=next_index,
                        )
                    )
                    chat.updated_at = datetime.now(timezone.utc)
                    await db.commit()

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    if chat is not None:
        headers["X-Chat-ID"] = str(chat.id)
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
