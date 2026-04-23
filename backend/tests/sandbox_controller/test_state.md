# Sandbox Controller Tests

Last Updated: 2026-04-23

## Scope of the feature
- Backend-to-sandbox-controller endpoint discovery and local dev-shim behavior.
- Controller-mode routing for persistent OpenCode sessions via nested official clients.

## Test files present
- `backend/tests/sandbox_controller/test_opencode_controller_proxy.py`
- `backend/tests/sandbox_controller/test_dev_shim.py`
- `backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py`

## Key scenarios covered
- `PublishedAppDraftDevRuntimeClient.ensure_opencode_endpoint(...)` uses the dedicated controller timeout and returns `{base_url, workspace_path, extra_headers}`.
- `OpenCodeServerClient` reuses controller-discovered official clients instead of proxying run/session RPCs through the controller backend.
- `OpenCodeServerClient.stream_turn_events` and `cancel_turn` can attach to the nested official sandbox client using explicit `sandbox_id` + `workspace_path`.
- OpenCode sandbox mode is detected when only `APPS_DRAFT_DEV_CONTROLLER_URL` is configured (without requiring `APPS_CODING_AGENT_OPENCODE_BASE_URL`).
- OpenCode sandbox mode remains enabled when `APPS_CODING_AGENT_OPENCODE_ENABLED=0` as long as controller URL configuration is present.
- Sprite-backed App Builder runtime forces OpenCode sandbox mode even if the legacy `APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER=0` flag is still present.
- Dev shim exposes local controller-compatible session/file/command endpoints under `/internal/sandbox-controller/sessions/*`.
- Dev shim exposes `POST /sessions/{sandbox_id}/opencode/endpoint` for local endpoint discovery and keeps controller-compatible local testing paths wired correctly.
- Dev shim `POST /sessions/start` returns controller session metadata including `workspace_path`.
- Dev shim endpoint discovery fails closed with `400` when draft sandbox is not running (no payload workspace fallback).
- Dev shim can run OpenCode in sandbox-scoped mode (per-sandbox OpenCode server rooted at sandbox workspace) and returns that scoped endpoint.
- Dev shim endpoint discovery maps virtual `/workspace/...` paths to the resolved sandbox project root so stage workspaces are honored instead of falling back to live workspace.
- Dev shim endpoint discovery fails closed when a requested stage workspace path cannot be resolved to an existing in-project directory.
- Dev shim stops sandbox-scoped OpenCode process when draft sandbox session is stopped.
- Draft-dev runtime client OpenCode event streaming uses SSE-friendly timeout config (no read timeout by default) to avoid mid-run stream drops.
- Draft-dev runtime client stream errors now include a fallback exception class label when exception text is empty.
- Draft-dev runtime client OpenCode start now supports a dedicated timeout override (`APPS_DRAFT_DEV_CONTROLLER_OPENCODE_START_TIMEOUT_SECONDS`) and defaults to a longer timeout than generic controller calls.
- Draft-dev runtime client draft-preview `start_session` and `sync_session` now use dedicated controller timeout overrides (`APPS_DRAFT_DEV_CONTROLLER_START_TIMEOUT_SECONDS`, `APPS_DRAFT_DEV_CONTROLLER_SYNC_TIMEOUT_SECONDS`) to prevent cold-bootstrap ReadTimeout failures.

## Last run command + date/time + result
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py backend/tests/sandbox_controller/test_opencode_controller_proxy.py backend/tests/sandbox_controller/test_dev_shim.py backend/tests/opencode_server_client/test_opencode_server_client.py backend/tests/coding_agent_api/test_v2_api.py backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- Date: 2026-04-16 18:25 EEST
- Result: PASS (71 passed, 8 warnings)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py backend/tests/sandbox_controller/test_opencode_controller_proxy.py backend/tests/sandbox_controller/test_dev_shim.py`
- Date: 2026-04-16 18:42 Asia/Hebron
- Result: PASS (17 passed, 8 warnings)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py backend/tests/published_apps/test_public_app_resolve_and_config.py backend/tests/sandbox_controller/test_dev_shim.py backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py backend/tests/app_versions/test_versions_endpoints.py`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`40 passed`). Controller/dev-shim runtime-client coverage now reflects `app_public_id` instead of the removed slug-era session payload.
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/sandbox_controller/test_opencode_controller_proxy.py tests/apps_builder_sandbox_runtime/test_sprite_backend_config.py`
- Date: 2026-03-09 01:36 EET
- Result: PASS (12 passed, 1 warning)
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/sandbox_controller/test_opencode_controller_proxy.py tests/opencode_server_client/test_opencode_server_client.py -k 'sprite_backend_forces_sandbox_mode_even_when_legacy_controller_flag_is_off or sandbox_controller_mode_is_enabled_even_when_opencode_flag_off or sandbox_controller_mode_detected_from_draft_dev_controller_url or start_run_routes_via_sandbox_controller or stream_and_cancel_route_via_sandbox_controller'`
- Date: 2026-03-09 00:26 EET
- Result: PASS (5 passed, 38 deselected, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_draft_dev_runtime_client_stream.py tests/sandbox_controller/test_dev_shim.py`
- Date: 2026-03-08 16:19:45 EET
- Result: PASS (16 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_draft_dev_runtime_client_stream.py::test_start_session_uses_dedicated_start_timeout tests/sandbox_controller/test_draft_dev_runtime_client_stream.py::test_sync_session_uses_dedicated_sync_timeout tests/published_apps/test_builder_revisions.py::test_draft_dev_session_preview_url_includes_runtime_context`
- Date: 2026-02-24
- Result: PASS (3 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py tests/sandbox_controller/test_dev_shim.py`
- Date: 2026-02-23
- Result: PASS (11 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_dev_shim.py tests/sandbox_controller/test_opencode_controller_proxy.py`
- Date: 2026-02-24
- Result: PASS (13 passed, 7 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_draft_dev_runtime_client_stream.py tests/opencode_server_client/test_opencode_server_client.py tests/sandbox_controller/test_dev_shim.py tests/sandbox_controller/test_opencode_controller_proxy.py`
- Date: 2026-02-19 22:28 UTC
- Result: PASS (33 passed overall)
- Command: `cd backend && PYTHONPATH=. pytest tests/sandbox_controller/test_draft_dev_runtime_client_stream.py tests/sandbox_controller/test_dev_shim.py tests/sandbox_controller/test_opencode_controller_proxy.py -q`
- Date: 2026-02-19 03:37:58 EET
- Result: PASS (10 passed overall, sandbox-controller suites)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_dev_shim.py tests/sandbox_controller/test_opencode_controller_proxy.py`
- Date: 2026-02-22 01:52 UTC
- Result: PASS (12 passed)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py`
- Date: 2026-02-22 01:43 UTC
- Result: PASS (27 passed)

## Known gaps or follow-ups
- Add integration tests against a real sandbox-controller deployment once the controller service is live.
