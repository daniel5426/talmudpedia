# Settings Hub Frontend Tests

Last Updated: 2026-04-12

## Scope
Settings Hub UI behavior for:
- Settings navigation information architecture
- Tenant profile save/read-only behavior
- Defaults save payload wiring

## Test Files
- `frontend-reshet/src/__tests__/settings_hub/settings_hub.test.tsx`
- `frontend-reshet/src/__tests__/settings_hub/tenant_profile_tab.test.tsx`
- `frontend-reshet/src/__tests__/settings_hub/defaults_tab.test.tsx`

## Key Scenarios Covered
- Settings hub renders the four primary sections.
- Settings hub restores the active section from the `tab` query string.
- Tenant profile save calls update API with edited fields.
- Non-admin/member role renders profile controls as read-only.
- Defaults tab submits the expected payload shape.
- Settings tab changes update the `tab` query string for reload persistence.

## Last Run
- Command: `npm test -- --runInBand src/__tests__/settings_hub`
- Date: 2026-04-12 23:17:02 EEST
- Result: Pass (3 suites, 6 tests)

## Known Gaps / Follow-ups
- Add tests for slug-change tenant context refresh flow.
- Add integrations-tab tests for credential 409 delete conflict message.
