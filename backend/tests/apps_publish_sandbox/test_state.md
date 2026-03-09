# Apps Publish Sandbox Test State

Last Updated: 2026-03-09

## Scope
Sandbox-based publish flow for Apps Builder (WYSIWYG live preview source), with focus on publish route guards, live-workspace builds, and dependency reuse behavior.

## Test Files Present
- `backend/tests/apps_publish_sandbox/test_publish_route_guards.py`
- `backend/tests/apps_publish_sandbox/test_publish_runtime_helpers.py`
- `backend/tests/apps_publish_sandbox/test_local_publish_dependency_reuse.py`

## Key Scenarios Covered
- Publish requires an active draft-dev session when sandbox publish mode is enabled.
- Publish rejects a second publish request when an active publish job already exists for the app.
- Publish runtime command exit-code parsing handles `code=0` correctly and reports malformed command results clearly.
- Publish dependency prep reuses the live workspace directly when `node_modules` is already present (or reports install-fallback status when unavailable).

## Last Run
- Command: `cd backend && set -a && source .env >/dev/null 2>&1 && PYTHONPATH=. pytest -q tests/apps_publish_sandbox/test_local_publish_dependency_reuse.py tests/apps_publish_sandbox/test_publish_runtime_helpers.py`
- Date/Time: 2026-03-09 19:03 EET
- Result: PASS (4 passed, included in targeted 29-pass sandbox/builder validation run)

## Known Gaps / Follow-Ups
- Happy-path sandbox publish success (mock build + published revision finalize).
- Full sandbox publish service integration paths (reuse -> skip install, install fallback, `npm run build`, archive export) against live-workspace publish.
- Session stop/expiry lock behavior during active publish.
- Publish polling `stage` field assertions.
