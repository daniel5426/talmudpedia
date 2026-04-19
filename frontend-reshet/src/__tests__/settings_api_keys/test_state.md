# Settings API Keys Test State

Last Updated: 2026-04-19

## Scope
Scoped settings API key service wiring for organization and project ownership.

## Test Files
- `settings_api_keys_service.test.ts`

## Key Scenarios Covered
- Lists organization API keys.
- Creates project API keys.
- Revokes and deletes scoped API keys.

## Last Run
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/settings_shell/settings_shell.test.tsx src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/settings_profile/settings_profile_service.test.ts src/__tests__/settings_projects/settings_projects_service.test.ts src/__tests__/settings_limits/settings_limits_service.test.ts src/__tests__/settings_audit/settings_audit_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts --watch=false`
- Date: 2026-04-19
- Result: Pass

## Known Gaps
- No UI-level API key dialog coverage yet.
