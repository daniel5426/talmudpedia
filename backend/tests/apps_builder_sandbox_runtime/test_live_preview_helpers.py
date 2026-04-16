from __future__ import annotations

from app.services.published_app_live_preview import (
    LIVE_PREVIEW_MODE,
    LIVE_PREVIEW_WATCH_EXCLUDE_GLOBS,
    build_live_preview_watch_script,
    build_live_preview_workspace_fingerprint,
    normalize_live_preview_payload,
)


def test_normalize_live_preview_payload_preserves_ready_build_metadata():
    payload = normalize_live_preview_payload(
        {
            "status": "ready",
            "current_build_id": "build-2",
            "last_successful_build_id": "build-2",
            "workspace_fingerprint": "fp-1",
            "dist_path": "/tmp/dist",
        }
    )

    assert payload["mode"] == LIVE_PREVIEW_MODE
    assert payload["status"] == "ready"
    assert payload["current_build_id"] == "build-2"
    assert payload["last_successful_build_id"] == "build-2"
    assert payload["workspace_fingerprint"] == "fp-1"
    assert payload["dist_path"] == "/tmp/dist"


def test_normalize_live_preview_payload_maps_failed_status_to_keep_last_good_and_supervisor():
    payload = normalize_live_preview_payload(
        {
            "status": "failed",
            "last_successful_build_id": "build-1",
            "error": "build exploded",
            "supervisor": {
                "build_watch_status": "running",
                "static_server_status": "running",
                "restart_reason": "heartbeat_repair",
            },
        }
    )

    assert payload["status"] == "failed_keep_last_good"
    assert payload["last_successful_build_id"] == "build-1"
    assert payload["supervisor"]["build_watch_status"] == "running"
    assert payload["supervisor"]["restart_reason"] == "heartbeat_repair"


def test_build_live_preview_workspace_fingerprint_is_stable_for_sorted_files():
    first = build_live_preview_workspace_fingerprint(
        entry_file="src/main.tsx",
        files={
            "src/App.tsx": "export default function App() { return null; }",
            "src/main.tsx": "console.log('hi')",
        },
    )
    second = build_live_preview_workspace_fingerprint(
        entry_file="src/main.tsx",
        files={
            "src/main.tsx": "console.log('hi')",
            "src/App.tsx": "export default function App() { return null; }",
        },
    )

    assert first == second


def test_build_live_preview_watch_script_uses_vite_watch_and_excludes_generated_paths():
    script = build_live_preview_watch_script(
        live_workspace_path="/workspace/app",
        live_preview_root_path="/workspace/app/.talmudpedia/live-preview",
    )

    assert "watcher.on(\"event\"" in script
    assert "watch: {" in script
    assert "setInterval(" not in script
    assert "revision_token_changed" not in script
    for pattern in LIVE_PREVIEW_WATCH_EXCLUDE_GLOBS:
        assert pattern in script
