# Pipeline Tool Bindings Test State

Last Updated: 2026-04-21

## Scope
Frontend pipeline editor behavior for pipeline-owned tool settings.

## Test files present
- `pipeline_tool_settings_page.test.tsx`

## Key scenarios covered
- The pipeline editor loads existing pipeline-owned tool binding settings from the backend.
- The tool-settings panel shows the model-facing tool name, description, input schema, and bound tool id.
- Saving the tool-settings panel submits `tool_name`, `description`, and `input_schema` through the pipeline tool-binding API.

## Last run command + date/time + result
- Command: `npm test -- --runInBand src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx`
- Date/Time: 2026-03-19 14:45 EET
- Result: pass (`1 suite, 1 test`)

## Known gaps or follow-ups
- Add coverage for the enable/disable checkbox path.
- Add coverage for invalid JSON error handling in the tool input schema editor.

## 2026-04-21 validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts`
- Result: PASS (`7 suites passed, 14 tests passed`)
