# Test State: Agent Builder v3

Last Updated: 2026-03-22

**Scope**
Graph Spec 3.0 frontend serialization defaults, Start/End/Set State contract editor behavior, and graph-analysis hook behavior for the agent builder.

**Test Files**
- `graphspec_v3_serialization.test.ts`
- `graph_contract_editors.test.tsx`
- `use_agent_graph_analysis.test.tsx`

**Scenarios Covered**
- Builder save always persists `spec_version: "3.0"`
- Legacy End nodes hydrate the new schema + binding config when loaded into the builder
- Start editor preserves the built-in workflow input and appends typed state variables
- End editor filters binding options by compatible types and emits structured `ValueRef` bindings
- Set State editor supports typed assignments and `ValueRef` sources
- Graph analysis hook debounces requests and submits normalized v3 graphs

**Last Run**
- Command: `pnpm test -- --runTestsByPath src/__tests__/agent_builder_v3/graphspec_v3_serialization.test.ts src/__tests__/agent_builder_v3/graph_contract_editors.test.tsx src/__tests__/agent_builder_v3/use_agent_graph_analysis.test.tsx --watch=false`
- Date: 2026-03-22
- Result: Pass (3 suites, 6 tests)

**Known Gaps / Follow-ups**
- No full ConfigPanel integration test yet for the backend-driven analysis loop
