# Settings Shell Test State

Last Updated: 2026-04-19

## Scope
Canonical `/admin/settings` shell tab routing and high-level section composition.

## Test Files
- `settings_shell.test.tsx`

## Key Scenarios Covered
- Canonical settings tabs render.
- Active tab restores from the `tab` query parameter.
- Project-to-audit jump seeds the audit view from the projects section.

## Last Run
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/settings_shell/settings_shell.test.tsx src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/settings_profile/settings_profile_service.test.ts src/__tests__/settings_projects/settings_projects_service.test.ts src/__tests__/settings_limits/settings_limits_service.test.ts src/__tests__/settings_audit/settings_audit_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts --watch=false`
- Date: 2026-04-19
- Result: Pass

## Known Gaps
- Does not yet validate every section body in-depth.
