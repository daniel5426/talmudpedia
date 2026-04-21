from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import Request


def resolve_backend_port(default: int = 8000) -> int:
    raw = (
        (os.getenv("BACKEND_PORT") or "").strip()
        or (os.getenv("PORT") or "").strip()
    )
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def resolve_local_backend_origin() -> str:
    explicit = (
        (os.getenv("BACKEND_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("PLATFORM_BASE_URL") or "").strip()
        or (os.getenv("API_BASE_URL") or "").strip()
    )
    if explicit:
        return explicit.rstrip("/")
    return f"http://127.0.0.1:{resolve_backend_port()}"


def resolve_runtime_api_base_url(request: Request | None = None) -> str:
    explicit = (os.getenv("APPS_DRAFT_DEV_RUNTIME_API_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")

    prefix_env = os.getenv("APPS_DRAFT_DEV_RUNTIME_API_PREFIX")
    api_prefix = (prefix_env or "").strip() if prefix_env is not None else ""
    if request is not None:
        parsed = urlparse(str(request.base_url))
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if prefix_env is None:
            api_prefix = str(request.scope.get("root_path") or "").strip()
            if not api_prefix:
                api_prefix = (request.headers.get("x-forwarded-prefix") or "").strip()
            if not api_prefix and str(request.url.path).startswith("/api/py/"):
                api_prefix = "/api/py"
    else:
        origin = resolve_local_backend_origin()

    if not api_prefix:
        return origin
    if not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    return f"{origin}{api_prefix.rstrip('/')}"


def resolve_apps_url_scheme() -> str:
    configured = (os.getenv("APPS_URL_SCHEME") or "").strip().lower()
    if configured in {"http", "https"}:
        return configured
    return "https"


def resolve_apps_url_port() -> str:
    configured = (os.getenv("APPS_URL_PORT") or "").strip()
    if configured:
        return configured if configured.startswith(":") else f":{configured}"

    base_domain = (os.getenv("APPS_BASE_DOMAIN") or "apps.localhost").strip().lower()
    is_local_domain = (
        base_domain == "localhost"
        or base_domain.endswith(".localhost")
        or base_domain.startswith("127.0.0.1")
    )
    if not is_local_domain:
        return ""

    port = resolve_backend_port()
    scheme = resolve_apps_url_scheme()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return ""
    return f":{port}"


def build_published_app_url(public_id: str) -> str:
    base_domain = os.getenv("APPS_BASE_DOMAIN", "apps.localhost")
    return f"{resolve_apps_url_scheme()}://{public_id}.{base_domain}{resolve_apps_url_port()}"


def resolve_sandbox_controller_url() -> str | None:
    explicit = (
        (os.getenv("APPS_SANDBOX_CONTROLLER_URL") or "").strip()
        or (os.getenv("APPS_DRAFT_DEV_CONTROLLER_URL") or "").strip()
    )
    if explicit:
        return explicit
    return f"{resolve_local_backend_origin()}/internal/sandbox-controller"
