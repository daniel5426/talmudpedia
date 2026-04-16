# App Versions Test State

Last Updated: 2026-04-16

## Scope
Watcher-owned builder versioning, restore, version preview, and pointer-only publish behavior.

## Test Files
- `backend/tests/app_versions/test_versions_endpoints.py`

## Key Scenarios Covered
- Legacy endpoints return `410` with explicit migration codes.
- `/versions` list and `/versions/{id}` retrieval behavior.
- `/versions/draft` returns `410` with the draft-dev sync migration message.
- Restore flow creates a new draft version with `restored_from_revision_id`.
- Publish-by-version succeeds immediately when the selected revision already has durable dist.
- Publish-by-version rejects non-materialized revisions with `REVISION_NOT_MATERIALIZED`.
- Stale queued/running publish jobs are timed out and no longer block subsequent publish requests.
- Version preview runtime returns `409 VERSION_BUILD_NOT_READY` when dist artifacts are missing.
- Cross-app version access returns `404`.

## Last Run
- Command: `cd backend && PYTHONPATH=. pytest -q tests/app_versions/test_versions_endpoints.py`
- Date: 2026-04-16
- Result: Not run after rewrite in this change set.

## Known Gaps / Follow-ups
- Add deeper assertions for `version_seq` ordering under concurrent version writes.
- Add integration coverage for coding-run finalization against real watcher-ready snapshot promotion.
