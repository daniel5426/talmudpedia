# App Versions Test State

Last Updated: 2026-03-15

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
- Stale queued/running publish jobs are timed out and no longer block subsequent publish requests.
- Publish failure diagnostics include publish-wait build state and auto-fix submission metadata.
- Version preview runtime returns `409 VERSION_BUILD_NOT_READY` when dist artifacts are missing.
- Cross-app version access returns `404`.
- Coding-run finalizer still enforces diff-only version creation.

## Last Run
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/app_versions/test_versions_endpoints.py`
- Date: 2026-03-15
- Result: FAIL (`test_versions_list_get_create_restore_and_cross_app_guard` receives `410` from `/versions/draft` where the test expects `200`)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_batch_finalizer.py tests/app_versions/test_coding_run_versions.py`
- Date: 2026-03-15
- Result: FAIL during collection (`ModuleNotFoundError: app.services.published_app_coding_batch_finalizer`)
- Command: `cd backend && pytest tests/app_versions/test_versions_endpoints.py`
- Date: 2026-03-07
- Result: Partial pass (`pytest backend/tests/app_versions/test_versions_endpoints.py -q -k get_active_publish_job_expires_stale_job` -> `1 passed, 9 deselected`)

## Known Gaps / Follow-ups
- Add deeper assertions for `version_seq` ordering under concurrent version writes.
- Add integration test for coding-run finalizer against real sandbox snapshot/promote flow.
