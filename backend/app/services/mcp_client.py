from __future__ import annotations

import asyncio
from fnmatch import fnmatch
import ipaddress
import os
import socket
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx


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


def _normalize_timeout(timeout_s: int | None) -> httpx.Timeout | None:
    if timeout_s is None:
        return None
    timeout = int(timeout_s)
    if timeout <= 0:
        raise ValueError("MCP timeout_s must be positive")
    if timeout > 120:
        raise ValueError("MCP timeout_s must be <= 120 seconds")
    return httpx.Timeout(timeout)


def _normalize_headers(headers: dict | None) -> dict[str, str] | None:
    if headers is None:
        return None
    if not isinstance(headers, dict):
        raise ValueError("MCP headers must be an object")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in headers.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = str(raw_value or "")
        if any(char in key for char in "\r\n") or any(char in value for char in "\r\n"):
            raise ValueError("MCP headers must not contain newline characters")
        normalized[key] = value
    return normalized or None


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


async def _validate_server_url(server_url: str) -> str:
    parsed = urlparse(server_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("MCP server_url must use http or https")
    if not parsed.hostname:
        raise ValueError("MCP server_url must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("MCP server_url must not embed credentials")

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


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict,
    headers: dict | None = None,
    timeout_s: int | None = None,
) -> dict:
    if not server_url:
        raise ValueError("MCP server_url is required")
    if not tool_name:
        raise ValueError("MCP tool_name is required")
    if not isinstance(arguments, dict):
        raise ValueError("MCP arguments must be an object")

    server_url = await _validate_server_url(server_url)
    headers = _normalize_headers(headers)

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    try:
        async with httpx.AsyncClient(timeout=_normalize_timeout(timeout_s)) as client:
            response = await client.post(server_url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"MCP transport error: HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"MCP transport error: {exc.__class__.__name__}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("MCP server returned invalid JSON") from exc

    if isinstance(data, dict) and data.get("error"):
        error_payload = data["error"]
        message = error_payload.get("message") if isinstance(error_payload, dict) else str(error_payload)
        code = error_payload.get("code") if isinstance(error_payload, dict) else None
        if code is not None:
            raise RuntimeError(f"MCP tool error [{code}]: {message}")
        raise RuntimeError(f"MCP tool error: {message}")

    if not isinstance(data, dict) or "result" not in data:
        raise RuntimeError("MCP tool response missing result")

    result = data.get("result")
    if not isinstance(result, dict):
        return {"result": result}
    return result
