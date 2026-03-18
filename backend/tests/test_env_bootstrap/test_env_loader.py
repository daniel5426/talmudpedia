from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.env_loader import (
    ENV_FILE_VAR,
    ENV_PROFILE_VAR,
    load_backend_env,
    resolve_backend_env_file,
    running_under_pytest,
)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_explicit_env_file_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    explicit = backend_dir / "custom.env"
    _write(explicit, "EXPLICIT_VALUE=1\n")
    _write(backend_dir / ".env.test.example", "EXAMPLE=1\n")

    monkeypatch.setenv(ENV_FILE_VAR, str(explicit))

    resolved = resolve_backend_env_file(backend_dir=backend_dir, prefer_test_env=True)

    assert resolved == explicit.resolve()


def test_missing_explicit_env_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    explicit = backend_dir / "missing.env"
    monkeypatch.setenv(ENV_FILE_VAR, str(explicit))

    with pytest.raises(FileNotFoundError):
        resolve_backend_env_file(backend_dir=backend_dir, prefer_test_env=True)


def test_test_profile_prefers_test_example_before_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write(backend_dir / ".env", "PROFILE=dev\n")
    _write(backend_dir / ".env.test.example", "PROFILE=test\n")
    monkeypatch.delenv(ENV_FILE_VAR, raising=False)
    monkeypatch.delenv(ENV_PROFILE_VAR, raising=False)

    resolved = resolve_backend_env_file(backend_dir=backend_dir, prefer_test_env=True)

    assert resolved == (backend_dir / ".env.test.example").resolve()


def test_non_test_profile_falls_back_to_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write(backend_dir / ".env", "PROFILE=dev\n")
    _write(backend_dir / ".env.test.example", "PROFILE=test\n")
    monkeypatch.delenv(ENV_FILE_VAR, raising=False)
    monkeypatch.setenv(ENV_PROFILE_VAR, "dev")

    resolved = resolve_backend_env_file(backend_dir=backend_dir, prefer_test_env=False)

    assert resolved == (backend_dir / ".env").resolve()


def test_load_backend_env_preserves_existing_values_when_override_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write(backend_dir / ".env.test.example", "KEEP_ME=file\nNEW_VALUE=fresh\n")
    monkeypatch.delenv(ENV_FILE_VAR, raising=False)
    monkeypatch.delenv(ENV_PROFILE_VAR, raising=False)
    monkeypatch.setenv("KEEP_ME", "shell")
    monkeypatch.delenv("NEW_VALUE", raising=False)

    loaded = load_backend_env(
        backend_dir=backend_dir,
        override=False,
        prefer_test_env=True,
        required=True,
    )

    assert loaded == (backend_dir / ".env.test.example").resolve()
    assert loaded == Path(os.environ[ENV_FILE_VAR])
    assert os.environ[ENV_PROFILE_VAR] == "test"
    assert os.environ["KEEP_ME"] == "shell"
    assert os.environ["NEW_VALUE"] == "fresh"


def test_load_backend_env_returns_none_when_no_default_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    monkeypatch.delenv(ENV_FILE_VAR, raising=False)
    monkeypatch.delenv(ENV_PROFILE_VAR, raising=False)

    assert load_backend_env(
        backend_dir=backend_dir,
        override=False,
        prefer_test_env=True,
        required=False,
    ) is None


def test_running_under_pytest_detects_current_test(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "backend/tests/test_env_bootstrap/test_env_loader.py::test")
    assert running_under_pytest() is True
