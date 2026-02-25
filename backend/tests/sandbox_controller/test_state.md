# Sandbox Controller Tests

Last Updated: 2026-02-24

## Scope of the feature
- Backend-to-sandbox-controller proxy behavior for OpenCode run lifecycle calls.
- Controller-mode routing (`start`, `stream`, `cancel`) for run-scoped OpenCode sessions.

## Test files present
- `backend/tests/sandbox_controller/test_opencode_controller_proxy.py`
- `backend/tests/sandbox_controller/test_dev_shim.py`
- `backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py`

## Key scenarios covered
- `OpenCodeServerClient.start_run` routes to `POST /sessions/{sandbox_id}/opencode/start` when sandbox-controller mode is enabled.
- `OpenCodeServerClient.stream_run_events` consumes controller stream events for a run-scoped sandbox ref.
- `OpenCodeServerClient.cancel_run` routes cancellation to `POST /sessions/{sandbox_id}/opencode/cancel`.
- OpenCode sandbox mode is detected when only `APPS_DRAFT_DEV_CONTROLLER_URL` is configured (without requiring `APPS_CODING_AGENT_OPENCODE_BASE_URL`).
- OpenCode sandbox mode remains enabled when `APPS_CODING_AGENT_OPENCODE_ENABLED=0` as long as controller URL configuration is present.
- Dev shim exposes local controller-compatible session/file/command endpoints under `/internal/sandbox-controller/sessions/*`.
- Dev shim proxies OpenCode lifecycle (`start`, `events`, `cancel`) through controller-compatible endpoints for local testing.
- Dev shim `POST /sessions/start` returns controller session metadata including `workspace_path`.
- Dev shim OpenCode start fails closed with `400` when draft sandbox is not running (no payload workspace fallback).
- Dev shim can run OpenCode in sandbox-scoped mode (per-sandbox OpenCode server rooted at sandbox workspace) and routes OpenCode start through that scoped client.
- Dev shim OpenCode start maps virtual `/workspace/...` paths to the resolved sandbox project root so stage workspaces are honored instead of falling back to live workspace.
- Dev shim OpenCode start now fails closed when a requested stage workspace path cannot be resolved to an existing in-project directory (prevents silent fallback to live workspace edits).
- Dev shim stops sandbox-scoped OpenCode process when draft sandbox session is stopped.
- Dev shim cancel now supports deterministic run shutdown semantics with explicit `run.cancelled` terminal events.
- Draft-dev runtime client OpenCode event streaming uses SSE-friendly timeout config (no read timeout by default) to avoid mid-run stream drops.
- Draft-dev runtime client stream errors now include a fallback exception class label when exception text is empty.
- Draft-dev runtime client OpenCode start now supports a dedicated timeout override (`APPS_DRAFT_DEV_CONTROLLER_OPENCODE_START_TIMEOUT_SECONDS`) and defaults to a longer timeout than generic controller calls.
- Draft-dev runtime client OpenCode question answers now use a dedicated timeout override (`APPS_DRAFT_DEV_CONTROLLER_OPENCODE_QUESTION_TIMEOUT_SECONDS`) and default to a longer timeout than generic controller calls.
- Draft-dev runtime client OpenCode start errors now include exception class fallback when exception text is empty.
- Draft-dev runtime client draft-preview `start_session` and `sync_session` now use dedicated controller timeout overrides (`APPS_DRAFT_DEV_CONTROLLER_START_TIMEOUT_SECONDS`, `APPS_DRAFT_DEV_CONTROLLER_SYNC_TIMEOUT_SECONDS`) to prevent cold-bootstrap ReadTimeout failures.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_draft_dev_runtime_client_stream.py::test_start_session_uses_dedicated_start_timeout tests/sandbox_controller/test_draft_dev_runtime_client_stream.py::test_sync_session_uses_dedicated_sync_timeout tests/published_apps/test_builder_revisions.py::test_draft_dev_session_preview_url_includes_runtime_context`
- Date: 2026-02-24
- Result: PASS (3 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/sandbox_controller/test_draft_dev_runtime_client_stream.py::test_answer_opencode_question_uses_dedicated_timeout tests/coding_agent_api/test_v2_api.py::test_v2_answer_question_endpoint tests/sandbox_controller/test_dev_shim.py::test_dev_shim_opencode_question_answer`
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
