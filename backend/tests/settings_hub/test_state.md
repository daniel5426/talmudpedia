# Settings Hub Backend Tests

Last Updated: 2026-02-09

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

## Last Run
- Command: `pytest backend/tests/settings_hub`
- Date: 2026-02-09 17:56 EET
- Result: Pass (7 passed)

## Known Gaps / Follow-ups
- Add integration test for global admin editing another tenant.
- Add endpoint tests for clearing defaults explicitly via `null` per field.
