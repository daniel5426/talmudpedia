# Settings Hub Frontend Tests

Last Updated: 2026-02-09

## Scope
Settings Hub UI behavior for:
- Tabbed information architecture
- Tenant profile save/read-only behavior
- Defaults save payload wiring

## Test Files
- `frontend-reshet/src/__tests__/settings_hub/settings_hub.test.tsx`
- `frontend-reshet/src/__tests__/settings_hub/tenant_profile_tab.test.tsx`
- `frontend-reshet/src/__tests__/settings_hub/defaults_tab.test.tsx`

## Key Scenarios Covered
- Settings hub renders the four primary tabs.
- Tenant profile save calls update API with edited fields.
- Non-admin/member role renders profile controls as read-only.
- Defaults tab submits the expected payload shape.

## Last Run
- Command: `npm test -- --runInBand src/__tests__/settings_hub`
- Date: 2026-02-09 18:08 EET
- Result: Pass (3 suites, 4 tests)

## Known Gaps / Follow-ups
- Add tests for slug-change tenant context refresh flow.
- Add integrations-tab tests for credential 409 delete conflict message.
