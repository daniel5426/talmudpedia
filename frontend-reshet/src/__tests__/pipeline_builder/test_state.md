# Pipeline Builder Test State

Last Updated: 2026-04-21

## Scope
- Frontend pipeline-builder save/run feedback around explicit compile materialization.

## Test files present
- `pipeline_run_stale_executable.test.tsx`

## Key scenarios covered
- The editor blocks run when the visual draft is newer than the latest executable.
- The user sees a compile-required message instead of a generic failure.

## Last run command + date/time + result
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx --watch=false`
- Date/Time: 2026-04-01
- Result: pass (`1 suite, 1 test`)

## Known gaps or follow-ups
- Add save-error coverage for illegal write operations returned from the backend.

## 2026-04-21 validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts`
- Result: PASS (`7 suites passed, 14 tests passed`)
