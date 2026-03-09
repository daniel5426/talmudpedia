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
from app.services.published_app_sandbox_backend_sprite import SpriteSandboxBackend


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
    backend = (os.getenv("APPS_SANDBOX_BACKEND") or "sprite").strip().lower()
    if backend != "sprite":
        return

    api_key = (
        (os.getenv("APPS_SPRITE_API_TOKEN") or "").strip()
        or (os.getenv("SPRITES_TOKEN") or "").strip()
        or (os.getenv("SPRITE_API_TOKEN") or "").strip()
    )
    if not api_key:
        raise RuntimeError(
            "APPS_SANDBOX_BACKEND=sprite requires APPS_SPRITE_API_TOKEN (or SPRITES_TOKEN) to be set."
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
        backend=(os.getenv("APPS_SANDBOX_BACKEND") or "sprite").strip() or "sprite",
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
        sprite_api_base_url=(os.getenv("APPS_SPRITE_API_BASE_URL") or "https://api.sprites.dev").strip(),
        sprite_api_token=(
            (os.getenv("APPS_SPRITE_API_TOKEN") or "").strip()
            or (os.getenv("SPRITES_TOKEN") or "").strip()
            or (os.getenv("SPRITE_API_TOKEN") or "").strip()
            or None
        ),
        sprite_name_prefix=(os.getenv("APPS_SPRITE_NAME_PREFIX") or "app-builder").strip() or "app-builder",
        sprite_workspace_path=(os.getenv("APPS_SPRITE_WORKSPACE_PATH") or "/home/sprite/app").strip() or "/home/sprite/app",
        sprite_stage_workspace_path=(os.getenv("APPS_SPRITE_STAGE_WORKSPACE_PATH") or "").strip() or None,
        sprite_publish_workspace_path=(os.getenv("APPS_SPRITE_PUBLISH_WORKSPACE_PATH") or "").strip() or None,
        sprite_preview_port=max(1024, int(os.getenv("APPS_SPRITE_PREVIEW_PORT", "8080"))),
        sprite_opencode_port=max(1024, int(os.getenv("APPS_SPRITE_OPENCODE_PORT", "4141"))),
        sprite_preview_service_name=(os.getenv("APPS_SPRITE_PREVIEW_SERVICE_NAME") or "builder-preview").strip() or "builder-preview",
        sprite_opencode_service_name=(os.getenv("APPS_SPRITE_OPENCODE_SERVICE_NAME") or "opencode").strip() or "opencode",
        sprite_opencode_command=(os.getenv("APPS_SPRITE_OPENCODE_COMMAND") or "").strip() or None,
        sprite_command_timeout_seconds=max(30, int(os.getenv("APPS_SPRITE_COMMAND_TIMEOUT_SECONDS", "900"))),
        sprite_retention_seconds=max(300, int(os.getenv("APPS_SPRITE_RETENTION_SECONDS", "21600"))),
        sprite_network_policy=(os.getenv("APPS_SPRITE_NETWORK_POLICY") or "").strip() or None,
    )


def build_published_app_sandbox_backend(
    config: PublishedAppSandboxBackendConfig,
) -> PublishedAppSandboxBackend:
    backend = str(config.backend or "").strip().lower()
    if not backend:
        if config.controller_url:
            backend = "controller"
        else:
            backend = "sprite"
    if backend == "local":
        return LocalSandboxBackend(config)
    if backend == "controller":
        return ControllerSandboxBackend(config)
    if backend == "sprite":
        return SpriteSandboxBackend(config)
    if backend == "e2b":
        raise ValueError("E2B is archived for App Builder. Configure APPS_SANDBOX_BACKEND=sprite.")
    raise ValueError(f"Unsupported sandbox backend `{backend}`")
