from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from app.services.published_app_live_preview import (
    build_live_preview_context_payload,
    build_live_preview_watch_script,
    build_live_preview_workspace_fingerprint,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _template_node_modules() -> Path:
    return _repo_root() / "backend/app/templates/published_apps/classic-chat/node_modules"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_current_dist_text(current_path: Path) -> str:
    chunks: list[str] = []
    for candidate in sorted(current_path.rglob("*")):
        if not candidate.is_file():
            continue
        try:
            chunks.append(candidate.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return "\n".join(chunks)


def _wait_for_status(
    *,
    process: subprocess.Popen[str],
    status_path: Path,
    predicate,
    timeout_seconds: float = 60.0,
) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()
            raise AssertionError(f"watch process exited early with code {process.returncode}: {output}")
        if status_path.exists():
            payload = _read_json(status_path)
            if predicate(payload):
                return payload
        time.sleep(0.2)
    latest = _read_json(status_path) if status_path.exists() else {}
    raise AssertionError(f"timed out waiting for live preview status; latest={latest}")


@pytest.mark.skipif(not _template_node_modules().exists(), reason="classic-chat node_modules with vite is required")
def test_live_preview_watch_script_rebuilds_and_keeps_last_good(tmp_path: Path):
    workspace = tmp_path / "workspace"
    live_preview_root = workspace / ".talmudpedia/live-preview"
    src_dir = workspace / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    live_preview_root.mkdir(parents=True, exist_ok=True)

    (workspace / "package.json").write_text(
        json.dumps(
            {
                "name": "live-preview-watch-fixture",
                "private": True,
                "type": "module",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (workspace / "index.html").write_text(
        "<!doctype html><html><body><div id='app'></div><script type='module' src='/src/main.js'></script></body></html>",
        encoding="utf-8",
    )
    main_file = workspace / "src/main.js"
    main_file.write_text(
        "document.querySelector('#app').textContent = 'version-one';\n",
        encoding="utf-8",
    )
    (workspace / "node_modules").symlink_to(_template_node_modules(), target_is_directory=True)

    initial_fingerprint = build_live_preview_workspace_fingerprint(
        entry_file="src/main.js",
        files={
            "index.html": (workspace / "index.html").read_text(encoding="utf-8"),
            "src/main.js": main_file.read_text(encoding="utf-8"),
        },
    )
    (live_preview_root / "context.json").write_text(
        json.dumps(build_live_preview_context_payload(workspace_fingerprint=initial_fingerprint), indent=2),
        encoding="utf-8",
    )
    script_path = live_preview_root / "build-watch.mjs"
    script_path.write_text(
        build_live_preview_watch_script(
            live_workspace_path=str(workspace),
            live_preview_root_path=str(live_preview_root),
        ),
        encoding="utf-8",
    )

    process = subprocess.Popen(
        ["node", str(script_path)],
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        status_path = live_preview_root / "status.json"
        first_ready = _wait_for_status(
            process=process,
            status_path=status_path,
            predicate=lambda payload: payload.get("status") == "ready" and bool(payload.get("last_successful_build_id")),
        )
        first_build_id = str(first_ready["last_successful_build_id"])
        current_path = live_preview_root / "current"
        assert "version-one" in _read_current_dist_text(current_path)

        main_file.write_text(
            "document.querySelector('#app').textContent = 'version-two';\n",
            encoding="utf-8",
        )
        second_ready = _wait_for_status(
            process=process,
            status_path=status_path,
            predicate=lambda payload: payload.get("status") == "ready"
            and bool(payload.get("last_successful_build_id"))
            and str(payload.get("last_successful_build_id")) != first_build_id,
        )
        second_build_id = str(second_ready["last_successful_build_id"])
        assert "version-two" in _read_current_dist_text(current_path)

        (live_preview_root / "context.json").write_text(
            json.dumps(build_live_preview_context_payload(workspace_fingerprint="context-only-update"), indent=2),
            encoding="utf-8",
        )
        time.sleep(2.0)
        after_context_only = _read_json(status_path)
        assert str(after_context_only.get("last_successful_build_id")) == second_build_id

        main_file.write_text(
            "document.querySelector('#app').textContent = ;\n",
            encoding="utf-8",
        )
        failed_payload = _wait_for_status(
            process=process,
            status_path=status_path,
            predicate=lambda payload: payload.get("status") == "failed_keep_last_good"
            and str(payload.get("last_successful_build_id")) == second_build_id,
        )
        assert str(failed_payload.get("current_build_id") or "") != second_build_id
        assert "version-two" in _read_current_dist_text(current_path)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
