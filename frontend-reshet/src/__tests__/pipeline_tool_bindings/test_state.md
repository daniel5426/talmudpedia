# Pipeline Tool Bindings Test State

Last Updated: 2026-03-19

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
