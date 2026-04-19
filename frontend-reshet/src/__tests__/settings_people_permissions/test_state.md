# Settings People & Permissions Test State

Last Updated: 2026-04-19

## Scope
Service contract for members, invitations, groups, roles, and role assignments in the canonical settings surface.

## Test Files
- `settings_people_permissions_service.test.ts`

## Key Scenarios Covered
- Members endpoint wiring.
- Invitation create endpoint wiring.
- Group create endpoint wiring.
- Role update endpoint wiring.
- Role assignment delete endpoint wiring.

## Last Run
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/settings_shell/settings_shell.test.tsx src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/settings_profile/settings_profile_service.test.ts src/__tests__/settings_projects/settings_projects_service.test.ts src/__tests__/settings_limits/settings_limits_service.test.ts src/__tests__/settings_audit/settings_audit_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts --watch=false`
- Date: 2026-04-19
- Result: Pass

## Known Gaps
- No UI interaction test for sub-tab flows yet.
