from __future__ import annotations

import pytest

from app.services.published_app_sandbox_backend import PublishedAppSandboxBackendConfig
from app.services.published_app_sandbox_backend_e2b import E2BSandboxBackend
from app.services.published_app_sandbox_backend_factory import (
    load_published_app_sandbox_backend_config,
    validate_published_app_sandbox_backend_env,
)


def test_validate_e2b_backend_env_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    monkeypatch.setenv("APPS_E2B_TEMPLATE", "talmudpedia-app-builder-dev")

    with pytest.raises(RuntimeError, match="E2B_API_KEY"):
        validate_published_app_sandbox_backend_env()


def test_validate_e2b_backend_env_requires_template_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.delenv("APPS_E2B_TEMPLATE", raising=False)
    monkeypatch.delenv("APPS_E2B_ALLOW_DEFAULT_TEMPLATE", raising=False)

    with pytest.raises(RuntimeError, match="APPS_E2B_TEMPLATE"):
        validate_published_app_sandbox_backend_env()


def test_validate_e2b_backend_env_accepts_template_plus_tag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("APPS_E2B_TEMPLATE", "talmudpedia-app-builder-dev")
    monkeypatch.setenv("APPS_E2B_TEMPLATE_TAG", "apps-builder")

    validate_published_app_sandbox_backend_env()


def test_validate_e2b_backend_env_allows_default_template_only_when_explicit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.delenv("APPS_E2B_TEMPLATE", raising=False)
    monkeypatch.setenv("APPS_E2B_ALLOW_DEFAULT_TEMPLATE", "1")

    validate_published_app_sandbox_backend_env()


def test_load_backend_config_reads_explicit_e2b_template(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("APPS_E2B_TEMPLATE", "talmudpedia-app-builder-dev")
    monkeypatch.setenv("APPS_E2B_TEMPLATE_TAG", "apps-builder")

    config = load_published_app_sandbox_backend_config()

    assert config.backend == "e2b"
    assert config.e2b_template == "talmudpedia-app-builder-dev:apps-builder"
    assert config.e2b_template_tag == "apps-builder"


def test_e2b_backend_forwards_only_non_empty_provider_envs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_DEFAULT_MODEL", "openai/gpt-5-chat-latest")
    monkeypatch.setenv("APPS_E2B_FORWARD_ENV_NAMES", "CUSTOM_ONE,CUSTOM_TWO")
    monkeypatch.setenv("CUSTOM_ONE", "custom-one")
    monkeypatch.setenv("CUSTOM_TWO", "")

    backend = E2BSandboxBackend(
        PublishedAppSandboxBackendConfig(
            backend="e2b",
            controller_url=None,
            controller_token=None,
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
            preview_proxy_base_path="/public/apps-builder/draft-dev/sessions",
            e2b_template="talmudpedia-app-builder-dev:apps-builder",
            e2b_template_tag="apps-builder",
            e2b_timeout_seconds=1800,
            e2b_workspace_path="/workspace",
            e2b_preview_port=4173,
            e2b_opencode_port=4141,
            e2b_secure=True,
            e2b_allow_internet_access=True,
            e2b_auto_pause=False,
        )
    )

    forwarded = backend._sandbox_envs()

    assert forwarded == {
        "OPENAI_API_KEY": "openai-key",
        "GEMINI_API_KEY": "gemini-key",
        "APPS_CODING_AGENT_OPENCODE_DEFAULT_MODEL": "openai/gpt-5-chat-latest",
        "CUSTOM_ONE": "custom-one",
    }
