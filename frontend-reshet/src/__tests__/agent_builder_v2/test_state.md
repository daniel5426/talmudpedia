# Test State: Agent Builder v2 (Orchestration + Runtime Overlay)

Last Updated: 2026-04-01

**Scope**
Orchestration node rendering, Graph Spec 3.0 save guardrails, execute-mode runtime overlay reduction, and run-tree reconciliation behavior.

**Test Files**
- `graphspec_v2_serialization.test.ts`
- `orchestration_node_rendering.test.tsx`
- `runtime_overlay_reducer.test.ts`
- `run_tree_reconcile.test.ts`
- `execute_mode_merge_graph.test.tsx`

**Scenarios Covered**
- GraphSpec save persists `spec_version: "3.0"` for orchestration and non-orchestration graphs
- Graph save writes canonical top-level `node.config` for orchestration nodes and does not persist `data.config`
- Orchestration node renderer registration and branch-handle rendering for `join`/`router`/`judge`/`replan`
- Runtime overlay reducers for spawn/lifecycle/join/cancel/policy events
- Runtime overlay reducers mark the taken branch from `branch_taken` as well as `next`
- Runtime overlay reducers clear stuck `running` node overlays when a run fails mid-graph
- Execute-mode graph merging clears stale static node status and colors runtime edges with the same active success styling as taken static edges
- Run-tree reconciliation correcting stream-only divergence and preserving terminal status authority
- Run-tree reconciliation skips rendering the lineage root run as a synthetic runtime child node
- Build mode static-only rendering vs execute mode merged graph rendering
- Orchestration route-table authoring support for router/judge handle derivation
- Save-time orchestration config normalization (idempotency defaults + route/outcome normalization)

**Last Run**
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v2/runtime_overlay_reducer.test.ts src/__tests__/agent_playground/trace_steps.test.ts --watch=false`
- Date: 2026-04-01 00:24 EEST
- Result: Pass (2 suites, 8 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v2/runtime_overlay_reducer.test.ts src/__tests__/agent_playground/useAgentRunController.test.tsx --watch=false`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (2 suites, 9 tests)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agent_builder_v2/runtime_overlay_reducer.test.ts src/__tests__/agent_builder_v2/execute_mode_merge_graph.test.tsx --watch=false`
- Date: 2026-03-31
- Result: Pass (2 suites, 5 tests)

**Known Gaps / Follow-ups**
- No full DOM integration test for live polling/reconciliation timing in `useAgentRuntimeGraph`
