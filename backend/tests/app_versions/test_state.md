# App Versions Test State

Last Updated: 2026-03-01

## Scope
Hard-cut versions-first API behavior for builder versioning, restore, and publish-by-version.

## Test Files
- `backend/tests/app_versions/test_versions_endpoints.py`
- `backend/tests/app_versions/test_coding_run_versions.py`

## Key Scenarios Covered
- Legacy endpoints return `410` with explicit migration codes.
- `/versions` list and `/versions/{id}` retrieval behavior.
- Draft version creation via `/versions/draft`.
- Restore flow creates a new draft version with `restored_from_revision_id`.
- Restore falls back to inline version files when manifest blob materialization fails.
- Restore returns `409 VERSION_SOURCE_UNAVAILABLE` when version source is unrecoverable.
- Publish-by-version uses selected `version_id` as `source_revision_id` and updates published pointer without creating extra version rows.
- Manual save (`/versions/draft`) enqueues revision build, while restore does not auto-enqueue.
- Publish-by-version with missing dist returns queued publish job and waits for build completion via worker flow.
- Publish-by-version fails safely when selected revision build fails and keeps previous published pointer unchanged.
- Publish failure diagnostics include publish-wait build state and auto-fix submission metadata.
- Version preview runtime returns `409 VERSION_BUILD_NOT_READY` when dist artifacts are missing.
- Cross-app version access returns `404`.
- Coding-run finalizer still enforces diff-only version creation.

## Last Run
- Command: `cd backend && pytest tests/app_versions/test_versions_endpoints.py`
- Date: 2026-03-01
- Result: Pass (9 passed)

## Known Gaps / Follow-ups
- Add deeper assertions for `version_seq` ordering under concurrent version writes.
- Add integration test for coding-run finalizer against real sandbox snapshot/promote flow.
