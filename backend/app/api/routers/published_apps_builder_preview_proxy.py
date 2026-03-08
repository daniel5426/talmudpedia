from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_published_app_preview_token
from app.db.postgres.models.published_apps import PublishedAppDraftDevSession
from app.db.postgres.session import get_db
from app.services.apps_builder_trace import apps_builder_trace


router = APIRouter(tags=["published-apps-builder-preview-proxy"])

PREVIEW_COOKIE_NAME = "published_app_preview_token"
PREVIEW_PROXY_HEADER = "e2b-traffic-access-token"
_PREVIEW_WEBSOCKET_OPEN_TIMEOUT_SECONDS = 20.0
_PREVIEW_WEBSOCKET_CONNECT_ATTEMPTS = 3


def _extract_preview_token(*, request: Request | None = None, websocket: WebSocket | None = None) -> str | None:
    query_params = request.query_params if request is not None else websocket.query_params
    cookies = request.cookies if request is not None else websocket.cookies
    query_token = str(query_params.get("runtime_token") or "").strip()
    if query_token:
        return query_token
    cookie_token = str(cookies.get(PREVIEW_COOKIE_NAME) or "").strip()
    return cookie_token or None


def _validate_preview_token(token: str) -> dict[str, Any]:
    try:
        payload = decode_published_app_preview_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid published app preview token") from exc
    scopes = payload.get("scope") or []
    if "apps.preview" not in scopes:
        raise HTTPException(status_code=403, detail="Preview token is missing apps.preview scope")
    return payload


async def _load_session(*, db: AsyncSession, session_id: str) -> PublishedAppDraftDevSession:
    try:
        session_uuid = UUID(str(session_id))
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Draft dev session not found") from exc
    result = await db.execute(
        select(PublishedAppDraftDevSession).where(PublishedAppDraftDevSession.id == session_uuid).limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    return session


def _resolve_preview_target(session: PublishedAppDraftDevSession) -> dict[str, str]:
    metadata = session.backend_metadata if isinstance(session.backend_metadata, dict) else {}
    preview = metadata.get("preview") if isinstance(metadata.get("preview"), dict) else {}
    upstream_base_url = str(preview.get("upstream_base_url") or "").strip()
    if not upstream_base_url:
        raise HTTPException(status_code=404, detail="Draft dev preview target is unavailable")
    base_path = str(preview.get("base_path") or "").strip() or "/"
    upstream_path = str(preview.get("upstream_path") or "").strip() or base_path
    traffic_access_token = str(preview.get("traffic_access_token") or "").strip()
    return {
        "upstream_base_url": upstream_base_url.rstrip("/"),
        "base_path": base_path,
        "upstream_path": upstream_path,
        "traffic_access_token": traffic_access_token,
    }


def _assert_preview_scope_matches_session(payload: dict[str, Any], session: PublishedAppDraftDevSession) -> None:
    token_app_id = str(payload.get("app_id") or "").strip()
    token_revision_id = str(payload.get("revision_id") or "").strip()
    if token_app_id != str(session.published_app_id):
        raise HTTPException(status_code=403, detail="Preview token does not match draft session app scope")
    if session.revision_id and token_revision_id and token_revision_id != str(session.revision_id):
        raise HTTPException(status_code=403, detail="Preview token does not match draft session revision scope")


def _compose_upstream_path(*, path: str, target: dict[str, str]) -> str:
    base = str(target.get("upstream_path") or target.get("base_path") or "/").strip() or "/"
    if not base.startswith("/"):
        base = f"/{base}"
    if path:
        return f"{base.rstrip('/')}/{path.lstrip('/')}"
    return base


def _upstream_url(*, path: str, query_params: Any, target: dict[str, str]) -> str:
    forwarded_query = [
        (key, value)
        for key, value in query_params.multi_items()
        if str(key) != "runtime_token"
    ]
    query_string = urlencode(forwarded_query)
    parsed = urlparse(target["upstream_base_url"])
    updated = parsed._replace(path=_compose_upstream_path(path=path, target=target), query=query_string)
    return urlunparse(updated)


def _proxy_headers(request: Request, *, target: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in {"host", "content-length", "cookie"}:
            continue
        headers[key] = value
    if target["traffic_access_token"]:
        headers[PREVIEW_PROXY_HEADER] = target["traffic_access_token"]
    return headers


def _websocket_proxy_connect_options(
    websocket: WebSocket,
    *,
    target: dict[str, str],
) -> tuple[list[tuple[str, str]], list[str]]:
    additional_headers: list[tuple[str, str]] = []
    traffic_access_token = str(target.get("traffic_access_token") or "").strip()
    if traffic_access_token:
        additional_headers.append((PREVIEW_PROXY_HEADER, traffic_access_token))

    origin = str(websocket.headers.get("origin") or "").strip()
    if origin:
        additional_headers.append(("origin", origin))

    user_agent = str(websocket.headers.get("user-agent") or "").strip()
    if user_agent:
        additional_headers.append(("user-agent", user_agent))

    raw_protocol_headers = websocket.headers.getlist("sec-websocket-protocol")
    subprotocols: list[str] = []
    for header in raw_protocol_headers:
        for item in str(header or "").split(","):
            protocol = item.strip()
            if protocol and protocol not in subprotocols:
                subprotocols.append(protocol)

    return additional_headers, subprotocols


def _set_preview_cookie(response: Response, *, request: Request, token: str) -> None:
    response.set_cookie(
        key=PREVIEW_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


@router.api_route(
    "/public/apps-builder/draft-dev/sessions/{session_id}/preview/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_builder_preview(
    session_id: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    session = await _load_session(db=db, session_id=session_id)
    token = _extract_preview_token(request=request)
    if not token:
        raise HTTPException(status_code=401, detail="Preview authentication required")
    payload = _validate_preview_token(token)
    _assert_preview_scope_matches_session(payload, session)
    target = _resolve_preview_target(session)
    upstream_url = _upstream_url(
        path=path,
        query_params=request.query_params,
        target=target,
    )
    apps_builder_trace(
        "preview.proxy.requested",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        method=request.method,
        path=path,
        upstream_url=upstream_url,
    )
    body = await request.body()
    async with httpx.AsyncClient(follow_redirects=False, timeout=60.0) as client:
        upstream = await client.request(
            request.method,
            upstream_url,
            headers=_proxy_headers(request, target=target),
            content=body if body else None,
        )
    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
    for key, value in upstream.headers.items():
        if key.lower() in excluded_headers or key.lower() == "content-type":
            continue
        response.headers[key] = value
    if request.query_params.get("runtime_token"):
        _set_preview_cookie(response, request=request, token=token)
    apps_builder_trace(
        "preview.proxy.completed",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        method=request.method,
        path=path,
        status_code=upstream.status_code,
    )
    return response


@router.websocket("/public/apps-builder/draft-dev/sessions/{session_id}/preview/{path:path}")
async def proxy_builder_preview_websocket(
    websocket: WebSocket,
    session_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    session = await _load_session(db=db, session_id=session_id)
    token = _extract_preview_token(websocket=websocket)
    if not token:
        await websocket.close(code=4401)
        return
    payload = _validate_preview_token(token)
    _assert_preview_scope_matches_session(payload, session)
    target = _resolve_preview_target(session)
    apps_builder_trace(
        "preview.proxy.websocket_open",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        path=path,
    )
    upstream_url = _upstream_url(
        path=path,
        query_params=websocket.query_params,
        target=target,
    )
    parsed = urlparse(upstream_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = urlunparse(parsed._replace(scheme=ws_scheme))
    extra_headers, subprotocols = _websocket_proxy_connect_options(websocket, target=target)
    upstream = None
    try:
        last_exc: Exception | None = None
        for attempt in range(1, _PREVIEW_WEBSOCKET_CONNECT_ATTEMPTS + 1):
            try:
                upstream = await websockets.connect(
                    ws_url,
                    additional_headers=extra_headers,
                    subprotocols=subprotocols or None,
                    open_timeout=_PREVIEW_WEBSOCKET_OPEN_TIMEOUT_SECONDS,
                    close_timeout=5.0,
                    ping_interval=20.0,
                    ping_timeout=20.0,
                )
                break
            except Exception as exc:
                last_exc = exc
                apps_builder_trace(
                    "preview.proxy.websocket_retry",
                    domain="preview.proxy",
                    session_id=str(session.id),
                    app_id=str(session.published_app_id),
                    revision_id=str(session.revision_id or ""),
                    sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
                    path=path,
                    attempt=attempt,
                    max_attempts=_PREVIEW_WEBSOCKET_CONNECT_ATTEMPTS,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                if attempt >= _PREVIEW_WEBSOCKET_CONNECT_ATTEMPTS:
                    raise
                await asyncio.sleep(min(0.5 * attempt, 1.0))
        if upstream is None:
            raise RuntimeError(str(last_exc or "Failed to connect upstream preview websocket"))

        await websocket.accept(subprotocol=getattr(upstream, "subprotocol", None))
        try:
            async def _client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def _upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            client_task = asyncio.create_task(_client_to_upstream())
            upstream_task = asyncio.create_task(_upstream_to_client())
            done, pending = await asyncio.wait(
                {client_task, upstream_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
        finally:
            await upstream.close()
    except WebSocketDisconnect:
        apps_builder_trace(
            "preview.proxy.websocket_closed",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
            path=path,
            reason="client_disconnect",
        )
        return
    except Exception as exc:
        apps_builder_trace(
            "preview.proxy.websocket_failed",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
            path=path,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close(code=1011)
    else:
        apps_builder_trace(
            "preview.proxy.websocket_closed",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
            path=path,
            reason="completed",
        )
