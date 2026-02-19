# Sandbox Controller Tests

Last Updated: 2026-02-19

## Scope of the feature
- Backend-to-sandbox-controller proxy behavior for OpenCode run lifecycle calls.
- Controller-mode routing (`start`, `stream`, `cancel`) for run-scoped OpenCode sessions.

## Test files present
- `backend/tests/sandbox_controller/test_opencode_controller_proxy.py`
- `backend/tests/sandbox_controller/test_dev_shim.py`

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
- Dev shim stops sandbox-scoped OpenCode process when draft sandbox session is stopped.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest tests/sandbox_controller/test_dev_shim.py tests/sandbox_controller/test_opencode_controller_proxy.py -q`
- Date: 2026-02-19 03:21:28 EET
- Result: PASS (8 passed overall, sandbox-controller suites)

## Known gaps or follow-ups
- Add integration tests against a real sandbox-controller deployment once the controller service is live.
