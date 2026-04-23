# App Versions Test State

Last Updated: 2026-04-23

## Scope
Watcher-owned builder versioning, first durable `app_init` creation, restore, version preview, and pointer-only publish behavior.

## Test Files
- `backend/tests/app_versions/test_versions_endpoints.py`

## Key Scenarios Covered
- Legacy endpoints return `410` with explicit migration codes.
- `/versions` list and `/versions/{id}` retrieval behavior.
- `/versions/draft` returns `410` with the draft-dev sync migration message.
- Fresh app create no longer seeds a fake provisional `app_init` version; the first durable version is expected only after real builder bootstrap.
- Restore flow creates a new draft version with `restored_from_revision_id`.
- Publish-by-version succeeds immediately when the selected revision already has durable dist.
- Publish-by-version rejects non-materialized revisions with `REVISION_NOT_MATERIALIZED`.
- Stale queued/running publish jobs are timed out and no longer block subsequent publish requests.
- Version preview runtime returns `409 VERSION_BUILD_NOT_READY` when dist artifacts are missing.
- Version preview runtime returns a bootstrap-ready `preview_url` and no separate token field.
- Cross-app version access returns `404`.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/app_versions/test_versions_endpoints.py`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`8 passed`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/published_apps/test_admin_apps_crud.py backend/tests/app_versions/test_versions_endpoints.py`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`12 passed`). Version restore/publish guards still hold after the clean cut to “no draft version on create; first real `app_init` version appears on first builder bootstrap”.

## Known Gaps / Follow-ups
- Add deeper assertions for `version_seq` ordering under concurrent version writes.
- Add integration coverage for coding-run finalization against real watcher-ready snapshot promotion.
