from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

import httpx
import websockets
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.requests import ClientDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppDraftDevSession, PublishedAppRevision
from app.db.postgres.session import get_db
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_auth_service import (
    PublishedAppAuthError,
    PublishedAppAuthRateLimitError,
    PublishedAppAuthService,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClient
from app.services.published_app_sandbox_backend_factory import load_published_app_sandbox_backend_config
from app.services.published_app_sprite_proxy_tunnel import get_sprite_proxy_tunnel_manager
from app.services.runtime_attachment_service import RuntimeAttachmentOwner
from app.services.runtime_surface import (
    RuntimeEventView,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
    RuntimeThreadOptions,
)
from app.services.thread_detail_service import serialize_thread_summary

from .published_apps_host_runtime import (
    GOOGLE_OAUTH_STATE_COOKIE_NAME,
    INTERNAL_PREFIX,
    _clear_session_cookie,
    _clear_google_oauth_state_cookie,
    _normalize_return_to_for_host,
    _request_origin_from_base_url,
    _resolve_optional_principal_from_cookie,
    _set_google_oauth_state_cookie,
    _set_session_cookie,
    _user_payload,
)
from .published_apps_public import (
    PublicAuthExchangeRequest,
    PublicAuthRequest,
    PublicChatStreamRequest,
    RuntimeBootstrapAuthResponse,
    RuntimeBootstrapResponse,
    _inject_runtime_context_into_html,
    _is_enabled,
    _stream_chat_for_app,
    _upload_published_app_attachments,
)
from .published_apps_preview_auth import (
    PREVIEW_COOKIE_NAME,
    PREVIEW_TARGET_DRAFT_DEV_SESSION,
    clear_preview_cookie,
    decode_preview_token,
    resolve_preview_token,
    set_preview_cookie as _set_canonical_preview_cookie,
    token_matches_target,
)


router = APIRouter(tags=["published-apps-builder-preview-proxy"])

_PREVIEW_WEBSOCKET_OPEN_TIMEOUT_SECONDS = 20.0
_PREVIEW_WEBSOCKET_CONNECT_ATTEMPTS = 3
_PREVIEW_HTTP_RETRY_DELAYS_SECONDS = (0.0, 0.35, 0.75, 1.5)
_HTML_URL_ATTR_PATTERN = re.compile(r"""(?P<prefix>\b(?:src|href)=["'])(?P<path>/[^"'?#]+(?:[?#][^"']*)?)""")
_INLINE_VITE_PATH_PATTERN = re.compile(
    r"""(?P<quote>["'])(?P<path>/(?:@vite|@react-refresh|src/|node_modules/|runtime-sdk/|__vite)[^"']*)(?P=quote)"""
)
_CSS_URL_PATH_PATTERN = re.compile(
    r"""url\((?P<quote>["']?)(?P<path>/(?:@vite|@react-refresh|src/|node_modules/|runtime-sdk/|__vite)[^)"']*)(?P=quote)\)"""
)
_HMR_OWNER_PATH_PATTERN = re.compile(
    r'(?P<prefix>__vite__createHotContext\()'
    r'(?P<quote>["\'])'
    r'(?P<path>/public/apps-builder/draft-dev/sessions/[^"\']+/preview/(?P<owner>(?:src/|node_modules/|runtime-sdk/|__vite)[^"\')]*?))'
    r'(?:\?[^"\')]*)?'
    r'(?P=quote)'
    r'(?P<suffix>\))'
)
_REWRITABLE_TEXT_PREFIXES = ("text/html", "application/javascript", "text/javascript", "text/css")
_VITE_CLIENT_HMR_ASSIGNMENTS = re.compile(
    r'const serverHost = "(?P<server_host>[^"]*)";\s*'
    r'const socketProtocol = (?P<socket_protocol>.*?);\s*'
    r'const hmrPort = (?P<hmr_port>.*?);\s*'
    r'const socketHost = `(?P<socket_host>.*?)`;\s*'
    r'const directSocketHost = "(?P<direct_socket_host>[^"]*)";',
    re.DOTALL,
)
_VITE_CLIENT_BASE_ASSIGNMENT = re.compile(r"const base = .*?;", re.DOTALL)
_HTML_BODY_CLOSE_PATTERN = re.compile(r"</body\s*>", re.IGNORECASE)
_HTML_HEAD_CLOSE_PATTERN = re.compile(r"</head\s*>", re.IGNORECASE)


def _normalize_preview_route(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "/"
    path = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return "/"
    normalized = path if path.startswith("/") else f"/{path}"
    normalized = re.sub(r"/{2,}", "/", normalized)
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized or "/"


def _build_preview_path_shim(*, target: dict[str, str], preview_route: str) -> str:
    base_path = str(target.get("base_path") or "/").strip() or "/"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    normalized_base_path = base_path[:-1] if base_path.endswith("/") and base_path != "/" else base_path
    base_path_literal = json.dumps(normalized_base_path)
    preview_route_literal = json.dumps(_normalize_preview_route(preview_route))
    return (
        "<script>\n"
        "(function(){\n"
        "  if (window.__talmudpediaPreviewPathShimInstalled) return;\n"
        "  window.__talmudpediaPreviewPathShimInstalled = true;\n"
        f"  const previewBasePath = {base_path_literal};\n"
        f"  const initialPreviewRoute = {preview_route_literal};\n"
        "  window.__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH = previewBasePath;\n"
        "  const normalizeAppPath = (pathname) => {\n"
        "    const raw = String(pathname || '').trim();\n"
        "    if (!raw) return '/';\n"
        "    const normalized = raw.startsWith('/') ? raw : '/' + raw;\n"
        "    if (normalized !== '/' && normalized.endsWith('/')) return normalized.slice(0, -1) || '/';\n"
        "    return normalized || '/';\n"
        "  };\n"
        "  const currentPreviewRoute = () => {\n"
        "    try {\n"
        "      const current = new URL(window.location.href);\n"
        "      const queryRoute = current.searchParams.get('preview_route');\n"
        "      return normalizeAppPath(queryRoute || initialPreviewRoute || '/');\n"
        "    } catch {\n"
        "      return normalizeAppPath(initialPreviewRoute || '/');\n"
        "    }\n"
        "  };\n"
        "  const toProxyUrl = (value) => {\n"
        "    if (value == null || value === '') return value;\n"
        "    try {\n"
        "      const current = new URL(window.location.href);\n"
        "      const next = new URL(String(value), current);\n"
        "      if (next.origin !== current.origin) return value;\n"
        "      const nextRoute = normalizeAppPath(next.pathname || '/');\n"
        "      next.pathname = previewBasePath;\n"
        "      next.searchParams.set('preview_route', nextRoute);\n"
        "      return next.pathname + next.search + next.hash;\n"
        "    } catch {\n"
        "      return String(value);\n"
        "    }\n"
        "  };\n"
        "  try {\n"
        "    const proto = Object.getPrototypeOf(window.location);\n"
        "    const descriptor = Object.getOwnPropertyDescriptor(proto, 'pathname');\n"
        "    if (descriptor && descriptor.configurable && typeof descriptor.get === 'function') {\n"
        "      Object.defineProperty(proto, 'pathname', {\n"
        "        configurable: true,\n"
        "        enumerable: descriptor.enumerable,\n"
        "        get: function() {\n"
        "          return currentPreviewRoute();\n"
        "        },\n"
        "        set: typeof descriptor.set === 'function'\n"
        "          ? function(value) {\n"
        "              return descriptor.set.call(window.location, toProxyUrl(value));\n"
        "            }\n"
        "          : undefined,\n"
        "      });\n"
        "    }\n"
        "  } catch {}\n"
        "  try {\n"
        "    const assign = window.location.assign.bind(window.location);\n"
        "    const replace = window.location.replace.bind(window.location);\n"
        "    window.location.assign = function(value) { assign(toProxyUrl(value)); };\n"
        "    window.location.replace = function(value) { replace(toProxyUrl(value)); };\n"
        "  } catch {}\n"
        "  for (const methodName of ['pushState', 'replaceState']) {\n"
        "    const original = window.history[methodName];\n"
        "    if (typeof original !== 'function') continue;\n"
        "    window.history[methodName] = function(state, unused, url) {\n"
        "      const nextUrl = typeof url === 'string' || url instanceof URL ? toProxyUrl(url) : url;\n"
        "      return original.call(this, state, unused, nextUrl);\n"
        "    };\n"
        "  }\n"
        "})();\n"
        "</script>\n"
    )


def _inject_preview_path_shim(*, html: str, target: dict[str, str], preview_route: str) -> str:
    if "__talmudpediaPreviewPathShimInstalled" in html:
        return html
    shim = _build_preview_path_shim(target=target, preview_route=preview_route)
    if _HTML_HEAD_CLOSE_PATTERN.search(html):
        return _HTML_HEAD_CLOSE_PATTERN.sub(lambda _match: f"{shim}</head>", html, count=1)
    if _HTML_BODY_CLOSE_PATTERN.search(html):
        return _HTML_BODY_CLOSE_PATTERN.sub(lambda _match: f"{shim}</body>", html, count=1)
    return shim + html


def _build_preview_debug_probe(*, runtime_token: str | None) -> str:
    token_literal = json.dumps(str(runtime_token or "").strip() or None)
    return (
        "<script>\n"
        "(function(){\n"
        "  if (window.__talmudpediaPreviewDebugInstalled) return;\n"
        "  window.__talmudpediaPreviewDebugInstalled = true;\n"
        f"  const runtimeToken = {token_literal};\n"
        "  const bridgeType = 'talmudpedia.preview-debug.v1';\n"
        "  const bodyTextSnippet = () => {\n"
        "    try {\n"
        "      return String((document && document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 220);\n"
        "    } catch {\n"
        "      return '';\n"
        "    }\n"
        "  };\n"
        "  const log = (event, fields) => {\n"
        "    try {\n"
        "      const payload = Object.assign({ event, runtimeTokenPresent: Boolean(runtimeToken), href: String(window.location.href || '') }, fields || {});\n"
        "      console.info('[apps-builder][iframe]', payload);\n"
        "      if (window.parent && window.parent !== window) {\n"
        "        window.parent.postMessage({ type: bridgeType, payload }, '*');\n"
        "      }\n"
        "    } catch {}\n"
        "  };\n"
        "  const normalizeUpdate = (payload) => {\n"
        "    const updates = Array.isArray(payload && payload.updates) ? payload.updates : [];\n"
        "    return updates.slice(0, 10).map((item) => item && typeof item === 'object' ? String(item.path || '') : '').filter(Boolean);\n"
        "  };\n"
        "  window.addEventListener('vite:beforeUpdate', (event) => {\n"
        "    log('vite.beforeUpdate', { type: event && event.type, paths: normalizeUpdate(event && event.detail), bodyText: bodyTextSnippet() });\n"
        "  });\n"
        "  window.addEventListener('vite:afterUpdate', (event) => {\n"
        "    window.setTimeout(() => {\n"
        "      log('vite.afterUpdate', { type: event && event.type, paths: normalizeUpdate(event && event.detail), bodyText: bodyTextSnippet() });\n"
        "    }, 0);\n"
        "  });\n"
        "  window.addEventListener('vite:beforeFullReload', (event) => {\n"
        "    log('vite.beforeFullReload', { type: event && event.type, path: String((event && event.detail && event.detail.path) || ''), bodyText: bodyTextSnippet() });\n"
        "  });\n"
        "  window.addEventListener('vite:error', (event) => {\n"
        "    const detail = event && event.detail;\n"
        "    log('vite.error', {\n"
        "      type: event && event.type,\n"
        "      message: detail && typeof detail === 'object' ? String(detail.message || '') : String(detail || ''),\n"
        "      plugin: detail && typeof detail === 'object' ? String(detail.plugin || '') : '',\n"
        "      id: detail && typeof detail === 'object' ? String(detail.id || '') : '',\n"
        "    });\n"
        "  });\n"
        "  window.addEventListener('error', (event) => {\n"
        "    log('window.error', {\n"
        "      message: String((event && event.message) || ''),\n"
        "      filename: String((event && event.filename) || ''),\n"
        "      lineno: Number((event && event.lineno) || 0),\n"
        "      colno: Number((event && event.colno) || 0),\n"
        "    });\n"
        "  });\n"
        "  window.addEventListener('unhandledrejection', (event) => {\n"
        "    const reason = event && event.reason;\n"
        "    log('window.unhandledrejection', {\n"
        "      reason: typeof reason === 'string' ? reason : String((reason && reason.message) || reason || ''),\n"
        "    });\n"
        "  });\n"
        "  log('probe.installed', { readyState: document.readyState, bodyText: bodyTextSnippet() });\n"
        "})();\n"
        "</script>\n"
    )


def _inject_preview_debug_probe(*, html: str, runtime_token: str | None) -> str:
    probe = _build_preview_debug_probe(runtime_token=runtime_token)
    if "__talmudpediaPreviewDebugInstalled" in html:
        return html
    if _HTML_BODY_CLOSE_PATTERN.search(html):
        return _HTML_BODY_CLOSE_PATTERN.sub(lambda _match: f"{probe}</body>", html, count=1)
    if _HTML_HEAD_CLOSE_PATTERN.search(html):
        return _HTML_HEAD_CLOSE_PATTERN.sub(lambda _match: f"{probe}</head>", html, count=1)
    return html + probe


def _preview_body_probe(content: bytes, *, content_type: str) -> dict[str, Any]:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type not in {"text/html", "application/javascript", "text/javascript"}:
        return {"content_type": normalized_content_type, "probeable": False}
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        return {"content_type": normalized_content_type, "probeable": False}
    head = text[:240]
    hmr_snippet = None
    if "@vite/client" in text or "vite-hmr" in text:
        markers = [
            "const serverHost",
            "const socketProtocol",
            "const socketHost",
            "const directSocketHost",
            "const previewRuntimeToken",
            "new WebSocket",
        ]
        positions = [text.find(marker) for marker in markers if text.find(marker) >= 0]
        if positions:
            start = max(0, min(positions) - 80)
            hmr_snippet = text[start : start + 900]
    hot_context_snippet = None
    hot_context_index = text.find("__vite__createHotContext(")
    if hot_context_index >= 0:
        hot_context_snippet = text[hot_context_index : hot_context_index + 260]
    return {
        "content_type": normalized_content_type,
        "probeable": True,
        "head": head,
        "hmr_snippet": hmr_snippet,
        "contains_vite_client": "@vite/client" in text,
        "contains_vite_hmr_create": "__vite__createHotContext" in text,
        "contains_hashed_assets": bool(re.search(r"/?assets/[^\"'\\s>]+-[A-Za-z0-9_-]{6,}\\.(?:js|css)", text)),
        "contains_runtime_token": "runtime_token" in text,
        "contains_preview_debug_probe": "__talmudpediaPreviewDebugInstalled" in text,
        "contains_preview_iframe_log": "[apps-builder][iframe]" in text,
        "hot_context_snippet": hot_context_snippet,
    }


def _summarize_websocket_message(message: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {"message_kind": "unknown"}
    if isinstance(message, bytes):
        summary["message_kind"] = "bytes"
        summary["size"] = len(message)
        return summary
    if not isinstance(message, str):
        summary["message_kind"] = type(message).__name__
        return summary
    summary["message_kind"] = "text"
    summary["size"] = len(message)
    text = message.strip()
    if not text:
        summary["text_kind"] = "empty"
        return summary
    try:
        payload = json.loads(text)
    except Exception:
        summary["text_kind"] = "raw"
        summary["head"] = text[:240]
        return summary
    if isinstance(payload, dict):
        summary["text_kind"] = "json"
        summary["payload_type"] = str(payload.get("type") or "")
        updates = payload.get("updates")
        if isinstance(updates, list):
            summary["update_count"] = len(updates)
            summary["update_paths"] = [
                str(item.get("path") or "")
                for item in updates[:8]
                if isinstance(item, dict) and str(item.get("path") or "").strip()
            ]
        summary["keys"] = sorted(str(key) for key in payload.keys())[:10]
        return summary
    summary["text_kind"] = type(payload).__name__
    return summary


async def _close_websocket_if_possible(
    websocket: WebSocket,
    *,
    code: int = 1011,
    accepted: bool = False,
) -> None:
    if not accepted:
        return
    if getattr(websocket, "application_state", None) == WebSocketState.DISCONNECTED:
        return
    if getattr(websocket, "client_state", None) == WebSocketState.DISCONNECTED:
        return
    await websocket.close(code=code)


def _should_retry_preview_request(*, method: str, status_code: int | None = None, error: Exception | None = None) -> bool:
    if str(method or "").upper() not in {"GET", "HEAD"}:
        return False
    if error is not None:
        return isinstance(error, httpx.HTTPError)
    return int(status_code or 0) in {404, 408, 425, 429, 500, 502, 503, 504}


def _extract_preview_token(*, request: Request | None = None, websocket: WebSocket | None = None) -> str | None:
    query_params = request.query_params if request is not None else websocket.query_params
    cookies = request.cookies if request is not None else websocket.cookies
    cookie_token = str(cookies.get(PREVIEW_COOKIE_NAME) or "").strip()
    if cookie_token:
        return cookie_token
    query_token = str(query_params.get("runtime_token") or "").strip()
    if query_token:
        return query_token
    return None


def _resolve_preview_token_for_session(
    *,
    session: PublishedAppDraftDevSession,
    request: Request | None = None,
    websocket: WebSocket | None = None,
) -> tuple[str, dict[str, Any], str]:
    if request is not None:
        return resolve_preview_token(
            request=request,
            matcher=lambda payload: token_matches_target(
                payload,
                app_id=str(session.published_app_id),
                preview_target_type=PREVIEW_TARGET_DRAFT_DEV_SESSION,
                preview_target_id=str(session.id),
                revision_id=str(session.revision_id) if session.revision_id else None,
            ),
        )
    query_params = websocket.query_params
    cookies = websocket.cookies
    first_auth_error: HTTPException | None = None
    scope_mismatch_seen = False
    for source, token in (
        ("cookie", str(cookies.get(PREVIEW_COOKIE_NAME) or "").strip()),
        ("query", str(query_params.get("runtime_token") or "").strip()),
    ):
        if not token:
            continue
        try:
            payload = decode_preview_token(token)
        except HTTPException as exc:
            if first_auth_error is None:
                first_auth_error = exc
            continue
        if not token_matches_target(
            payload,
            app_id=str(session.published_app_id),
            preview_target_type=PREVIEW_TARGET_DRAFT_DEV_SESSION,
            preview_target_id=str(session.id),
            revision_id=str(session.revision_id) if session.revision_id else None,
        ):
            scope_mismatch_seen = True
            continue
        return token, payload, source
    if first_auth_error is not None:
        raise first_auth_error
    if scope_mismatch_seen:
        raise HTTPException(status_code=403, detail="Preview token does not match preview target scope")
    raise HTTPException(status_code=401, detail="Preview authentication required")


async def _load_session(*, db: AsyncSession, session_id: str) -> PublishedAppDraftDevSession:
    try:
        session_uuid = UUID(str(session_id))
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Draft dev session not found") from exc
    result = await db.execute(
        select(PublishedAppDraftDevSession)
        .options(selectinload(PublishedAppDraftDevSession.draft_workspace))
        .where(PublishedAppDraftDevSession.id == session_uuid)
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    return session


async def _touch_preview_session_activity(
    *,
    db: AsyncSession,
    session: PublishedAppDraftDevSession,
    reason: str,
    throttle_seconds: int = 30,
) -> None:
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    touched = await runtime_service.touch_session_activity(
        session=session,
        throttle_seconds=throttle_seconds,
    )
    if not touched:
        return
    await db.commit()
    apps_builder_trace(
        "preview.proxy.session_activity_touched",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        reason=reason,
    )


async def _load_preview_app_and_revision(
    *,
    db: AsyncSession,
    session: PublishedAppDraftDevSession,
) -> tuple[PublishedApp, PublishedAppRevision]:
    app = await db.get(PublishedApp, session.published_app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    revision_id = session.revision_id
    if revision_id is None:
        raise HTTPException(status_code=404, detail="Preview revision not found")
    revision = await db.get(PublishedAppRevision, revision_id)
    if revision is None or str(revision.published_app_id) != str(app.id):
        raise HTTPException(status_code=404, detail="Preview revision not found")
    return app, revision


def _builder_preview_internal_prefix(*, session_id: str) -> str:
    return f"/public/apps-builder/draft-dev/sessions/{session_id}/preview{INTERNAL_PREFIX}"


def _build_builder_preview_bootstrap(
    *,
    request: Request,
    session: PublishedAppDraftDevSession,
    app: PublishedApp,
    revision: PublishedAppRevision,
) -> RuntimeBootstrapResponse:
    origin = _request_origin_from_base_url(str(request.base_url))
    internal_prefix = _builder_preview_internal_prefix(session_id=str(session.id))
    return RuntimeBootstrapResponse(
        app_id=str(app.id),
        public_id=app.public_id,
        revision_id=str(revision.id),
        mode="builder-preview",
        api_base_path="/",
        api_base_url=origin,
        chat_stream_path=f"{internal_prefix}/chat/stream",
        chat_stream_url=f"{origin}{internal_prefix}/chat/stream",
        auth=RuntimeBootstrapAuthResponse(
            enabled=bool(app.auth_enabled),
            providers=list(app.auth_providers or []),
            exchange_enabled=bool(app.external_auth_oidc),
        ),
    )


def _preview_request_kind(path: str) -> str:
    normalized = str(path or "").strip().lstrip("/")
    if not normalized:
        return "document"
    if normalized == "_talmudpedia/status":
        return "status"
    if normalized == "_talmudpedia/runtime/bootstrap":
        return "runtime_bootstrap"
    if normalized == "_talmudpedia/chat/stream":
        return "chat_stream"
    if normalized == "_talmudpedia/auth/state":
        return "auth_state"
    if normalized.startswith("assets/"):
        return "asset"
    if normalized.endswith(".css"):
        return "css_asset"
    return "other"


async def _resolve_preview_target(session: PublishedAppDraftDevSession) -> dict[str, str]:
    workspace = getattr(session, "draft_workspace", None)
    workspace_metadata = getattr(workspace, "backend_metadata", None)
    metadata = (
        workspace_metadata
        if isinstance(workspace_metadata, dict)
        else session.backend_metadata
        if isinstance(session.backend_metadata, dict)
        else {}
    )
    preview = metadata.get("preview") if isinstance(metadata.get("preview"), dict) else {}
    workspace_state = metadata.get("workspace") if isinstance(metadata.get("workspace"), dict) else {}
    services = metadata.get("services") if isinstance(metadata.get("services"), dict) else {}
    provider = str(metadata.get("provider") or getattr(session, "runtime_backend", None) or "").strip().lower()
    sprite_name = str(workspace_state.get("sprite_name") or getattr(session, "sandbox_id", None) or "").strip()
    preview_port = services.get("preview_port")
    if provider == "sprite" and sprite_name and preview_port:
        config = load_published_app_sandbox_backend_config()
        tunnel_base_url = await get_sprite_proxy_tunnel_manager().ensure_tunnel(
            api_base_url=config.sprite_api_base_url,
            api_token=str(config.sprite_api_token or "").strip(),
            sprite_name=sprite_name,
            remote_host="127.0.0.1",
            remote_port=int(preview_port),
        )
        return {
            "upstream_base_url": tunnel_base_url.rstrip("/"),
            "base_path": str(preview.get("base_path") or "").strip() or "/",
            "upstream_path": "/",
            "auth_header_name": "Authorization",
            "auth_token": "",
            "auth_token_prefix": "",
            "extra_headers": json.dumps({}, sort_keys=True),
            "resolver_kind": "sprite_tunnel",
            "provider": provider or "sprite",
        }
    if provider == "sprite" and sprite_name:
        config = load_published_app_sandbox_backend_config()
        effective_preview_port = int(preview_port or config.sprite_preview_port or 8080)
        tunnel_base_url = await get_sprite_proxy_tunnel_manager().ensure_tunnel(
            api_base_url=config.sprite_api_base_url,
            api_token=str(config.sprite_api_token or "").strip(),
            sprite_name=sprite_name,
            remote_host="127.0.0.1",
            remote_port=effective_preview_port,
        )
        return {
            "upstream_base_url": tunnel_base_url.rstrip("/"),
            "base_path": str(preview.get("base_path") or PublishedAppDraftDevRuntimeClient.from_env().build_preview_proxy_path(str(session.id))).strip() or "/",
            "upstream_path": "/",
            "auth_header_name": "Authorization",
            "auth_token": "",
            "auth_token_prefix": "",
            "extra_headers": json.dumps({}, sort_keys=True),
            "resolver_kind": "sprite_tunnel_fallback",
            "provider": "sprite",
        }
    upstream_base_url = str(preview.get("upstream_base_url") or "").strip()
    if not upstream_base_url:
        raise HTTPException(status_code=404, detail="Draft dev preview target is unavailable")
    base_path = str(preview.get("base_path") or "").strip() or "/"
    upstream_path = str(preview.get("upstream_path") or "").strip() or base_path
    auth_header_name = str(preview.get("auth_header_name") or "").strip() or "Authorization"
    auth_token_env = str(preview.get("auth_token_env") or "").strip()
    auth_token_prefix_value = preview.get("auth_token_prefix")
    auth_token_prefix = str(auth_token_prefix_value) if auth_token_prefix_value is not None else ""
    auth_token = str(os.getenv(auth_token_env) or "").strip() if auth_token_env else ""
    extra_headers = preview.get("extra_headers") if isinstance(preview.get("extra_headers"), dict) else {}
    return {
        "upstream_base_url": upstream_base_url.rstrip("/"),
        "base_path": base_path,
        "upstream_path": upstream_path,
        "auth_header_name": auth_header_name,
        "auth_token": auth_token,
        "auth_token_prefix": auth_token_prefix,
        "extra_headers": json.dumps(extra_headers, sort_keys=True),
        "resolver_kind": "workspace_preview",
        "provider": provider or "unknown",
    }


def _is_refreshable_preview_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.RemoteProtocolError):
        return True
    message = str(exc or "").lower()
    return "certificate verify failed" in message or "hostname mismatch" in message


def _merge_preview_base_path(*, target: dict[str, str], session_id: str) -> str:
    base_path = str(target.get("base_path") or "").strip()
    if base_path:
        return base_path
    return PublishedAppDraftDevRuntimeClient.from_env().build_preview_proxy_path(session_id)


async def _refresh_preview_target(
    *,
    db: AsyncSession,
    session: PublishedAppDraftDevSession,
    current_target: dict[str, str],
) -> dict[str, str] | None:
    _ = db
    refreshed_target = await _resolve_preview_target(session)
    if refreshed_target is None or refreshed_target == current_target:
        return None
    apps_builder_trace(
        "preview.proxy.refreshed",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or "") or None,
        upstream_base_url=str(refreshed_target.get("upstream_base_url") or ""),
        refresh_source="stored_metadata",
    )
    return refreshed_target


async def _request_preview_upstream(
    *,
    request: Request,
    upstream_url: str,
    target: dict[str, str],
    body: bytes,
) -> httpx.Response:
    started_at = time.perf_counter()
    async with httpx.AsyncClient(follow_redirects=False, timeout=60.0) as client:
        upstream = None
        last_error: httpx.HTTPError | None = None
        attempt_count = 0
        for delay in _PREVIEW_HTTP_RETRY_DELAYS_SECONDS:
            attempt_count += 1
            if delay > 0:
                await asyncio.sleep(delay)
            attempt_started_at = time.perf_counter()
            try:
                candidate = await client.request(
                    request.method,
                    upstream_url,
                    headers=_proxy_headers(request, target=target),
                    content=body if body else None,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                apps_builder_trace(
                    "preview.proxy.upstream_attempt",
                    domain="preview.proxy",
                    method=request.method,
                    upstream_url=upstream_url,
                    attempt=attempt_count,
                    delay_ms=int(delay * 1000),
                    duration_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                    retryable=_should_retry_preview_request(method=request.method, error=exc),
                )
                if _is_refreshable_preview_error(exc):
                    raise
                if _should_retry_preview_request(method=request.method, error=exc):
                    continue
                raise
            apps_builder_trace(
                "preview.proxy.upstream_attempt",
                domain="preview.proxy",
                method=request.method,
                upstream_url=upstream_url,
                attempt=attempt_count,
                delay_ms=int(delay * 1000),
                duration_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                status_code=candidate.status_code,
                retryable=_should_retry_preview_request(method=request.method, status_code=candidate.status_code),
            )
            if _should_retry_preview_request(method=request.method, status_code=candidate.status_code):
                upstream = candidate
                continue
            upstream = candidate
            break
        if upstream is None:
            if last_error is not None:
                raise last_error
            raise HTTPException(status_code=502, detail="Draft dev preview upstream request failed")
        probe = _preview_body_probe(upstream.content, content_type=str(upstream.headers.get("content-type") or ""))
    apps_builder_trace(
        "preview.proxy.upstream_response",
        domain="preview.proxy",
        method=request.method,
        upstream_url=upstream_url,
        attempt_count=attempt_count,
        total_duration_ms=int((time.perf_counter() - started_at) * 1000),
        status_code=upstream.status_code,
        content_security_policy=str(upstream.headers.get("content-security-policy") or ""),
        x_frame_options=str(upstream.headers.get("x-frame-options") or ""),
        **probe,
    )
    return upstream


def _preview_rewrite_summary(
    *,
    path: str,
    content_type: str,
    original_content: bytes,
    rewritten_content: bytes,
    runtime_context: RuntimeBootstrapResponse | None,
) -> dict[str, Any]:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    text = ""
    try:
        text = rewritten_content.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    return {
        "request_kind": _preview_request_kind(path),
        "content_type": normalized_content_type,
        "byte_delta": len(rewritten_content) - len(original_content),
        "contains_preview_path_shim": "__talmudpediaPreviewPathShimInstalled" in text,
        "contains_preview_base_path_global": "__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH" in text,
        "contains_preview_debug_probe": "__talmudpediaPreviewDebugInstalled" in text,
        "contains_proxy_vite_client_path": "/preview/@vite/client" in text,
        "contains_proxy_src_path": "/preview/src/" in text,
        "contains_runtime_bootstrap_path": "/_talmudpedia/runtime/bootstrap" in text,
        "contains_runtime_context": bool(runtime_context and "/_talmudpedia/chat/stream" in text),
    }


def _assert_preview_scope_matches_session(payload: dict[str, Any], session: PublishedAppDraftDevSession) -> None:
    if not token_matches_target(
        payload,
        app_id=str(session.published_app_id),
        preview_target_type=PREVIEW_TARGET_DRAFT_DEV_SESSION,
        preview_target_id=str(session.id),
        revision_id=str(session.revision_id) if session.revision_id else None,
    ):
        raise HTTPException(status_code=403, detail="Preview token does not match preview target scope")


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
        if str(key) not in {"runtime_token", "runtime_base_path", "preview_route", "__reload"}
    ]
    query_string = urlencode(forwarded_query)
    parsed = urlparse(target["upstream_base_url"])
    updated = parsed._replace(path=_compose_upstream_path(path=path, target=target), query=query_string)
    return urlunparse(updated)


def _compose_proxy_path(*, target: dict[str, str], resource_path: str) -> str:
    base_path = str(target.get("base_path") or "/").strip() or "/"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    return f"{base_path.rstrip('/')}/{str(resource_path or '').lstrip('/')}"

def _rewrite_inline_vite_paths(*, target: dict[str, str], text: str, runtime_token: str | None) -> str:
    def _replace_inline(match: re.Match[str]) -> str:
        quote = str(match.group("quote") or '"')
        original = str(match.group("path") or "")
        if original.startswith("//"):
            return match.group(0)
        rewritten = _compose_proxy_path(target=target, resource_path=original)
        return f"{quote}{rewritten}{quote}"

    return _INLINE_VITE_PATH_PATTERN.sub(_replace_inline, text)


def _rewrite_css_url_paths(*, target: dict[str, str], text: str, runtime_token: str | None) -> str:
    def _replace_css_url(match: re.Match[str]) -> str:
        quote = str(match.group("quote") or "")
        original = str(match.group("path") or "")
        if original.startswith("//"):
            return match.group(0)
        rewritten = _compose_proxy_path(target=target, resource_path=original)
        return f"url({quote}{rewritten}{quote})"

    return _CSS_URL_PATH_PATTERN.sub(_replace_css_url, text)


def _rewrite_vite_client_hmr_runtime(*, target: dict[str, str], text: str, runtime_token: str | None) -> str:
    base_path = str(target.get("base_path") or "/").strip() or "/"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    if not base_path.endswith("/"):
        base_path = f"{base_path}/"

    replacement = (
        'const serverHost = `${importMetaUrl.host}' + base_path + '`;\n'
        'const socketProtocol = importMetaUrl.protocol === "https:" ? "wss" : "ws";\n'
        "const hmrPort = null;\n"
        'const socketHost = `${importMetaUrl.host}' + base_path + '`;\n'
        'const directSocketHost = `${importMetaUrl.host}' + base_path + '`;'
    )
    rewritten = _VITE_CLIENT_HMR_ASSIGNMENTS.sub(replacement, text, count=1)
    rewritten = _VITE_CLIENT_BASE_ASSIGNMENT.sub(f"const base = {json.dumps(base_path)};", rewritten, count=1)
    rewritten = re.sub(
        r'(const wsToken = .*?;\n)',
        r"\1"
        'const previewBridgeType = "talmudpedia.preview-debug.v1";\n'
        "const __previewHmrLog = (event, fields = {}) => {\n"
        "\ttry {\n"
        "\t\tconst payload = Object.assign({ event, href: String((typeof location !== \"undefined\" && location.href) || \"\") }, fields || {});\n"
        "\t\tconsole.info(\"[apps-builder][iframe]\", payload);\n"
        "\t\tif (typeof window !== \"undefined\" && window.parent && window.parent !== window) {\n"
        "\t\t\twindow.parent.postMessage({ type: previewBridgeType, payload }, \"*\");\n"
        "\t\t}\n"
        "\t} catch {}\n"
        "};\n",
        rewritten,
        count=1,
    )
    rewritten = rewritten.replace(
        'createConnection: () => new WebSocket(`${socketProtocol}://${socketHost}?token=${wsToken}`, "vite-hmr"),',
        'createConnection: () => (__previewHmrLog("vite.client.websocket_create", { mode: "primary", url: `${socketProtocol}://${socketHost}?token=${wsToken}` }), new WebSocket(`${socketProtocol}://${socketHost}?token=${wsToken}`, "vite-hmr")),',
    )
    rewritten = rewritten.replace(
        'createConnection: () => new WebSocket(`${socketProtocol}://${directSocketHost}?token=${wsToken}`, "vite-hmr"),',
        'createConnection: () => (__previewHmrLog("vite.client.websocket_create", { mode: "fallback", url: `${socketProtocol}://${directSocketHost}?token=${wsToken}` }), new WebSocket(`${socketProtocol}://${directSocketHost}?token=${wsToken}`, "vite-hmr")),',
    )
    rewritten = rewritten.replace(
        "queueUpdate(payload) {\n"
        "\t\tthis.updateQueue.push(this.fetchUpdate(payload));\n",
        "queueUpdate(payload) {\n"
        '\t\t__previewHmrLog("vite.client.queueUpdate", { path: String((payload && payload.path) || ""), acceptedPath: String((payload && payload.acceptedPath) || ""), type: String((payload && payload.type) || "") });\n'
        "\t\tthis.updateQueue.push(this.fetchUpdate(payload));\n",
    )
    rewritten = rewritten.replace(
        "async fetchUpdate(update) {\n"
        "\t\tconst { path, acceptedPath, firstInvalidatedBy } = update;\n",
        "async fetchUpdate(update) {\n"
        "\t\tconst { path, acceptedPath, firstInvalidatedBy } = update;\n"
        '\t\t__previewHmrLog("vite.client.fetchUpdate.begin", { path: String(path || ""), acceptedPath: String(acceptedPath || ""), firstInvalidatedBy: String(firstInvalidatedBy || "") });\n',
    )
    rewritten = rewritten.replace(
        "\t\tconst mod = this.hotModulesMap.get(path);\n"
        "\t\tif (!mod) return;\n",
        "\t\tconst mod = this.hotModulesMap.get(path);\n"
        '\t\tif (!mod) {\n'
        '\t\t\t__previewHmrLog("vite.client.fetchUpdate.no_module", { path: String(path || ""), acceptedPath: String(acceptedPath || "") });\n'
        "\t\t\treturn;\n"
        "\t\t}\n",
    )
    rewritten = rewritten.replace(
        "\t\t\ttry {\n"
        "\t\t\t\tfetchedModule = await this.importUpdatedModule(update);\n"
        "\t\t\t} catch (e) {\n"
        "\t\t\t\tthis.warnFailedUpdate(e, acceptedPath);\n"
        "\t\t\t}\n",
        "\t\t\ttry {\n"
        '\t\t\t\t__previewHmrLog("vite.client.fetchUpdate.import_begin", { path: String(path || ""), acceptedPath: String(acceptedPath || "") });\n'
        "\t\t\t\tfetchedModule = await this.importUpdatedModule(update);\n"
        '\t\t\t\t__previewHmrLog("vite.client.fetchUpdate.import_done", { path: String(path || ""), acceptedPath: String(acceptedPath || ""), fetched: Boolean(fetchedModule) });\n'
        "\t\t\t} catch (e) {\n"
        '\t\t\t\t__previewHmrLog("vite.client.fetchUpdate.import_error", { path: String(path || ""), acceptedPath: String(acceptedPath || ""), message: String((e && e.message) || e || "") });\n'
        "\t\t\t\tthis.warnFailedUpdate(e, acceptedPath);\n"
        "\t\t\t}\n",
    )
    rewritten = rewritten.replace(
        "\t\treturn () => {\n"
        "\t\t\ttry {\n",
        "\t\treturn () => {\n"
        "\t\t\ttry {\n"
        '\t\t\t\t__previewHmrLog("vite.client.fetchUpdate.apply_begin", { path: String(path || ""), acceptedPath: String(acceptedPath || ""), callbackCount: qualifiedCallbacks.length, isSelfUpdate: Boolean(isSelfUpdate) });\n',
    )
    rewritten = rewritten.replace(
        '\t\t\t\tthis.logger.debug(`hot updated: ${loggedPath}`);\n',
        '\t\t\t\tthis.logger.debug(`hot updated: ${loggedPath}`);\n'
        '\t\t\t\t__previewHmrLog("vite.client.fetchUpdate.apply_done", { loggedPath: String(loggedPath || "") });\n',
    )
    rewritten = rewritten.replace(
        "function handleMessage(payload) {\n"
        "\tswitch (payload.type) {\n",
        "function handleMessage(payload) {\n"
        '\t__previewHmrLog("vite.client.handleMessage", { type: String((payload && payload.type) || ""), updatePaths: Array.isArray(payload && payload.updates) ? payload.updates.map((item) => String((item && item.path) || "")).filter(Boolean).slice(0, 12) : [] });\n'
        "\tswitch (payload.type) {\n",
    )
    rewritten = rewritten.replace(
        '\t\t\tawait Promise.all(payload.updates.map(async (update) => {\n'
        '\t\t\t\tif (update.type === "js-update") return hmrClient.queueUpdate(update);\n',
        '\t\t\tawait Promise.all(payload.updates.map(async (update) => {\n'
        '\t\t\t\tif (update.type === "js-update") return hmrClient.queueUpdate(update);\n'
        '\t\t\t\t__previewHmrLog("vite.client.cssUpdate.begin", { path: String((update && update.path) || ""), type: String((update && update.type) || "") });\n',
    )
    rewritten = rewritten.replace(
        "\t\t\t\tconst el = Array.from(document.querySelectorAll(\"link\")).find((e) => !outdatedLinkTags.has(e) && cleanUrl(e.href).includes(searchUrl));\n"
        "\t\t\t\tif (!el) return;\n",
        "\t\t\t\tconst el = Array.from(document.querySelectorAll(\"link\")).find((e) => !outdatedLinkTags.has(e) && cleanUrl(e.href).includes(searchUrl));\n"
        '\t\t\t\tif (!el) {\n'
        '\t\t\t\t\t__previewHmrLog("vite.client.cssUpdate.no_link", { path: String(path || ""), searchUrl: String(searchUrl || "") });\n'
        "\t\t\t\t\treturn;\n"
        "\t\t\t\t}\n",
    )
    rewritten = rewritten.replace(
        "\t\t\t\t\tconst newLinkTag = el.cloneNode();\n"
        "\t\t\t\t\tnewLinkTag.href = new URL(newPath, el.href).href;\n",
        "\t\t\t\t\tconst newLinkTag = el.cloneNode();\n"
        "\t\t\t\t\tnewLinkTag.href = new URL(newPath, el.href).href;\n"
        '\t\t\t\t\t__previewHmrLog("vite.client.cssUpdate.link_prepared", { path: String(path || ""), newHref: String(newLinkTag.href || ""), oldHref: String(el.href || "") });\n',
    )
    rewritten = rewritten.replace(
        "\t\t\t\t\tconst removeOldEl = () => {\n"
        "\t\t\t\t\t\tel.remove();\n"
        "\t\t\t\t\t\tconsole.debug(`[vite] css hot updated: ${searchUrl}`);\n"
        "\t\t\t\t\t\tresolve();\n"
        "\t\t\t\t\t};\n",
        "\t\t\t\t\tconst removeOldEl = () => {\n"
        "\t\t\t\t\t\tel.remove();\n"
        "\t\t\t\t\t\tconsole.debug(`[vite] css hot updated: ${searchUrl}`);\n"
        '\t\t\t\t\t\t__previewHmrLog("vite.client.cssUpdate.swap_done", { path: String(path || ""), searchUrl: String(searchUrl || ""), href: String(newLinkTag.href || "") });\n'
        "\t\t\t\t\t\tresolve();\n"
        "\t\t\t\t\t};\n",
    )
    rewritten = rewritten.replace(
        "\t\t\t\t\tnewLinkTag.addEventListener(\"load\", removeOldEl);\n"
        "\t\t\t\t\tnewLinkTag.addEventListener(\"error\", removeOldEl);\n",
        "\t\t\t\t\tnewLinkTag.addEventListener(\"load\", removeOldEl);\n"
        '\t\t\t\t\tnewLinkTag.addEventListener("error", () => {\n'
        '\t\t\t\t\t\t__previewHmrLog("vite.client.cssUpdate.link_error", { path: String(path || ""), href: String(newLinkTag.href || "") });\n'
        "\t\t\t\t\t\tremoveOldEl();\n"
        "\t\t\t\t\t});\n",
    )
    return rewritten


def _restore_hmr_owner_paths(*, text: str) -> str:
    def _replace_owner(match: re.Match[str]) -> str:
        prefix = str(match.group("prefix") or "")
        quote = str(match.group("quote") or '"')
        owner = str(match.group("owner") or "")
        suffix = str(match.group("suffix") or "")
        return f"{prefix}{quote}/{owner}{quote}{suffix}"

    return _HMR_OWNER_PATH_PATTERN.sub(_replace_owner, text)


def _rewrite_html_preview_content(
    *,
    target: dict[str, str],
    content: bytes,
    runtime_token: str | None,
    runtime_context: RuntimeBootstrapResponse | None,
    preview_route: str,
) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    rewritten = text
    if runtime_context is not None:
        rewritten = _inject_runtime_context_into_html(rewritten, runtime_context)
    rewritten = _inject_preview_path_shim(html=rewritten, target=target, preview_route=preview_route)
    return rewritten.encode("utf-8")


def _rewrite_text_preview_content(
    *,
    target: dict[str, str],
    path: str,
    content_type: str,
    content: bytes,
    runtime_token: str | None,
    runtime_context: RuntimeBootstrapResponse | None,
    preview_route: str,
) -> tuple[bytes, bool]:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type != "text/html":
        return content, False
    rewritten = _rewrite_html_preview_content(
        target=target,
        content=content,
        runtime_token=runtime_token,
        runtime_context=runtime_context,
        preview_route=preview_route,
    )
    return rewritten, rewritten != content


def _proxy_headers(request: Request, *, target: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in {"host", "content-length", "cookie", "if-none-match", "if-modified-since"}:
            continue
        headers[key] = value
    extra_headers = json.loads(str(target.get("extra_headers") or "{}"))
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            if str(key).strip():
                headers[str(key)] = str(value)
    auth_token = str(target.get("auth_token") or "").strip()
    if auth_token:
        headers[str(target.get("auth_header_name") or "Authorization")] = (
            f"{str(target.get('auth_token_prefix') or '')}{auth_token}"
        )
    return headers


def _websocket_proxy_connect_options(
    websocket: WebSocket,
    *,
    target: dict[str, str],
) -> tuple[list[tuple[str, str]], list[str]]:
    additional_headers: list[tuple[str, str]] = []
    extra_headers = json.loads(str(target.get("extra_headers") or "{}"))
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            if str(key).strip():
                additional_headers.append((str(key), str(value)))
    auth_token = str(target.get("auth_token") or "").strip()
    if auth_token:
        additional_headers.append(
            (
                str(target.get("auth_header_name") or "Authorization"),
                f"{str(target.get('auth_token_prefix') or '')}{auth_token}",
            )
        )

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
    _set_canonical_preview_cookie(response=response, request=request, token=token)


async def _load_preview_request_context(
    *,
    db: AsyncSession,
    request: Request,
    session_id: str,
) -> tuple[PublishedAppDraftDevSession, PublishedApp, PublishedAppRevision, dict[str, Any], str]:
    session = await _load_session(db=db, session_id=session_id)
    token = _extract_preview_token(request=request)
    if not token:
        raise HTTPException(status_code=401, detail="Preview authentication required")
    payload = decode_preview_token(token)
    _assert_preview_scope_matches_session(payload, session)
    app, revision = await _load_preview_app_and_revision(db=db, session=session)
    return session, app, revision, payload, token


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/status")
async def builder_preview_status(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session, _, _, _, token = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    await _touch_preview_session_activity(
        db=db,
        session=session,
        reason="status_poll",
        throttle_seconds=15,
    )
    await db.commit()
    workspace = getattr(session, "draft_workspace", None)
    backend_metadata = (
        dict(workspace.backend_metadata or {})
        if workspace is not None and isinstance(workspace.backend_metadata, dict)
        else dict(session.backend_metadata or {}) if isinstance(session.backend_metadata, dict) else {}
    )
    live_preview = (
        dict(backend_metadata.get("live_preview") or {})
        if isinstance(backend_metadata.get("live_preview"), dict)
        else {"mode": "build_watch_static", "status": "booting"}
    )
    requested_build_id = str(request.query_params.get("__build") or "").strip() or None
    apps_builder_trace(
        "preview.status.responded",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or "") or None,
        status=str(live_preview.get("status") or "").strip() or None,
        current_build_id=str(live_preview.get("current_build_id") or "").strip() or None,
        last_successful_build_id=str(live_preview.get("last_successful_build_id") or "").strip() or None,
        requested_build_id=requested_build_id,
        requested_build_matches_last_successful=(
            requested_build_id == (str(live_preview.get("last_successful_build_id") or "").strip() or None)
            if requested_build_id is not None
            else None
        ),
        updated_at=live_preview.get("updated_at"),
        debug_build_sequence=live_preview.get("debug_build_sequence"),
        debug_last_trigger_reason=str(live_preview.get("debug_last_trigger_reason") or "").strip() or None,
        debug_last_trigger_revision_token=str(live_preview.get("debug_last_trigger_revision_token") or "").strip() or None,
        debug_last_trigger_workspace_fingerprint=str(live_preview.get("debug_last_trigger_workspace_fingerprint") or "").strip() or None,
        debug_last_phase=str(live_preview.get("debug_last_phase") or "").strip() or None,
        debug_last_phase_at=live_preview.get("debug_last_phase_at"),
        debug_recent_events=live_preview.get("debug_recent_events"),
        error=str(live_preview.get("error") or "").strip() or None,
        token_present=bool(token),
    )
    response = JSONResponse(live_preview)
    if token:
        _set_preview_cookie(response, request=request, token=token)
    return response


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/state")
async def builder_preview_auth_state(
    session_id: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    session, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
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
        "preview_session_id": str(session.id),
    }


@router.post("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/signup")
async def builder_preview_signup(
    session_id: str,
    request: Request,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
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


@router.post("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/login")
async def builder_preview_login(
    session_id: str,
    request: Request,
    payload: PublicAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
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


@router.post("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/exchange")
async def builder_preview_exchange_auth_token(
    session_id: str,
    request: Request,
    payload: PublicAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
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


@router.post("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/logout")
async def builder_preview_logout(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is not None:
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


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/google/start")
async def builder_preview_google_start(
    session_id: str,
    request: Request,
    return_to: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
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
    cookie_name = f"{GOOGLE_OAUTH_STATE_COOKIE_NAME}_preview"
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
        cookie_name=cookie_name,
    )
    return response


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/auth/google/callback")
async def builder_preview_google_callback(
    session_id: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
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
    cookie_name = f"{GOOGLE_OAUTH_STATE_COOKIE_NAME}_preview"
    oauth_state_nonce = (request.cookies.get(cookie_name) or "").strip()
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
            cookie_name=cookie_name,
        )
        return response
    return_to = _normalize_return_to_for_host(str(request.base_url), state_payload.get("return_to"))  # type: ignore[name-defined]
    redirect = RedirectResponse(url=return_to or "/", status_code=302)
    _set_session_cookie(response=redirect, request=request, token=result.token)
    _clear_google_oauth_state_cookie(
        response=redirect,
        request=request,
        cookie_name=cookie_name,
    )
    return redirect


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/runtime/bootstrap")
async def builder_preview_runtime_bootstrap(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session, app, revision, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    bootstrap = _build_builder_preview_bootstrap(request=request, session=session, app=app, revision=revision)
    return JSONResponse(bootstrap.model_dump())


@router.post("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/chat/stream")
async def builder_preview_chat_stream(
    session_id: str,
    request: Request,
    payload: PublicChatStreamRequest,
    db: AsyncSession = Depends(get_db),
):
    session, app, _, principal_payload, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
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
        enforce_app_auth=bool(app.auth_enabled),
        allow_chat_persistence=True,
        request_user_id=str(principal["app_account_id"]) if principal else None,
        extra_context={
            "builder_preview": True,
            "builder_preview_session_id": str(session.id),
            "published_app_preview_user_id": str(principal_payload.get("user_id") or "") or None,
        },
    )
    if stale_cookie:
        _clear_session_cookie(response=stream_response, request=request)
    return stream_response


@router.post("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/attachments/upload")
async def builder_preview_upload_attachments(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    thread_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if app.auth_enabled and principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
    owner = RuntimeAttachmentOwner(
        organization_id=app.organization_id,
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


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/threads")
async def builder_preview_list_threads(
    session_id: str,
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
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


@router.get("/public/apps-builder/draft-dev/sessions/{session_id}/preview/_talmudpedia/threads/{thread_id}")
async def builder_preview_get_thread(
    session_id: str,
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
    _, app, _, _, _ = await _load_preview_request_context(db=db, request=request, session_id=session_id)
    principal, stale_cookie = await _resolve_optional_principal_from_cookie(db=db, request=request, expected_app=app)
    if principal is None:
        response = JSONResponse(status_code=401, content={"detail": "Authentication required"})
        if stale_cookie:
            _clear_session_cookie(response=response, request=request)
        return response
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


@router.api_route(
    "/public/apps-builder/draft-dev/sessions/{session_id}/preview",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@router.api_route(
    "/public/apps-builder/draft-dev/sessions/{session_id}/preview/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_builder_preview(
    session_id: str,
    request: Request,
    path: str = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    proxy_started_at = time.perf_counter()
    session = await _load_session(db=db, session_id=session_id)
    query_token = str(request.query_params.get("runtime_token") or "").strip()
    cookie_token = str(request.cookies.get(PREVIEW_COOKIE_NAME) or "").strip()
    try:
        token, payload, token_source = _resolve_preview_token_for_session(session=session, request=request)
    except HTTPException as exc:
        if cookie_token and exc.status_code in {401, 403}:
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            clear_preview_cookie(response=response)
            return response
        raise
    await _touch_preview_session_activity(
        db=db,
        session=session,
        reason="http_request",
        throttle_seconds=30,
    )
    target = await _resolve_preview_target(session)
    request_kind = _preview_request_kind(path)
    upstream_url = _upstream_url(
        path=path,
        query_params=request.query_params,
        target=target,
    )
    backend_metadata = dict(session.backend_metadata or {}) if isinstance(session.backend_metadata, dict) else {}
    live_preview = (
        dict(backend_metadata.get("live_preview") or {})
        if isinstance(backend_metadata.get("live_preview"), dict)
        else {}
    )
    requested_build_id = str(request.query_params.get("__build") or "").strip() or None
    apps_builder_trace(
        "preview.proxy.requested",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        method=request.method,
        path=path,
        request_kind=request_kind,
        token_source=token_source,
        query_keys=sorted(str(key) for key in request.query_params.keys()),
        preview_route=str(request.query_params.get("preview_route") or ""),
        requested_build_id=requested_build_id,
        live_preview_current_build_id=str(live_preview.get("current_build_id") or "").strip() or None,
        live_preview_last_successful_build_id=str(live_preview.get("last_successful_build_id") or "").strip() or None,
        requested_build_matches_last_successful=(
            requested_build_id == (str(live_preview.get("last_successful_build_id") or "").strip() or None)
            if requested_build_id is not None
            else None
        ),
        upstream_url=upstream_url,
        upstream_base_url=str(target.get("upstream_base_url") or ""),
        target_base_path=str(target.get("base_path") or ""),
        target_upstream_path=str(target.get("upstream_path") or ""),
    )
    apps_builder_trace(
        "preview.proxy.target_resolved",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        path=path,
        request_kind=request_kind,
        resolver_kind=str(target.get("resolver_kind") or ""),
        provider=str(target.get("provider") or ""),
        upstream_base_url=str(target.get("upstream_base_url") or ""),
        target_base_path=str(target.get("base_path") or ""),
        target_upstream_path=str(target.get("upstream_path") or ""),
        has_auth_token=bool(str(target.get("auth_token") or "").strip()),
        auth_header_name=str(target.get("auth_header_name") or ""),
        has_extra_headers=bool(str(target.get("extra_headers") or "").strip() not in {"", "{}"}),
    )
    preview_route = _normalize_preview_route(request.query_params.get("preview_route"))
    runtime_context: RuntimeBootstrapResponse | None = None
    if request.method.upper() == "GET" and not path:
        app, revision = await _load_preview_app_and_revision(db=db, session=session)
        runtime_context = _build_builder_preview_bootstrap(
            request=request,
            session=session,
            app=app,
            revision=revision,
        )
    body = b""
    if request.method.upper() not in {"GET", "HEAD"}:
        try:
            body = await request.body()
        except ClientDisconnect:
            apps_builder_trace(
                "preview.proxy.client_disconnected",
                domain="preview.proxy",
                session_id=str(session.id),
                app_id=str(session.published_app_id),
                revision_id=str(session.revision_id or ""),
                sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
                method=request.method,
                path=path,
                request_kind=request_kind,
            )
            return Response(status_code=499)
    try:
        try:
            upstream = await _request_preview_upstream(
                request=request,
                upstream_url=upstream_url,
                target=target,
                body=body,
            )
        except httpx.HTTPError as exc:
            if not _is_refreshable_preview_error(exc):
                raise
            refreshed_target = await _refresh_preview_target(
                db=db,
                session=session,
                current_target=target,
            )
            if refreshed_target is None:
                raise
            target = refreshed_target
            upstream_url = _upstream_url(
                path=path,
                query_params=request.query_params,
                target=target,
            )
            apps_builder_trace(
                "preview.proxy.retrying_after_refresh",
                domain="preview.proxy",
                session_id=str(session.id),
                app_id=str(session.published_app_id),
                revision_id=str(session.revision_id or ""),
                sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
                method=request.method,
                path=path,
                upstream_url=upstream_url,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            upstream = await _request_preview_upstream(
                request=request,
                upstream_url=upstream_url,
                target=target,
                body=body,
            )
    except httpx.TimeoutException as exc:
        apps_builder_trace(
            "preview.proxy.failed",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
            method=request.method,
            path=path,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        raise HTTPException(status_code=504, detail="Draft dev preview upstream timed out") from exc
    except httpx.HTTPError as exc:
        apps_builder_trace(
            "preview.proxy.failed",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
            method=request.method,
            path=path,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        raise HTTPException(status_code=502, detail="Draft dev preview upstream request failed") from exc
    content_type = str(upstream.headers.get("content-type") or "")
    response_content = upstream.content
    content_rewritten = False
    rewrite_started_at = time.perf_counter()
    if request.method.upper() == "GET" and upstream.status_code == 200:
        response_content, content_rewritten = _rewrite_text_preview_content(
            target=target,
            path=path,
            content_type=content_type,
            content=upstream.content,
            runtime_token=token,
            runtime_context=runtime_context,
            preview_route=preview_route,
        )
    rewrite_summary = _preview_rewrite_summary(
        path=path,
        content_type=content_type,
        original_content=upstream.content,
        rewritten_content=response_content,
        runtime_context=runtime_context,
    )
    excluded_headers = {"content-encoding", "transfer-encoding", "connection", "content-length"}
    if content_rewritten:
        excluded_headers.update({"etag", "last-modified"})
    response = Response(
        content=response_content,
        status_code=upstream.status_code,
        media_type=content_type,
    )
    for key, value in upstream.headers.items():
        if key.lower() in excluded_headers or key.lower() == "content-type":
            continue
        response.headers[key] = value
    if content_rewritten:
        response.headers["Cache-Control"] = "no-store"
    if token:
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
        request_kind=request_kind,
        token_source=token_source,
        proxy_duration_ms=int((time.perf_counter() - proxy_started_at) * 1000),
        rewrite_duration_ms=int((time.perf_counter() - rewrite_started_at) * 1000),
        status_code=upstream.status_code,
        content_type=content_type,
        content_rewritten=content_rewritten,
        rewrite_summary=rewrite_summary,
        response_probe=_preview_body_probe(response_content, content_type=content_type),
    )
    return response


@router.websocket("/public/apps-builder/draft-dev/sessions/{session_id}/preview")
@router.websocket("/public/apps-builder/draft-dev/sessions/{session_id}/preview/{path:path}")
async def proxy_builder_preview_websocket(
    websocket: WebSocket,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    path: str = "",
) -> None:
    session = await _load_session(db=db, session_id=session_id)
    apps_builder_trace(
        "preview.proxy.websocket_rejected",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        path=path,
        reason="builder_preview_static_mode",
    )
    await websocket.close(code=4404)
