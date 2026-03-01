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
- Publish-by-version auto-builds missing dist artifacts on the selected version before pointer publish.
- Version preview runtime endpoint returns a revision-scoped tokenized runtime URL.
- Cross-app version access returns `404`.
- Coding-run finalizer still enforces diff-only version creation.

## Last Run
- Command: `cd backend && pytest -q tests/app_versions/test_versions_endpoints.py tests/app_versions/test_coding_run_versions.py`
- Date: 2026-03-01
- Result: Pass (8 passed)

## Known Gaps / Follow-ups
- Add deeper assertions for `version_seq` ordering under concurrent version writes.
- Add integration test for coding-run finalizer against real sandbox snapshot/promote flow.
