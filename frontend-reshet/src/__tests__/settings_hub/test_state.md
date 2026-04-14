# Settings Hub Frontend Tests

Last Updated: 2026-04-14

## Scope
Settings Hub UI behavior for:
- Settings navigation information architecture
- Organization settings save/read-only behavior
- Defaults save payload wiring

## Test Files
- `frontend-reshet/src/__tests__/settings_hub/settings_hub.test.tsx`
- `frontend-reshet/src/__tests__/settings_hub/tenant_profile_tab.test.tsx`
- `frontend-reshet/src/__tests__/settings_hub/defaults_tab.test.tsx`

## Key Scenarios Covered
- Settings hub renders the four primary sections.
- Settings hub restores the active section from the `tab` query string.
- Tenant profile save calls update API with edited fields.
- Missing `organizations.write` scope renders profile controls as read-only.
- Scope-based settings access uses auth-session `hasScope()` instead of legacy role strings.
- Defaults tab submits the expected payload shape.
- Settings tab changes update the `tab` query string for reload persistence.
- Settings model and credential loaders now consume the canonical control-plane list envelope.

## Last Run
- Command: `pnpm exec jest src/__tests__/settings_hub/settings_hub.test.tsx src/__tests__/settings_hub/tenant_profile_tab.test.tsx --runInBand`
- Date: 2026-04-14 23:18 EEST
- Result: Pass (2 suites, 4 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/settings_hub/settings_hub.test.tsx src/__tests__/settings_hub/tenant_profile_tab.test.tsx src/__tests__/settings_hub/defaults_tab.test.tsx --watch=false`
- Date: 2026-04-14 Asia/Hebron
- Result: Pass (3 suites, 6 tests)
- Command: `npm test -- --runInBand src/__tests__/settings_hub`
- Date: 2026-04-12 23:17:02 EEST
- Result: Pass (3 suites, 6 tests)

## Known Gaps / Follow-ups
- Add tests for slug-change tenant context refresh flow.
- Add integrations-tab tests for credential 409 delete conflict message.
