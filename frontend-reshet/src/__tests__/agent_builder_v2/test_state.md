# Test State: Agent Builder v2 (Orchestration + Runtime Overlay)

Last Updated: 2026-02-09

**Scope**
GraphSpec v2 frontend compatibility for orchestration node rendering, save-version guardrails, execute-mode runtime overlay reduction, and run-tree reconciliation behavior.

**Test Files**
- `graphspec_v2_serialization.test.ts`
- `orchestration_node_rendering.test.tsx`
- `runtime_overlay_reducer.test.ts`
- `run_tree_reconcile.test.ts`
- `execute_mode_merge_graph.test.tsx`

**Scenarios Covered**
- GraphSpec save keeps/forces `spec_version` correctly for v1/v2 graphs
- Orchestration node renderer registration and branch-handle rendering for `join`/`router`/`judge`/`replan`
- Runtime overlay reducers for spawn/lifecycle/join/cancel/policy events
- Run-tree reconciliation correcting stream-only divergence and preserving terminal status authority
- Build mode static-only rendering vs execute mode merged graph rendering

**Last Run**
- Command: `npm test -- agent_builder_v2`
- Date: 2026-02-09 18:42 EET
- Result: Pass (5 suites, 9 tests)

**Known Gaps / Follow-ups**
- No full DOM integration test for live polling/reconciliation timing in `useAgentRuntimeGraph`
