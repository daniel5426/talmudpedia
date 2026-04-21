# Settings Hub Backend Tests

Last Updated: 2026-04-21

## Scope
Organization settings hub backend APIs:
- Organization profile update (`PATCH /api/tenants/{tenant_slug}`)
- Organization defaults read/update (`GET/PATCH /api/tenants/{tenant_slug}/settings`)

## Test Files
- `backend/tests/settings_hub/test_tenant_profile_update.py`
- `backend/tests/settings_hub/test_tenant_defaults_settings.py`

## Key Scenarios Covered
- Owner can update tenant profile fields.
- Member cannot update tenant profile fields.
- Organization settings GET returns normalized values.
- Organization settings PATCH accepts valid default model pointers.
- Organization settings PATCH rejects capability mismatches and unknown models.
- Organization settings PATCH only accepts active model rows as defaults.
- Test fixtures no longer depend on removed legacy org-membership role fields.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/settings_hub`
- Date/Time: 2026-04-21 21:13 EEST
- Result: FAIL (`6 failed`). All requests returned `404` on the current `/api/tenants/...` settings/profile routes.
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/settings_hub/test_tenant_profile_update.py backend/tests/settings_hub/test_tenant_defaults_settings.py`
- Date: 2026-04-20
- Result: Pass (7 passed across the two settings_hub files in the combined settings validation run)

## Known Gaps / Follow-ups
- Add integration test for global admin editing another tenant.
- Add endpoint tests for clearing defaults explicitly via `null` per field.
- `.env.test` still points tests at `talmudpedia_dev`; that environment-safety cleanup is still separate.
