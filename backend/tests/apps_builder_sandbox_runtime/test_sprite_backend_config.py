from __future__ import annotations

import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.services import published_app_sandbox_backend_sprite as backend_module
from app.services.published_app_sandbox_backend_factory import (
    build_published_app_sandbox_backend,
    load_published_app_sandbox_backend_config,
    validate_published_app_sandbox_backend_env,
)
from app.services.published_app_sandbox_backend_sprite import SpriteSandboxBackend


def test_validate_sprite_backend_env_requires_api_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "sprite")
    monkeypatch.delenv("APPS_SPRITE_API_TOKEN", raising=False)
    monkeypatch.delenv("SPRITES_TOKEN", raising=False)
    monkeypatch.delenv("SPRITE_API_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="APPS_SPRITE_API_TOKEN"):
        validate_published_app_sandbox_backend_env()


def test_validate_sprite_backend_env_accepts_primary_or_alias_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "sprite")
    monkeypatch.delenv("APPS_SPRITE_API_TOKEN", raising=False)
    monkeypatch.setenv("SPRITES_TOKEN", "sprite-token")

    validate_published_app_sandbox_backend_env()


def test_load_backend_config_defaults_to_sprite(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APPS_SANDBOX_BACKEND", raising=False)
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    monkeypatch.setenv("APPS_SPRITE_NAME_PREFIX", "talmudpedia-builder")
    monkeypatch.setenv("APPS_SPRITE_WORKSPACE_PATH", "/home/sprite/app")

    config = load_published_app_sandbox_backend_config()

    assert config.backend == "sprite"
    assert config.sprite_api_token == "sprite-token"
    assert config.sprite_name_prefix == "talmudpedia-builder"
    assert config.sprite_workspace_path == "/home/sprite/app"
    assert config.sprite_stage_workspace_path == "/home/sprite/.talmudpedia/stage/current/workspace"
    assert config.sprite_preview_service_name == "builder-preview"


def test_sprite_backend_default_stage_path_lives_outside_live_workspace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    config = load_published_app_sandbox_backend_config()

    backend = build_published_app_sandbox_backend(config)
    assert isinstance(backend, SpriteSandboxBackend)

    assert backend._live_workspace_path() == "/home/sprite/app"
    assert backend._stage_workspace_path() == "/home/sprite/.talmudpedia/stage/current/workspace"
    assert "node_modules/" in backend_module._SYNC_IGNORE_PREFIXES


def test_build_backend_returns_sprite_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    config = load_published_app_sandbox_backend_config()

    backend = build_published_app_sandbox_backend(config)

    assert isinstance(backend, SpriteSandboxBackend)


def test_build_backend_rejects_archived_e2b(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    config = load_published_app_sandbox_backend_config()

    with pytest.raises(ValueError, match="E2B is archived"):
        build_published_app_sandbox_backend(config)


@pytest.mark.asyncio
async def test_sprite_heartbeat_waits_for_preview_without_restarting_services(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    backend = build_published_app_sandbox_backend(load_published_app_sandbox_backend_config())
    assert isinstance(backend, SpriteSandboxBackend)

    waited = {"called": False}

    async def _fake_get_sprite(*, sprite_name: str):
        assert sprite_name == "sprite-app-1"
        return {"url": "https://fresh-sprite-host.example"}

    async def _fake_wait_for_preview_ready(*, sprite_name: str) -> None:
        assert sprite_name == "sprite-app-1"
        waited["called"] = True

    async def _fake_read_revision_token(**kwargs) -> str:
        _ = kwargs
        return "revision-token-1"

    async def _fail_ensure_services(*, sprite_name: str) -> None:
        raise AssertionError(f"heartbeat should not restart services for {sprite_name}")

    monkeypatch.setattr(backend, "_get_sprite", _fake_get_sprite)
    monkeypatch.setattr(backend, "_wait_for_preview_ready", _fake_wait_for_preview_ready)
    monkeypatch.setattr(backend, "_ensure_services", _fail_ensure_services)
    monkeypatch.setattr(backend, "_read_revision_token", _fake_read_revision_token)

    result = await backend.heartbeat_session(sandbox_id="sprite-app-1", idle_timeout_seconds=180)

    assert result["status"] == "serving"
    assert waited["called"] is True
    assert result["backend_metadata"]["preview"]["upstream_base_url"] == "https://fresh-sprite-host.example"


@pytest.mark.asyncio
async def test_sprite_promote_stage_workspace_mirrors_in_place_without_service_restart(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    backend = build_published_app_sandbox_backend(load_published_app_sandbox_backend_config())
    assert isinstance(backend, SpriteSandboxBackend)

    mirrored = SimpleNamespace(called=False, sprite_name=None, source=None, target=None)

    async def _fake_mirror_workspace(*, sprite_name: str, source_workspace_path: str, target_workspace_path: str) -> None:
        mirrored.called = True
        mirrored.sprite_name = sprite_name
        mirrored.source = source_workspace_path
        mirrored.target = target_workspace_path

    async def _fail_ensure_services(*, sprite_name: str) -> None:
        raise AssertionError(f"promote should not restart services for {sprite_name}")

    monkeypatch.setattr(backend, "_mirror_workspace", _fake_mirror_workspace)
    monkeypatch.setattr(backend, "_ensure_services", _fail_ensure_services)

    result = await backend.promote_stage_workspace(sandbox_id="sprite-app-1")

    assert result["status"] == "promoted"
    assert mirrored.called is True
    assert mirrored.sprite_name == "sprite-app-1"
    assert mirrored.source == backend._stage_workspace_path()
    assert mirrored.target == backend._live_workspace_path()


@pytest.mark.asyncio
async def test_sprite_start_repairs_dependencies_when_preview_readiness_initially_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    backend = build_published_app_sandbox_backend(load_published_app_sandbox_backend_config())
    assert isinstance(backend, SpriteSandboxBackend)

    install_calls: list[bool] = []
    ready_attempts = {"count": 0}
    ensure_calls = {"count": 0}

    async def _fake_ensure_sprite(*, sprite_name: str):
        return {"name": sprite_name, "url": f"https://{sprite_name}.sprites.app"}

    async def _fake_ensure_workspace_dirs(*, sprite_name: str):
        return None

    async def _fake_sync_files_to_workspace(*, sprite_name: str, workspace_path: str, files):
        return "revision-token-1"

    async def _fake_install_dependencies_if_needed(*, sprite_name: str, workspace_path: str, dependency_hash: str, force_install: bool):
        install_calls.append(force_install)

    async def _fake_ensure_services(*, sprite_name: str):
        ensure_calls["count"] += 1

    async def _fake_wait_for_preview_ready(*, sprite_name: str):
        ready_attempts["count"] += 1
        if ready_attempts["count"] == 1:
            raise RuntimeError("preview warmup failed")

    monkeypatch.setattr(backend, "_ensure_sprite", _fake_ensure_sprite)
    monkeypatch.setattr(backend, "_ensure_workspace_dirs", _fake_ensure_workspace_dirs)
    monkeypatch.setattr(backend, "_sync_files_to_workspace", _fake_sync_files_to_workspace)
    monkeypatch.setattr(backend, "_install_dependencies_if_needed", _fake_install_dependencies_if_needed)
    monkeypatch.setattr(backend, "_ensure_services", _fake_ensure_services)
    monkeypatch.setattr(backend, "_wait_for_preview_ready", _fake_wait_for_preview_ready)

    result = await backend.start_session(
        session_id="workspace-1",
        runtime_generation=1,
        tenant_id="tenant-1",
        app_id="app-1",
        user_id="user-1",
        revision_id="revision-1",
        entry_file="src/main.tsx",
        files={"src/main.tsx": "console.log(1)"},
        idle_timeout_seconds=180,
        dependency_hash="dep-hash-1",
        draft_dev_token="draft-token",
        preview_base_path="/public/apps-builder/draft-dev/sessions/session-1/preview/",
    )

    assert result["status"] == "serving"
    assert install_calls == [False, True]
    assert ensure_calls["count"] == 2
    assert ready_attempts["count"] == 2


@pytest.mark.asyncio
async def test_sprite_snapshot_workspace_filters_generated_paths_before_serializing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("APPS_SPRITE_API_TOKEN", "sprite-token")
    backend = build_published_app_sandbox_backend(load_published_app_sandbox_backend_config())
    assert isinstance(backend, SpriteSandboxBackend)

    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (workspace / ".cache" / "opencode").mkdir(parents=True, exist_ok=True)
    (workspace / "dist").mkdir(parents=True, exist_ok=True)
    (workspace / ".talmudpedia").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "App.tsx").write_text("export default function App() { return null; }\n", encoding="utf-8")
    (workspace / "node_modules" / "pkg" / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (workspace / ".cache" / "opencode" / "selected_agent_contract.json").write_text("{}", encoding="utf-8")
    (workspace / "dist" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (workspace / ".talmudpedia" / "runtime-revision-token").write_text("rev-1", encoding="utf-8")

    async def _run_script_locally(
        *,
        sprite_name: str,
        command: list[str],
        stdin_text: str,
        cwd: str | None = None,
        timeout_seconds: int,
        max_output_bytes: int,
        allow_nonzero: bool = False,
    ):
        _ = sprite_name, command, cwd, timeout_seconds, max_output_bytes, allow_nonzero
        completed = subprocess.run(
            ["python3", "-"],
            input=stdin_text,
            text=True,
            capture_output=True,
            check=True,
        )
        return completed.stdout, 0

    monkeypatch.setattr(backend, "_exec_with_stdin", _run_script_locally)

    snapshot = await backend._snapshot_workspace_files(  # noqa: SLF001
        sprite_name="sprite-app-1",
        workspace_path=str(workspace),
    )

    assert snapshot["file_count"] == 1
    assert snapshot["files"] == {"src/App.tsx": "export default function App() { return null; }\n"}
    assert snapshot["revision_token"] == "rev-1"
