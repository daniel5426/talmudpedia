# Test State: Agent Builder v3

Last Updated: 2026-04-22

**Scope**
Graph Spec 4.0 frontend serialization defaults, Start-as-projection contract editing, canonical workflow modality toggles, graph-analysis hook behavior, scoped ValueRef picker behavior, and ConfigPanel contract-driven filtering for the agent builder.

**Test Files**
- `graphspec_v3_serialization.test.ts`
- `graph_contract_editors.test.tsx`
- `use_agent_graph_analysis.test.tsx`
- `template_suggestions.test.tsx`
- `config_panel_value_ref_contracts.test.tsx`
- `config_panel_artifact_contracts.test.tsx`
- `node_types_registry.test.ts`
- `state_variable_modal.test.tsx`
- `graph_authoring_defaults.test.ts`

**Scenarios Covered**
- Builder save always persists `spec_version: "4.0"` plus top-level `workflow_contract` and `state_contract`
- Branching node configs normalize to opaque `branch_*` ids during graph hydration/save
- Legacy End nodes hydrate the new schema + binding config when loaded into the builder
- Saved Graph Spec 4.0 contract nodes roundtrip through save + rehydrate without serialization drift
- Legacy Start-owned state normalizes into top-level `state_contract`
- Start editor reads workflow/state contract data from the graph-level contract projection
- Start editor renders the 4 canonical workflow modalities (`text`, `files`, `audio`, `images`) with toggles instead of legacy helper inputs
- End editor filters binding options by compatible types and emits structured `ValueRef` bindings through the new searchable picker UI
- End and generic ValueRef pickers use node-scoped upstream output inventory instead of global node outputs
- Set State editor supports typed assignments and `ValueRef` sources
- Graph analysis hook debounces requests and submits normalized v4 graphs
- Builder prompt/template suggestions use scoped graph-analysis inventory, show friendly labels, and insert one stable token per value
- Prompt mention/template inputs insert `@path` variable aliases instead of legacy `{{ ... }}` tokens
- ConfigPanel filters `value_ref` options using backend operator field contracts in the specialized Classify surface
- ConfigPanel opens End structured output in a modal from the output row
- ConfigPanel persists the selected End property binding when saving the structured-output modal
- Start editor blocks disabling a workflow input when live bindings still reference it and shows the consumer list
- Start state-variable modal uses typed default-value controls for booleans and lists instead of a generic JSON textarea
- Start state-variable modal blocks duplicate state-variable keys before save and shows an inline validation error
- ConfigPanel renders artifact field-mapping inputs from backend-provided artifact operator contracts
- The frontend node registry is derived from the canonical built-in node specs, so renderer coverage cannot drift for built-in nodes like `speech_to_text`
- ConfigPanel resource loaders now consume canonical control-plane list envelopes for models, tools, pipelines, and agents.
- Schema-default mirroring now supports nested object defaults without inventing fields that the backend does not own.

**Last Run**
- Command: `pnpm exec jest src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx --runInBand`
- Date: 2026-04-14 23:18 EEST
- Result: Pass (2 suites, 3 tests)
- Command: `cd frontend-reshet && ./node_modules/.bin/jest --runInBand src/__tests__/agent_builder_v3/graph_authoring_defaults.test.ts src/__tests__/agent_builder_v3/graphspec_v3_serialization.test.ts`
- Date: 2026-04-22 Asia/Hebron
- Result: Pass (2 suites, 6 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/graphspec_v3_serialization.test.ts --watch=false`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (1 suite, 5 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/use_agent_graph_analysis.test.tsx src/__tests__/agent_builder_v3/graphspec_v3_serialization.test.ts src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx src/__tests__/agent_builder_v3/node_types_registry.test.ts src/__tests__/agent_builder_v3/template_suggestions.test.tsx --watch=false`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (6 suites, 16 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/graphspec_v3_serialization.test.ts src/__tests__/agent_builder_v3/use_agent_graph_analysis.test.tsx src/__tests__/agent_builder_v3/template_suggestions.test.tsx src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx src/__tests__/agent_playground/useAgentRunController.test.tsx --watch=false`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (6 suites, 20 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/state_variable_modal.test.tsx --watch=false`
- Date: 2026-03-31 13:07:06 EEST
- Result: Pass (3 suites, 10 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/state_variable_modal.test.tsx --watch=false`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (1 suite, 4 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx --watch=false`
- Date: 2026-04-01 09:54:48 EEST
- Result: Pass (2 suites, 10 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/template_suggestions.test.tsx src/__tests__/agent_builder_v3/state_variable_modal.test.tsx --watch=false`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (2 suites, 6 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v3/node_types_registry.test.ts --watch=false`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (1 suite, 1 test)
- Command: `pnpm test -- --runTestsByPath src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/use_agent_graph_analysis.test.tsx src/__tests__/agent_builder_v3/template_suggestions.test.tsx --watch=false`
- Date: 2026-03-29 Asia/Hebron
- Result: Pass (4 suites, 13 tests)
- Command: `pnpm test -- --runTestsByPath src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx --watch=false`
- Date: 2026-03-29 02:16 EEST
- Result: Pass (2 suites, 7 tests)

**Known Gaps / Follow-ups**
- No full builder-session test yet that edits nodes through the canvas, saves, reloads, and re-fetches live analysis end-to-end

**2026-04-21 validation**
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts`
- Result: PASS (`7 suites passed, 14 tests passed`)
