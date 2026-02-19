# Coding Agent Per-Run Sandbox Isolation Implementation

Last Updated: 2026-02-19

## Scope Implemented in This Change
- Added run-scoped sandbox session persistence for coding-agent runs.
- Added runtime wiring so coding-agent runs initialize sandbox context before execution.
- Added fail-closed stream behavior when a run lacks sandbox context.
- Added OpenCode sandbox-controller routing path (`start`, `stream`, `cancel`) in client integration.
- Added OpenCode workspace path violation guard that fails closed and aborts upstream run.
- Added API response metadata fields for sandbox observability.
- Fixed completed-run ordering so sandbox file snapshot/apply occurs before sandbox teardown.
- Added OpenCode context fallback so `coding_run_sandbox_*` metadata can drive engine start when `opencode_*` keys are absent.
- Added best-effort sync of existing builder draft session after auto-apply so preview reflects completed coding-run edits.
- Added workspace-path propagation from sandbox `/sessions/start` into persisted run sandbox context to avoid ambiguous `/workspace` defaults in local shim workflows.
- Hardened dev shim OpenCode start path to fail closed when sandbox workspace is not active (no payload-path fallback).
- Added coding-run create behavior to snapshot active builder draft sandbox files into a fresh draft revision before run start, so run sandbox seeds from live builder code instead of stale template revisions.
- Updated local shim OpenCode execution to support sandbox-scoped OpenCode server processes (`cwd` bound to sandbox workspace) so OpenCode project root aligns with the same draft preview sandbox.

## Backend Changes
- New DB model + migration:
  - `backend/app/db/postgres/models/published_apps.py`
  - `backend/alembic/versions/c7f1a2b3d4e5_add_coding_run_sandbox_sessions.py`
- New run sandbox service:
  - `backend/app/services/published_app_coding_run_sandbox_service.py`
- Runtime integration:
  - `backend/app/services/published_app_coding_agent_runtime.py`
  - `backend/app/services/published_app_coding_agent_tools.py`
- OpenCode integration and guards:
  - `backend/app/services/opencode_server_client.py`
  - `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
- OpenCode host bootstrap hardening:
  - `backend/main.py`
- Local sandbox-controller dev shim (controller-compatible routes backed by embedded local runtime):
  - `backend/app/api/routers/sandbox_controller_dev_shim.py`
  - Mounted in `backend/main.py` at `/internal/sandbox-controller/*`

## Local Dev Shim Notes
- Enable shim mode with:
  - `APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED=1`
- Point controller URL at backend shim path:
  - `APPS_DRAFT_DEV_CONTROLLER_URL=http://127.0.0.1:8000/internal/sandbox-controller`
  - or `APPS_SANDBOX_CONTROLLER_URL=http://127.0.0.1:8000/internal/sandbox-controller`
- Optional auth token:
  - `APPS_SANDBOX_CONTROLLER_TOKEN=<token>` (or `APPS_DRAFT_DEV_CONTROLLER_TOKEN`)
- Shim supports:
  - Session lifecycle (`/sessions/start`, `sync`, `heartbeat`, `stop`)
  - File and command endpoints used by coding tools
  - OpenCode controller routes (`/opencode/start`, `events`, `cancel`) for local testing
  - Optional sandbox-scoped OpenCode process mode enabled by default via `APPS_SANDBOX_CONTROLLER_DEV_SHIM_OPENCODE_PER_SANDBOX=1` (set to `0` to use shared host OpenCode mode).

## API Contract Additions
- `CodingAgentRunResponse` now includes:
  - `sandbox_id?: string`
  - `sandbox_status?: string`
  - `sandbox_started_at?: datetime`
- File:
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent.py`

## Config Additions / Behavior
- `APPS_SANDBOX_CONTROLLER_URL` and `APPS_SANDBOX_CONTROLLER_TOKEN` are now accepted by draft-dev runtime client configuration (fallback-compatible with existing draft-dev controller vars).
- `APPS_CODING_AGENT_SANDBOX_REQUIRED=1` enforces OpenCode sandbox-controller availability.
- Local OpenCode auto-bootstrap now defaults to off unless explicitly enabled (`APPS_CODING_AGENT_OPENCODE_AUTO_BOOTSTRAP=1`).

## Tests Added
- `backend/tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py`
- `backend/tests/sandbox_controller/test_opencode_controller_proxy.py`

## Follow-ups Not Yet Implemented
- Per-tenant/global concurrency admission queueing for run sandboxes.
- Full controller service implementation/deployment (this change wires client/runtime contracts and guarded behavior).
- Egress policy monitoring and billing/quota enforcement.
