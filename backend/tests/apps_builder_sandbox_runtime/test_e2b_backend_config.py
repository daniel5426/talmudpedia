from __future__ import annotations

import pytest

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
