# Apps Publish Sandbox Test State

Last Updated: 2026-02-26

## Scope
Sandbox-based publish flow for Apps Builder (WYSIWYG live preview source), with focus on publish route guards and sandbox workspace plumbing.

## Test Files Present
- `backend/tests/apps_publish_sandbox/test_publish_route_guards.py`
- `backend/tests/apps_publish_sandbox/test_publish_runtime_helpers.py`
- `backend/tests/apps_publish_sandbox/test_local_publish_dependency_reuse.py`

## Key Scenarios Covered
- Publish requires an active draft-dev session when sandbox publish mode is enabled.
- Publish rejects a second publish request when an active publish job already exists for the app.
- Publish runtime command exit-code parsing handles `code=0` correctly and reports malformed command results clearly.
- Publish dependency prep reuses live sandbox `node_modules` into the isolated publish workspace (or reports install-fallback status when unavailable).

## Last Run
- Command: `pytest -q backend/tests/apps_publish_sandbox`
- Date/Time: 2026-02-26 (local run during implementation)
- Result: pass (8 passed)

## Known Gaps / Follow-Ups
- Happy-path sandbox publish success (mock build + published revision finalize).
- Full sandbox publish service integration paths (reuse -> skip install, install fallback, `npm run build`, archive export).
- Session stop/expiry lock behavior during active publish.
- Publish polling `stage` field assertions.
