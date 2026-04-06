# Test State: Agent Builder (GraphSpec Serialization + Branch Handles)

Last Updated: 2026-04-05

**Scope**
Frontend GraphSpec serialization, builder node normalization, and branch handle rendering.

**Test Files**
- `graphspec_serialization.test.tsx`
- `branch_handles.test.tsx`
- `canvas_centering.test.ts`
- `header_config_editor_copy_id.test.tsx`
- `agent_builder_page_errors.test.tsx`

**Scenarios Covered**
- GraphSpec save writes canonical top-level `node.config` and strips persisted `data.config`
- Serialization of handle fields into GraphSpec
- Artifact input mappings normalization and preservation
- Classify and if/else branch handle IDs (fallbacks, dedupe, else handle)
- Stable classify branch ids render as handles even when labels change
- Canvas centering offsets for build mode with/without catalog and execute mode with right panel
- Builder details/config panel renders the agent ID and copies it to the clipboard
- Builder page surfaces structured backend save errors instead of generic failure text

**Last Run**
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder/canvas_centering.test.ts --watch=false`
- Date: 2026-04-05
- Result: Pass (1 suite, 3 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder/branch_handles.test.tsx --watch=false`
- Date: 2026-03-31
- Result: Pass (1 suite, 3 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder/agent_builder_page_errors.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx --watch=false`
- Date: 2026-04-01
- Result: Pass (2 suites, 2 tests)

**Known Gaps / Follow-ups**
- No end-to-end builder save/publish UI test
- GraphSpec v2 + runtime overlay coverage now lives in `../agent_builder_v2/`
