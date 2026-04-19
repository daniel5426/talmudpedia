# Settings Projects Test State

Last Updated: 2026-04-19

## Scope
Projects service contract for the new settings-managed project surface.

## Test Files
- `settings_projects_service.test.ts`

## Key Scenarios Covered
- Lists projects.
- Loads a project detail.
- Loads project members.
- Updates a project.

## Last Run
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/settings_shell/settings_shell.test.tsx src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/settings_profile/settings_profile_service.test.ts src/__tests__/settings_projects/settings_projects_service.test.ts src/__tests__/settings_limits/settings_limits_service.test.ts src/__tests__/settings_audit/settings_audit_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts --watch=false`
- Date: 2026-04-19
- Result: Pass

## Known Gaps
- No detail-panel UI interaction coverage yet.
