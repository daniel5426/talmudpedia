import pytest

from app.services.published_app_publish_runtime import (
    _extract_command_exit_code,
    _format_command_failure,
    _resolve_npm_install_command,
)


def test_extract_command_exit_code_accepts_zero() -> None:
    assert _extract_command_exit_code({"code": 0, "stdout": "up to date"}, command_name="npm install") == 0


def test_extract_command_exit_code_rejects_missing_code() -> None:
    with pytest.raises(RuntimeError, match="missing exit code"):
        _extract_command_exit_code({"stdout": "ok"}, command_name="npm install")


def test_format_command_failure_for_invalid_code_is_clear() -> None:
    message = _format_command_failure("npm install", {"stdout": "weird"})
    assert "invalid (" in message
    assert "missing exit code" in message


def test_resolve_npm_install_command_prefers_ci_with_lockfile() -> None:
    assert _resolve_npm_install_command({"package-lock.json": "{}"}) == ["npm", "ci"]
    assert _resolve_npm_install_command({"package.json": "{}"}) == ["npm", "install", "--no-audit", "--no-fund"]
