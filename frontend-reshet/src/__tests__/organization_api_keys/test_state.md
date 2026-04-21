# Organization API Keys Test State

Last Updated: 2026-04-21

## Scope
Validate frontend organization API keys service API wiring for embedded agent runtime admin.

## Test Files
- organization_api_keys_service.test.ts

## Key Scenarios Covered
- List API keys endpoint wiring (GET /admin/organizations/api-keys)
- Create API key with default scopes
- Create API key with custom scopes
- Revoke API key endpoint wiring (POST /admin/organizations/api-keys/{key_id}/revoke)
- Error propagation from httpClient

## Last Run
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/organization_api_keys/organization_api_keys_service.test.ts`
- Date/Time: 2026-04-21
- Result: pass (5/5)

## Known Gaps
- Does not validate API keys tab rendering (UI-level test).
- Does not validate create/revoke dialog interactions.

## 2026-04-21 tenant-to-organization validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/organization_api_keys/organization_api_keys_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/admin_threads/threads_table.test.ts src/__tests__/admin_threads/admin_thread_page.test.tsx src/__tests__/admin_monitoring/users_table_monitoring.test.tsx src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx`
- Result: PASS (`12 suites passed, 30 tests passed`)
