# Test State: Agent Builder v2 (Orchestration + Runtime Overlay)

Last Updated: 2026-03-22

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
- Run-tree reconciliation correcting stream-only divergence and preserving terminal status authority
- Run-tree reconciliation skips rendering the lineage root run as a synthetic runtime child node
- Build mode static-only rendering vs execute mode merged graph rendering
- Orchestration route-table authoring support for router/judge handle derivation
- Save-time orchestration config normalization (idempotency defaults + route/outcome normalization)

**Last Run**
- Command: `pnpm test -- --runTestsByPath src/__tests__/agent_builder_v2/graphspec_v2_serialization.test.ts --watch=false`
- Date: 2026-03-22
- Result: Pass (1 suite, 5 tests)

**Known Gaps / Follow-ups**
- No full DOM integration test for live polling/reconciliation timing in `useAgentRuntimeGraph`
