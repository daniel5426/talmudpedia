from __future__ import annotations

import os

from app.services.published_app_sandbox_backend import (
    PublishedAppSandboxBackend,
    PublishedAppSandboxBackendConfig,
    is_truthy,
)
from app.services.published_app_sandbox_backend_controller import ControllerSandboxBackend
from app.services.published_app_sandbox_backend_e2b import E2BSandboxBackend
from app.services.published_app_sandbox_backend_local import LocalSandboxBackend


def _resolve_e2b_template_reference(template: str | None, template_tag: str | None) -> str | None:
    raw_template = str(template or "").strip()
    if not raw_template:
        return None
    if ":" in raw_template:
        return raw_template
    raw_tag = str(template_tag or "").strip()
    if not raw_tag:
        return raw_template
    return f"{raw_template}:{raw_tag}"


def validate_published_app_sandbox_backend_env() -> None:
    backend = (os.getenv("APPS_SANDBOX_BACKEND") or "").strip().lower()
    if backend != "e2b":
        return

    api_key = (os.getenv("E2B_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "APPS_SANDBOX_BACKEND=e2b requires E2B_API_KEY to be set in the backend environment."
        )

    allow_default_template = is_truthy(os.getenv("APPS_E2B_ALLOW_DEFAULT_TEMPLATE", "0"), default=False)
    template = _resolve_e2b_template_reference(
        (os.getenv("APPS_E2B_TEMPLATE") or "").strip(),
        (os.getenv("APPS_E2B_TEMPLATE_TAG") or "").strip(),
    )
    if template or allow_default_template:
        return

    raise RuntimeError(
        "APPS_SANDBOX_BACKEND=e2b requires APPS_E2B_TEMPLATE to be set. "
        "Build the dedicated app-builder template first or set APPS_E2B_ALLOW_DEFAULT_TEMPLATE=1 "
        "to bypass this guard temporarily."
    )


def load_published_app_sandbox_backend_config() -> PublishedAppSandboxBackendConfig:
    timeout_seconds = int(os.getenv("APPS_DRAFT_DEV_CONTROLLER_TIMEOUT_SECONDS", "15"))
    controller_url = (
        (os.getenv("APPS_SANDBOX_CONTROLLER_URL") or "").strip()
        or (os.getenv("APPS_DRAFT_DEV_CONTROLLER_URL") or "").strip()
        or None
    )
    controller_token = (
        (os.getenv("APPS_SANDBOX_CONTROLLER_TOKEN") or "").strip()
        or (os.getenv("APPS_DRAFT_DEV_CONTROLLER_TOKEN") or "").strip()
        or None
    )
    preview_proxy_base_path = (os.getenv("APPS_DRAFT_DEV_PREVIEW_PROXY_BASE_PATH") or "").strip()
    if not preview_proxy_base_path:
        preview_proxy_base_path = "/public/apps-builder/draft-dev/sessions"
    if not preview_proxy_base_path.startswith("/"):
        preview_proxy_base_path = f"/{preview_proxy_base_path}"
    return PublishedAppSandboxBackendConfig(
        backend=(os.getenv("APPS_SANDBOX_BACKEND") or "").strip() or None,
        controller_url=controller_url,
        controller_token=controller_token,
        request_timeout_seconds=max(3, timeout_seconds),
        local_preview_base_url=(os.getenv("APPS_DRAFT_DEV_PREVIEW_BASE_URL") or "http://127.0.0.1:5173").strip(),
        embedded_local_enabled=is_truthy(os.getenv("APPS_DRAFT_DEV_EMBEDDED_LOCAL_ENABLED", "1"), default=True),
        preview_proxy_base_path=preview_proxy_base_path.rstrip("/"),
        e2b_template=_resolve_e2b_template_reference(
            (os.getenv("APPS_E2B_TEMPLATE") or "").strip() or None,
            (os.getenv("APPS_E2B_TEMPLATE_TAG") or "").strip() or None,
        ),
        e2b_template_tag=(os.getenv("APPS_E2B_TEMPLATE_TAG") or "").strip() or None,
        e2b_timeout_seconds=max(180, int(os.getenv("APPS_E2B_SANDBOX_TIMEOUT_SECONDS", "1800"))),
        e2b_workspace_path=(os.getenv("APPS_E2B_WORKSPACE_PATH") or "/workspace").strip() or "/workspace",
        e2b_preview_port=max(1024, int(os.getenv("APPS_E2B_PREVIEW_PORT", "4173"))),
        e2b_opencode_port=max(1024, int(os.getenv("APPS_E2B_OPENCODE_PORT", "4141"))),
        e2b_secure=is_truthy(os.getenv("APPS_E2B_SECURE", "1"), default=True),
        e2b_allow_internet_access=is_truthy(os.getenv("APPS_E2B_ALLOW_INTERNET_ACCESS", "1"), default=True),
        e2b_auto_pause=is_truthy(os.getenv("APPS_E2B_AUTO_PAUSE", "0"), default=False),
    )


def build_published_app_sandbox_backend(
    config: PublishedAppSandboxBackendConfig,
) -> PublishedAppSandboxBackend:
    backend = str(config.backend or "").strip().lower()
    if not backend:
        if config.controller_url:
            backend = "controller"
        else:
            backend = "e2b"
    if backend == "local":
        return LocalSandboxBackend(config)
    if backend == "controller":
        return ControllerSandboxBackend(config)
    if backend == "e2b":
        return E2BSandboxBackend(config)
    raise ValueError(f"Unsupported sandbox backend `{backend}`")
