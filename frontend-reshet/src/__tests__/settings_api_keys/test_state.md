# Settings API Keys Test State

Last Updated: 2026-04-21

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

## 2026-04-21 validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/settings_api_keys/settings_api_keys_service.test.ts`
- Result: `1 suite passed`

## 2026-04-21 tenant-to-organization validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/admin_threads/threads_table.test.ts src/__tests__/admin_threads/admin_thread_page.test.tsx src/__tests__/admin_monitoring/users_table_monitoring.test.tsx src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx`
- Result: PASS (`11 suites passed, 25 tests passed`)
