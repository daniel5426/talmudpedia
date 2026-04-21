from __future__ import annotations

import os
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost").strip().lower()


def _host_without_port(host_header: str | None) -> str:
    return (host_header or "").split(":", 1)[0].strip().lower()


def _public_id_from_host(host_header: str | None) -> Optional[str]:
    host = _host_without_port(host_header)
    base_domain = _apps_base_domain()
    suffix = f".{base_domain}"
    if not host or host == base_domain or not host.endswith(suffix):
        return None
    public_id = host[: -len(suffix)].strip().lower()
    return public_id or None


def _request_origin_from_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _request_relative_url(path: str, query: str) -> str:
    return f"{path}?{query}" if query else path


def _normalize_return_to_for_host(base_url: str, raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return "/"
    if value.startswith("/"):
        return value
    try:
        parsed = urlparse(value)
        current = urlparse(base_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.netloc == current.netloc:
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            if parsed.fragment:
                path = f"{path}#{parsed.fragment}"
            return path
    except Exception:
        pass
    return "/"


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    updated = parsed._replace(query=urlencode(current))
    return urlunparse(updated)
