# Settings Hub Backend Tests

Last Updated: 2026-04-20

## Scope
Tenant settings hub backend APIs:
- Tenant profile update (`PATCH /api/tenants/{tenant_slug}`)
- Tenant defaults read/update (`GET/PATCH /api/tenants/{tenant_slug}/settings`)

## Test Files
- `backend/tests/settings_hub/test_tenant_profile_update.py`
- `backend/tests/settings_hub/test_tenant_defaults_settings.py`

## Key Scenarios Covered
- Owner can update tenant profile fields.
- Member cannot update tenant profile fields.
- Tenant slug uniqueness is enforced.
- Tenant settings GET returns normalized values.
- Tenant settings PATCH accepts valid default model pointers.
- Tenant settings PATCH rejects capability mismatches and unknown models.
- Tenant settings PATCH only accepts active model rows as defaults.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/settings_hub/test_tenant_profile_update.py backend/tests/settings_hub/test_tenant_defaults_settings.py`
- Date: 2026-04-20
- Result: Not run after latest slug-isolation edits

## Known Gaps / Follow-ups
- Add integration test for global admin editing another tenant.
- Add endpoint tests for clearing defaults explicitly via `null` per field.
- `.env.test` still points tests at `talmudpedia_dev`; that environment-safety cleanup is still separate.
