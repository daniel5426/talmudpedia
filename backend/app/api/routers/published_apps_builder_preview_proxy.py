from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_published_app_preview_token
from app.db.postgres.models.published_apps import PublishedAppDraftDevSession
from app.db.postgres.session import get_db
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClient
from app.services.published_app_sandbox_backend_factory import load_published_app_sandbox_backend_config
from app.services.published_app_sprite_proxy_tunnel import get_sprite_proxy_tunnel_manager


router = APIRouter(tags=["published-apps-builder-preview-proxy"])

PREVIEW_COOKIE_NAME = "published_app_preview_token"
_PREVIEW_WEBSOCKET_OPEN_TIMEOUT_SECONDS = 20.0
_PREVIEW_WEBSOCKET_CONNECT_ATTEMPTS = 3
_PREVIEW_HTTP_RETRY_DELAYS_SECONDS = (0.0, 0.35, 0.75, 1.5)
_HTML_URL_ATTR_PATTERN = re.compile(r"""(?P<prefix>\b(?:src|href)=["'])(?P<path>/[^"'?#]+(?:[?#][^"']*)?)""")
_INLINE_VITE_PATH_PATTERN = re.compile(
    r"""(?P<quote>["'])(?P<path>/(?:@vite|@react-refresh|src/|node_modules/|runtime-sdk/|__vite)[^"']*)(?P=quote)"""
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


async def _accept_websocket_if_needed(websocket: WebSocket, *, subprotocol: str | None = None) -> None:
    if getattr(websocket, "application_state", None) == WebSocketState.CONNECTED:
        return
    await websocket.accept(subprotocol=subprotocol)


async def _close_websocket_if_possible(websocket: WebSocket, *, code: int = 1011) -> None:
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
        select(PublishedAppDraftDevSession)
        .options(selectinload(PublishedAppDraftDevSession.draft_workspace))
        .where(PublishedAppDraftDevSession.id == session_uuid)
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    return session


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
    provider = str(metadata.get("provider") or "").strip().lower()
    sprite_name = str(workspace_state.get("sprite_name") or "").strip()
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
    }


def _is_refreshable_preview_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.ConnectError):
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
    sandbox_id = str(getattr(session, "sandbox_id", "") or "").strip()
    if not sandbox_id:
        return None
    client = PublishedAppDraftDevRuntimeClient.from_env()
    try:
        refreshed = await client.heartbeat_session(sandbox_id=sandbox_id, idle_timeout_seconds=0)
    except Exception as exc:
        apps_builder_trace(
            "preview.proxy.refresh_failed",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=sandbox_id,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        return None
    metadata = refreshed.get("backend_metadata") if isinstance(refreshed, dict) else None
    if not isinstance(metadata, dict):
        return None
    preview = metadata.get("preview") if isinstance(metadata.get("preview"), dict) else None
    if not isinstance(preview, dict):
        return None
    preview["base_path"] = _merge_preview_base_path(target=current_target, session_id=str(session.id))
    workspace = getattr(session, "draft_workspace", None)
    if workspace is not None:
        workspace.backend_metadata = dict(metadata)
    session.backend_metadata = dict(metadata)
    await db.commit()
    apps_builder_trace(
        "preview.proxy.refreshed",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=sandbox_id,
        upstream_base_url=str(preview.get("upstream_base_url") or ""),
    )
    return await _resolve_preview_target(session)


async def _request_preview_upstream(
    *,
    request: Request,
    upstream_url: str,
    target: dict[str, str],
    body: bytes,
) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=False, timeout=60.0) as client:
        upstream = None
        last_error: httpx.HTTPError | None = None
        for delay in _PREVIEW_HTTP_RETRY_DELAYS_SECONDS:
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                candidate = await client.request(
                    request.method,
                    upstream_url,
                    headers=_proxy_headers(request, target=target),
                    content=body if body else None,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if _is_refreshable_preview_error(exc):
                    raise
                if _should_retry_preview_request(method=request.method, error=exc):
                    continue
                raise
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
        status_code=upstream.status_code,
        content_security_policy=str(upstream.headers.get("content-security-policy") or ""),
        x_frame_options=str(upstream.headers.get("x-frame-options") or ""),
        **probe,
    )
    return upstream


def _assert_preview_scope_matches_session(payload: dict[str, Any], session: PublishedAppDraftDevSession) -> None:
    token_app_id = str(payload.get("app_id") or "").strip()
    if token_app_id != str(session.published_app_id):
        raise HTTPException(status_code=403, detail="Preview token does not match draft session app scope")


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


def _compose_proxy_path(*, target: dict[str, str], resource_path: str) -> str:
    base_path = str(target.get("base_path") or "/").strip() or "/"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    return f"{base_path.rstrip('/')}/{str(resource_path or '').lstrip('/')}"


def _append_runtime_token_to_path(*, path: str, runtime_token: str | None) -> str:
    token = str(runtime_token or "").strip()
    if not token:
        return path
    parsed = urlparse(path)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if any(str(key) == "runtime_token" for key, _ in query_items):
        return path
    query_items.append(("runtime_token", token))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _rewrite_inline_vite_paths(*, target: dict[str, str], text: str, runtime_token: str | None) -> str:
    def _replace_inline(match: re.Match[str]) -> str:
        quote = str(match.group("quote") or '"')
        original = str(match.group("path") or "")
        if original.startswith("//"):
            return match.group(0)
        rewritten = _compose_proxy_path(target=target, resource_path=original)
        rewritten = _append_runtime_token_to_path(path=rewritten, runtime_token=runtime_token)
        return f"{quote}{rewritten}{quote}"

    return _INLINE_VITE_PATH_PATTERN.sub(_replace_inline, text)


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
    token_literal = json.dumps(str(runtime_token or "").strip() or None)
    rewritten = re.sub(
        r'(const wsToken = .*?;\n)',
        r"\1"
        f"const previewRuntimeToken = {token_literal};\n"
        'const previewRuntimeTokenSuffix = previewRuntimeToken ? `&runtime_token=${encodeURIComponent(previewRuntimeToken)}` : "";\n'
        'const previewBridgeType = "talmudpedia.preview-debug.v1";\n'
        "const __previewHmrLog = (event, fields = {}) => {\n"
        "\ttry {\n"
        "\t\tconst payload = Object.assign({ event, href: String((typeof location !== \"undefined\" && location.href) || \"\"), runtimeTokenPresent: Boolean(previewRuntimeToken) }, fields || {});\n"
        "\t\tconsole.info(\"[apps-builder][iframe]\", payload);\n"
        "\t\tif (typeof window !== \"undefined\" && window.parent && window.parent !== window) {\n"
        "\t\t\twindow.parent.postMessage({ type: previewBridgeType, payload }, \"*\");\n"
        "\t\t}\n"
        "\t} catch {}\n"
        "};\n",
        rewritten,
        count=1,
    )
    rewritten = rewritten.replace("?token=${wsToken}", "?token=${wsToken}${previewRuntimeTokenSuffix}")
    rewritten = rewritten.replace(
        'createConnection: () => new WebSocket(`${socketProtocol}://${socketHost}?token=${wsToken}${previewRuntimeTokenSuffix}`, "vite-hmr"),',
        'createConnection: () => (__previewHmrLog("vite.client.websocket_create", { mode: "primary", url: `${socketProtocol}://${socketHost}?token=${wsToken}${previewRuntimeTokenSuffix}` }), new WebSocket(`${socketProtocol}://${socketHost}?token=${wsToken}${previewRuntimeTokenSuffix}`, "vite-hmr")),',
    )
    rewritten = rewritten.replace(
        'createConnection: () => new WebSocket(`${socketProtocol}://${directSocketHost}?token=${wsToken}${previewRuntimeTokenSuffix}`, "vite-hmr"),',
        'createConnection: () => (__previewHmrLog("vite.client.websocket_create", { mode: "fallback", url: `${socketProtocol}://${directSocketHost}?token=${wsToken}${previewRuntimeTokenSuffix}` }), new WebSocket(`${socketProtocol}://${directSocketHost}?token=${wsToken}${previewRuntimeTokenSuffix}`, "vite-hmr")),',
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


def _rewrite_html_preview_content(*, target: dict[str, str], content: bytes, runtime_token: str | None) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    def _replace_attr(match: re.Match[str]) -> str:
        original = str(match.group("path") or "")
        if original.startswith("//"):
            return match.group(0)
        rewritten = _compose_proxy_path(target=target, resource_path=original)
        rewritten = _append_runtime_token_to_path(path=rewritten, runtime_token=runtime_token)
        return f"{match.group('prefix')}{rewritten}"

    rewritten = _HTML_URL_ATTR_PATTERN.sub(_replace_attr, text)
    rewritten = _rewrite_inline_vite_paths(target=target, text=rewritten, runtime_token=runtime_token)
    rewritten = _inject_preview_debug_probe(html=rewritten, runtime_token=runtime_token)
    return rewritten.encode("utf-8")


def _rewrite_text_preview_content(
    *,
    target: dict[str, str],
    path: str,
    content_type: str,
    content: bytes,
    runtime_token: str | None,
) -> tuple[bytes, bool]:
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if not normalized_content_type.startswith(_REWRITABLE_TEXT_PREFIXES):
        return content, False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content, False
    if normalized_content_type == "text/html":
        rewritten = _rewrite_html_preview_content(target=target, content=content, runtime_token=runtime_token)
        return rewritten, rewritten != content
    rewritten_text = _rewrite_inline_vite_paths(target=target, text=text, runtime_token=runtime_token)
    rewritten_text = _restore_hmr_owner_paths(text=rewritten_text)
    is_vite_client = str(path).strip().lstrip("/") == "@vite/client"
    if normalized_content_type in {"application/javascript", "text/javascript"} and (
        is_vite_client
        or "@vite/client" in rewritten_text
        or "const wsToken =" in rewritten_text
        or "new WebSocket(`${socketProtocol}://${socketHost}?token=${wsToken}`" in rewritten_text
    ):
        rewritten_text = _rewrite_vite_client_hmr_runtime(
            target=target,
            text=rewritten_text,
            runtime_token=runtime_token,
        )
    rewritten = rewritten_text.encode("utf-8")
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
    response.set_cookie(
        key=PREVIEW_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


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
    session = await _load_session(db=db, session_id=session_id)
    token = _extract_preview_token(request=request)
    if not token:
        raise HTTPException(status_code=401, detail="Preview authentication required")
    payload = _validate_preview_token(token)
    _assert_preview_scope_matches_session(payload, session)
    target = await _resolve_preview_target(session)
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
        upstream_base_url=str(target.get("upstream_base_url") or ""),
        target_base_path=str(target.get("base_path") or ""),
        target_upstream_path=str(target.get("upstream_path") or ""),
    )
    body = await request.body()
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
    if request.method.upper() == "GET" and upstream.status_code == 200:
        response_content, content_rewritten = _rewrite_text_preview_content(
            target=target,
            path=path,
            content_type=content_type,
            content=upstream.content,
            runtime_token=token,
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
        status_code=upstream.status_code,
        content_type=content_type,
        content_rewritten=content_rewritten,
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
        "preview.proxy.websocket_requested",
        domain="preview.proxy",
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id or ""),
        sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
        path=path,
        query_keys=sorted(str(key) for key in websocket.query_params.keys()),
        has_cookie=bool(str(websocket.cookies.get(PREVIEW_COOKIE_NAME) or "").strip()),
    )
    token = _extract_preview_token(websocket=websocket)
    if not token:
        apps_builder_trace(
            "preview.proxy.websocket_auth_missing",
            domain="preview.proxy",
            session_id=str(session.id),
            app_id=str(session.published_app_id),
            revision_id=str(session.revision_id or ""),
            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
            path=path,
            query_keys=sorted(str(key) for key in websocket.query_params.keys()),
            has_cookie=bool(str(websocket.cookies.get(PREVIEW_COOKIE_NAME) or "").strip()),
        )
        await websocket.close(code=4401)
        return
    payload = _validate_preview_token(token)
    _assert_preview_scope_matches_session(payload, session)
    target = await _resolve_preview_target(session)
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
    upstream_message_count = 0
    client_message_count = 0
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

        await _accept_websocket_if_needed(
            websocket,
            subprotocol=getattr(upstream, "subprotocol", None),
        )
        try:
            async def _client_to_upstream() -> None:
                nonlocal client_message_count
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        client_message_count += 1
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        client_message_count += 1
                        await upstream.send(message["bytes"])

            async def _upstream_to_client() -> None:
                nonlocal upstream_message_count
                async for message in upstream:
                    upstream_message_count += 1
                    if upstream_message_count <= 12:
                        apps_builder_trace(
                            "preview.proxy.websocket_frame",
                            domain="preview.proxy",
                            session_id=str(session.id),
                            app_id=str(session.published_app_id),
                            revision_id=str(session.revision_id or ""),
                            sandbox_id=str(getattr(session, "sandbox_id", "") or ""),
                            path=path,
                            direction="upstream_to_client",
                            ordinal=upstream_message_count,
                            **_summarize_websocket_message(message),
                        )
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
            upstream_message_count=upstream_message_count,
            client_message_count=client_message_count,
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
            upstream_message_count=upstream_message_count,
            client_message_count=client_message_count,
        )
        await _close_websocket_if_possible(websocket, code=1011)
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
            upstream_message_count=upstream_message_count,
            client_message_count=client_message_count,
        )
