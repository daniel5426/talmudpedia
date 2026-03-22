# Test State: Agent Builder v3

Last Updated: 2026-03-22

**Scope**
Graph Spec 3.0 frontend serialization defaults, Start/End/Set State contract editor behavior, graph-analysis hook behavior, and ConfigPanel contract-driven ValueRef filtering for the agent builder.

**Test Files**
- `graphspec_v3_serialization.test.ts`
- `graph_contract_editors.test.tsx`
- `use_agent_graph_analysis.test.tsx`
- `config_panel_value_ref_contracts.test.tsx`
- `config_panel_artifact_contracts.test.tsx`

**Scenarios Covered**
- Builder save always persists `spec_version: "3.0"`
- Legacy End nodes hydrate the new schema + binding config when loaded into the builder
- Saved Graph Spec 3.0 Start/Classify/Set State/End contract nodes roundtrip through save + rehydrate without serialization drift
- Start editor preserves the built-in workflow input and appends typed state variables
- End editor filters binding options by compatible types and emits structured `ValueRef` bindings through the new searchable picker UI
- Set State editor supports typed assignments and `ValueRef` sources
- Graph analysis hook debounces requests and submits normalized v3 graphs
- ConfigPanel filters `value_ref` options using backend operator field contracts in the specialized Classify surface
- ConfigPanel opens End structured output in a modal from the output row
- ConfigPanel renders artifact field-mapping inputs from backend-provided artifact operator contracts

**Last Run**
- Command: `pnpm test -- --runTestsByPath src/__tests__/agent_builder_v3/graphspec_v3_serialization.test.ts src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx --watch=false`
- Date: 2026-03-22
- Result: Pass (4 suites, 10 tests)

**Known Gaps / Follow-ups**
- No full builder-session test yet that edits nodes through the canvas, saves, reloads, and re-fetches live analysis end-to-end
