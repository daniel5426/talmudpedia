# Apps Publish Sandbox Test State

Last Updated: 2026-04-16

## Scope
Residual draft-dev local-runtime dependency reuse coverage. The legacy sandbox publish runtime coverage was removed with the pointer-only publish hard cut.

## Test Files Present
- `backend/tests/apps_publish_sandbox/test_local_publish_dependency_reuse.py`

## Key Scenarios Covered
- Publish dependency prep reuses the live workspace directly when `node_modules` is already present (or reports install-fallback status when unavailable).

## Last Run
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_publish_sandbox/test_local_publish_dependency_reuse.py`
- Date/Time: 2026-04-16 Asia/Hebron
- Result: Not run after the publish-runtime hard cut in this change set.

## Known Gaps / Follow-Ups
- Remove this folder entirely if no other draft-dev local-runtime dependency tests are added here.
