from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
import ipaddress
import json
import os
import re
import socket
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx


MCP_PROTOCOL_VERSION = "2025-03-26"
DEFAULT_TIMEOUT_S = 20
SESSION_TTL_SECONDS = 300
SESSION_ID_HEADER = "Mcp-Session-Id"
PROTOCOL_HEADER = "MCP-Protocol-Version"
JSONRPC_VERSION = "2.0"
CLIENT_INFO = {"name": "Talmudpedia MCP Client", "version": "1.0"}

_SESSION_CACHE: dict[str, tuple[str, float]] = {}
_WWW_AUTH_PARAM_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_-]*)="([^"]*)"')


class McpUnauthorizedError(RuntimeError):
    def __init__(self, message: str, *, www_authenticate: str | None = None):
        super().__init__(message)
        self.www_authenticate = www_authenticate


class McpProtocolError(RuntimeError):
    pass


@dataclass
class McpInitializeResult:
    server_info: dict[str, Any]
    capabilities: dict[str, Any]
    protocol_version: str
    session_id: str | None = None


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _allowed_mcp_hosts() -> list[str]:
    raw = str(os.getenv("MCP_ALLOWED_HOSTS") or "").strip()
    if not raw:
        return []
    return [item for item in (part.strip().lower() for part in raw.split(",")) if item]


def _normalize_timeout(timeout_s: int | None) -> httpx.Timeout:
    timeout = int(timeout_s or DEFAULT_TIMEOUT_S)
    if timeout <= 0:
        raise ValueError("MCP timeout_s must be positive")
    if timeout > 120:
        raise ValueError("MCP timeout_s must be <= 120 seconds")
    return httpx.Timeout(timeout)


def _normalize_headers(headers: dict | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not headers:
        return normalized
    if not isinstance(headers, dict):
        raise ValueError("MCP headers must be an object")
    for raw_key, raw_value in headers.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = str(raw_value or "")
        if any(char in key for char in "\r\n") or any(char in value for char in "\r\n"):
            raise ValueError("MCP headers must not contain newline characters")
        normalized[key] = value
    return normalized


def _is_non_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


async def _resolve_hostname_addresses(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"MCP hostname '{hostname}' could not be resolved") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        raw_ip = str(info[4][0])
        if raw_ip in seen:
            continue
        seen.add(raw_ip)
        addresses.append(ipaddress.ip_address(raw_ip))
    if not addresses:
        raise ValueError(f"MCP hostname '{hostname}' did not resolve to an address")
    return addresses


async def validate_mcp_server_url(server_url: str, *, for_auth: bool = False) -> str:
    parsed = urlparse(server_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("MCP server_url must use http or https")
    if not parsed.hostname:
        raise ValueError("MCP server_url must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("MCP server_url must not embed credentials")
    if for_auth and parsed.scheme != "https" and not _env_flag("MCP_ALLOW_INSECURE_OAUTH", default=False):
        raise ValueError("OAuth-backed MCP servers must use https")

    hostname = parsed.hostname.strip().lower()
    allow_private_hosts = _env_flag("MCP_ALLOW_PRIVATE_HOSTS", default=False)
    allowed_hosts = _allowed_mcp_hosts()
    if allowed_hosts and not any(fnmatch(hostname, pattern) for pattern in allowed_hosts):
        raise ValueError(f"MCP hostname '{hostname}' is not in MCP_ALLOWED_HOSTS")
    if not allow_private_hosts and hostname in {"localhost"}:
        raise ValueError("MCP private or loopback hosts are blocked by default")

    try:
        resolved_ips = [ipaddress.ip_address(hostname)]
    except ValueError:
        resolved_ips = await _resolve_hostname_addresses(hostname)
    if not allow_private_hosts:
        for resolved_ip in resolved_ips:
            if _is_non_public_ip(resolved_ip):
                raise ValueError("MCP private or loopback hosts are blocked by default")
    return server_url


def _auth_headers(base_headers: dict[str, str] | None, bearer_token: str | None) -> dict[str, str]:
    headers = _normalize_headers(base_headers)
    headers.setdefault("Accept", "application/json, text/event-stream")
    headers.setdefault("Content-Type", "application/json")
    headers[PROTOCOL_HEADER] = MCP_PROTOCOL_VERSION
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


def _session_cache_key(*, server_url: str, auth_identity: str) -> str:
    return f"{server_url}::{auth_identity}"


def _cached_session_id(cache_key: str) -> str | None:
    cached = _SESSION_CACHE.get(cache_key)
    if not cached:
        return None
    session_id, expires_at = cached
    if expires_at <= time.time():
        _SESSION_CACHE.pop(cache_key, None)
        return None
    return session_id


def _store_session_id(cache_key: str, session_id: str | None) -> None:
    if not session_id:
        return
    _SESSION_CACHE[cache_key] = (session_id, time.time() + SESSION_TTL_SECONDS)


def _extract_json_payload(response: httpx.Response) -> dict[str, Any]:
    content_type = str(response.headers.get("content-type") or "").strip().lower()
    if "text/event-stream" in content_type:
        raw_text = response.text or ""
        data_lines: list[str] = []
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(":"):
                continue
            if stripped.lower().startswith("data:"):
                data_lines.append(stripped[5:].strip())
        if data_lines:
            try:
                payload = json.loads("\n".join(data_lines))
            except ValueError as exc:
                preview = raw_text.strip()
                if len(preview) > 160:
                    preview = preview[:160] + "...[truncated]"
                raise McpProtocolError(
                    "MCP server returned event-stream data that was not valid JSON. "
                    f"Response preview: {preview}"
                ) from exc
            if not isinstance(payload, dict):
                raise McpProtocolError("MCP server returned an invalid SSE JSON-RPC envelope")
            return payload

    try:
        payload = response.json()
    except ValueError as exc:
        content_type = content_type or "unknown"
        preview = (response.text or "").strip()
        if len(preview) > 160:
            preview = preview[:160] + "...[truncated]"
        detail = f"MCP server returned non-JSON response (content-type: {content_type})"
        if preview:
            detail += f". Response preview: {preview}"
        raise McpProtocolError(detail) from exc
    if not isinstance(payload, dict):
        raise McpProtocolError("MCP server returned an invalid JSON-RPC envelope")
    return payload


async def _post_jsonrpc(
    *,
    client: httpx.AsyncClient,
    server_url: str,
    headers: dict[str, str],
    method: str,
    params: dict[str, Any] | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    expect_response: bool = True,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params is not None:
        payload["params"] = params
    if request_id is not None:
        payload["id"] = request_id

    request_headers = dict(headers)
    if session_id:
        request_headers[SESSION_ID_HEADER] = session_id

    response = await client.post(server_url, json=payload, headers=request_headers)
    if response.status_code == 401:
        raise McpUnauthorizedError(
            f"MCP server requires authorization for {method}",
            www_authenticate=response.headers.get("www-authenticate"),
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in {404, 405, 415}:
            raise McpProtocolError(
                f"MCP endpoint rejected {method} with HTTP {status_code}. "
                "This URL does not appear to be a Streamable HTTP MCP endpoint."
            ) from exc
        raise McpProtocolError(f"MCP transport error: HTTP {status_code}") from exc
    if not expect_response:
        return None
    envelope = _extract_json_payload(response)
    if envelope.get("error"):
        error_payload = envelope["error"]
        message = error_payload.get("message") if isinstance(error_payload, dict) else str(error_payload)
        code = error_payload.get("code") if isinstance(error_payload, dict) else None
        raise McpProtocolError(f"MCP error{f' [{code}]' if code is not None else ''}: {message}")
    return {
        "result": envelope.get("result"),
        "session_id": response.headers.get(SESSION_ID_HEADER) or session_id,
        "protocol_version": response.headers.get(PROTOCOL_HEADER),
    }


async def initialize_mcp_session(
    *,
    server_url: str,
    headers: dict[str, str] | None = None,
    bearer_token: str | None = None,
    timeout_s: int | None = None,
    auth_identity: str = "shared",
    force_reinitialize: bool = False,
) -> McpInitializeResult:
    server_url = await validate_mcp_server_url(server_url)
    cache_key = _session_cache_key(server_url=server_url, auth_identity=auth_identity)
    session_id = None if force_reinitialize else _cached_session_id(cache_key)
    request_headers = _auth_headers(headers, bearer_token)

    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await _post_jsonrpc(
            client=client,
            server_url=server_url,
            headers=request_headers,
            method="initialize",
            params={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "sampling": {}},
                "clientInfo": CLIENT_INFO,
            },
            request_id=str(uuid.uuid4()),
            session_id=session_id,
        )
        assert response is not None
        session_id = response.get("session_id")
        _store_session_id(cache_key, session_id)
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        await _post_jsonrpc(
            client=client,
            server_url=server_url,
            headers=request_headers,
            method="notifications/initialized",
            params={},
            session_id=session_id,
            expect_response=False,
        )

    return McpInitializeResult(
        server_info=result.get("serverInfo") if isinstance(result.get("serverInfo"), dict) else {},
        capabilities=result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {},
        protocol_version=str(result.get("protocolVersion") or response.get("protocol_version") or MCP_PROTOCOL_VERSION),
        session_id=session_id,
    )


async def list_mcp_tools(
    *,
    server_url: str,
    headers: dict[str, str] | None = None,
    bearer_token: str | None = None,
    timeout_s: int | None = None,
    auth_identity: str = "shared",
) -> dict[str, Any]:
    init_result = await initialize_mcp_session(
        server_url=server_url,
        headers=headers,
        bearer_token=bearer_token,
        timeout_s=timeout_s,
        auth_identity=auth_identity,
    )
    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await _post_jsonrpc(
            client=client,
            server_url=server_url,
            headers=_auth_headers(headers, bearer_token),
            method="tools/list",
            params={},
            request_id=str(uuid.uuid4()),
            session_id=init_result.session_id,
        )
    result = response.get("result") if isinstance(response, dict) and isinstance(response.get("result"), dict) else {}
    return {
        "initialize": init_result,
        "tools": result.get("tools") if isinstance(result.get("tools"), list) else [],
        "next_cursor": result.get("nextCursor"),
    }


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict,
    headers: dict | None = None,
    timeout_s: int | None = None,
    bearer_token: str | None = None,
    auth_identity: str = "shared",
) -> dict:
    if not server_url:
        raise ValueError("MCP server_url is required")
    if not tool_name:
        raise ValueError("MCP tool_name is required")
    if not isinstance(arguments, dict):
        raise ValueError("MCP arguments must be an object")

    init_result = await initialize_mcp_session(
        server_url=server_url,
        headers=headers,
        bearer_token=bearer_token,
        timeout_s=timeout_s,
        auth_identity=auth_identity,
    )
    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await _post_jsonrpc(
            client=client,
            server_url=server_url,
            headers=_auth_headers(headers, bearer_token),
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
            request_id=str(uuid.uuid4()),
            session_id=init_result.session_id,
        )
    result = response.get("result")
    if not isinstance(result, dict):
        return {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result, "isError": False}
    return result


def parse_www_authenticate_header(header_value: str | None) -> dict[str, str]:
    if not header_value:
        return {}
    return {match.group(1): match.group(2) for match in _WWW_AUTH_PARAM_RE.finditer(header_value)}


async def fetch_json_document(url: str, *, timeout_s: int | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return payload


def _authorization_server_metadata_candidates(auth_server: str) -> list[str]:
    normalized = str(auth_server or "").strip().rstrip("/")
    if not normalized:
        return []
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []

    origin = f"{parsed.scheme}://{parsed.netloc}"
    issuer_path = parsed.path.strip("/")
    candidates: list[str] = []

    # RFC 8414 path-based issuer form:
    #   https://host/.well-known/oauth-authorization-server/<issuer-path>
    #   https://host/.well-known/openid-configuration/<issuer-path>
    if issuer_path:
        candidates.extend(
            [
                f"{origin}/.well-known/oauth-authorization-server/{issuer_path}",
                f"{origin}/.well-known/openid-configuration/{issuer_path}",
            ]
        )

    # Legacy/common issuer-relative locations used by some providers.
    candidates.extend(
        [
            f"{normalized}/.well-known/oauth-authorization-server",
            f"{normalized}/.well-known/openid-configuration",
            f"{origin}/.well-known/oauth-authorization-server",
            f"{origin}/.well-known/openid-configuration",
        ]
    )

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _protected_resource_metadata_candidates(server_url: str) -> list[str]:
    normalized = str(server_url or "").strip().rstrip("/")
    if not normalized:
        return []
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []

    origin = f"{parsed.scheme}://{parsed.netloc}"
    resource_path = parsed.path.strip("/")
    candidates: list[str] = []

    if resource_path:
        candidates.append(f"{origin}/.well-known/oauth-protected-resource/{resource_path}")

    candidates.extend(
        [
            f"{origin}/.well-known/oauth-protected-resource",
            f"{normalized}/.well-known/oauth-protected-resource",
        ]
    )

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


async def discover_mcp_oauth_metadata(
    *,
    server_url: str,
    challenge_header: str | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    await validate_mcp_server_url(server_url, for_auth=True)
    challenge_params = parse_www_authenticate_header(challenge_header)
    prm_url = challenge_params.get("resource_metadata")
    protected_resource: dict[str, Any] | None = None
    fetch_errors: list[str] = []
    for candidate in ([prm_url] if prm_url else _protected_resource_metadata_candidates(server_url)):
        try:
            protected_resource = await fetch_json_document(candidate, timeout_s=timeout_s)
            prm_url = candidate
            break
        except Exception as exc:
            fetch_errors.append(f"{candidate}: {exc}")
    if protected_resource is None:
        raise ValueError("Unable to resolve protected resource metadata: " + "; ".join(fetch_errors))

    auth_servers = protected_resource.get("authorization_servers")
    if not isinstance(auth_servers, list) or not auth_servers:
        raise ValueError("Protected resource metadata did not include authorization_servers")
    auth_server = str(auth_servers[0]).rstrip("/")

    auth_server_metadata: dict[str, Any] | None = None
    fetch_errors = []
    for candidate in _authorization_server_metadata_candidates(auth_server):
        try:
            auth_server_metadata = await fetch_json_document(candidate, timeout_s=timeout_s)
            break
        except Exception as exc:
            fetch_errors.append(f"{candidate}: {exc}")
    if auth_server_metadata is None:
        raise ValueError("Unable to resolve authorization server metadata: " + "; ".join(fetch_errors))

    return {
        "protected_resource_metadata_url": prm_url,
        "protected_resource_metadata": protected_resource,
        "authorization_server": auth_server,
        "authorization_server_metadata": auth_server_metadata,
        "challenge": challenge_params,
    }


async def register_oauth_client(
    *,
    registration_endpoint: str,
    payload: dict[str, Any],
    timeout_s: int | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await client.post(
            registration_endpoint,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict) or not body.get("client_id"):
        raise ValueError("Dynamic client registration did not return a client_id")
    return body


async def exchange_oauth_code(
    *,
    token_endpoint: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise ValueError("OAuth token exchange did not return access_token")
    return body


async def refresh_oauth_token(
    *,
    token_endpoint: str,
    refresh_token: str,
    client_id: str,
    client_secret: str | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise ValueError("OAuth token refresh did not return access_token")
    return body


def normalize_token_payload(payload: dict[str, Any], *, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    merged = dict(previous or {})
    merged.update(payload or {})
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        try:
            merged["expires_at"] = (now + timedelta(seconds=max(int(expires_in) - 30, 0))).isoformat()
        except Exception:
            pass
    if merged.get("refresh_token") in {None, ""} and isinstance(previous, dict):
        prior_refresh = previous.get("refresh_token")
        if prior_refresh:
            merged["refresh_token"] = prior_refresh
    return merged


def token_expired(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return True
    raw = payload.get("expires_at")
    if not raw:
        return False
    try:
        expires_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
