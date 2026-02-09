# Agent Builder v2 Frontend Refactor Handoff

Last Updated: 2026-02-09

## 1. Purpose
This handoff is for a fresh-context implementation chat to execute a full frontend refactor for Agent Builder to support GraphSpec v2 orchestration and runtime topology visualization in Execute mode.

This file is intentionally decision-complete so the implementer does not need to re-research core facts.

## 2. Product Goals
1. Opening the seeded Platform Architect in Builder must render all nodes correctly (no blank rectangles).
2. Orchestration branch edges must visibly connect to real handles.
3. Saving v2 graphs must never downgrade `spec_version`.
4. Execute mode must show runtime-created nodes/edges in real time as decisions happen.
5. Runtime topology must reconcile with backend run tree for correctness.
6. Runtime topology is ephemeral per run (never persisted into draft graph_definition).

## 3. Locked Decisions
These are already approved and should be treated as fixed requirements:

1. Rollout scope now: **Builder Execute mode** (not full Playground parity in this phase).
2. Runtime data source: **SSE stream + `/agents/runs/{run_id}/tree` reconciliation**.
3. Persistence policy: **ephemeral runtime topology only**.
4. Runtime graph granularity: **child runs + orchestration decisions**.
5. Tool-level spans remain in trace panels, not graph nodes.

## 4. Research Findings (Verified Facts)
Use these as implementation truth; do not re-investigate unless behavior has changed.

### 4.1 Backend already supports GraphSpec v2 orchestration
- Platform Architect seed uses GraphSpec v2 and orchestration node types:
  - `spawn_run`, `spawn_group`, `join`, `judge`, `replan`, `router`, `cancel_subtree`
- Seed graph includes orchestration branch handles (`completed`, `failed`, `replan`, etc.).

Source:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/registry_seeding.py:502`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/registry_seeding.py:659`

### 4.2 Backend operator catalog already includes orchestration operators
- `/agents/operators` includes nodes with `category="orchestration"`.

Source:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/executors/standard.py:1386`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/agents.py:170`

### 4.3 Frontend static builder is behind backend surface
- Node type renderer map omits orchestration node types, causing default renderer fallback.
- Frontend categories do not include `orchestration`, and catalog group map only includes six legacy categories.

Source:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/nodes/index.ts:5`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/types.ts:4`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/NodeCatalog.tsx:206`

### 4.4 Frontend save path can break v2
- Save normalization hardcodes `spec_version: "1.0"`.
- Backend compiler requires `spec_version='2.0'` when v2 orchestration nodes exist.

Source:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/graphspec.ts:63`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/graph/compiler.py:269`

### 4.5 Runtime events needed for dynamic topology already exist
- Backend emits orchestration events:
  - `orchestration.spawn_decision`
  - `orchestration.child_lifecycle`
  - `orchestration.join_decision`
  - `orchestration.policy_deny`
  - `orchestration.cancellation_propagation`
- Run tree endpoint already exists.

Source:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/execution/emitter.py:142`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/agents.py:721`

### 4.6 Current builder execution hook does not consume orchestration events
- `useAgentRunController` handles token/node/tool events but not orchestration events.

Source:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/hooks/useAgentRunController.ts:413`

## 5. Architecture & Data Flow (Target)

### 5.1 Static graph layer (persisted)
- Source: agent `graph_definition` from `/agents/{id}`.
- Editable in Build mode.
- Includes GraphSpec v1 + v2 nodes.
- Saved back to `graph_definition`.

### 5.2 Runtime overlay layer (ephemeral)
- Source: stream events and run-tree reconciliation.
- Rendered only in Execute mode.
- Non-editable, non-persisted.
- Reset on new run or explicit clear.

### 5.3 Merge strategy (render-time)
- Execute mode renders `mergedGraph = staticGraph + runtimeOverlay`.
- Build mode renders static graph only.
- Runtime elements are visually distinct and excluded from save payload.

### 5.4 Authority model
- Real-time updates: SSE events.
- Correctness/stability: periodic/final `/runs/{run_id}/tree`.
- If discrepancy occurs, run-tree wins for lineage/status.

## 6. File-by-File Implementation Plan

## 6.1 Static v2 support in Agent Builder
1. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/types.ts`.
- Add `orchestration` to `AgentNodeCategory`.
- Add orchestration types to `AgentNodeType` union:
  - `spawn_run`, `spawn_group`, `join`, `router`, `judge`, `replan`, `cancel_subtree`
- Add static specs to `AGENT_NODE_SPECS` for fallback.
- Extend `CATEGORY_COLORS` / `CATEGORY_LABELS` for orchestration.
- Extend `getNodeOutputHandles` for:
  - `join` => `completed`, `completed_with_errors`, `failed`, `timed_out`, `pending`
  - `replan` => `replan`, `continue`
  - `judge` => from outcomes or fallback `pass`, `fail`
  - `router` => config routes + `default`

2. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/nodes/index.ts`.
- Register all orchestration node types to `BaseNode`.

3. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/nodes/BaseNode.tsx`.
- Add icon mappings for orchestration types.
- Add specialized branch-row rendering for `join`, `router`, `judge`, `replan` using config handles.
- Keep existing behavior for legacy nodes.

4. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/NodeCatalog.tsx`.
- Include orchestration category in grouped buckets and category render order.
- Ensure operators with `category="orchestration"` are not dropped.

5. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/ConfigPanel.tsx`.
- Add orchestration icon/category mapping support.
- Keep dynamic operator-driven config field behavior from `listOperators()`.

## 6.2 Save/version hardening
1. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/graphspec.ts`.
- Add version-aware save normalization API.
- Remove hardcoded return of `"1.0"`.
- Version rule:
  - Preserve incoming `spec_version` if present.
  - If any node type in v2 orchestration set, force `"2.0"`.
  - Else default to existing or `"1.0"`.

2. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/agents/[id]/builder/page.tsx`.
- Track loaded `spec_version` in graph ref.
- Pass version into normalization on save.
- Replace local page-specific graph interface with shared service type.

## 6.3 Shared service typing and API usage
1. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/agent.ts`.
- Add/extend types for:
  - `Agent.graph_definition`
  - run-tree response payload
  - orchestration SSE events
- Add:
  - `getRunTree(runId: string)`
  - `getRunStatus(runId: string, includeTree?: boolean)`

2. Keep all new API/types in `src/services/` per frontend layering rule.

## 6.4 Runtime overlay implementation
1. Create `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/agent-runtime-graph.ts`.
- Pure functions and types:
  - runtime node model
  - runtime edge model
  - event-to-patch reducers
  - reconciliation reducers
- Deterministic IDs to avoid collisions:
  - `runtime-run:<run_id>`
  - `runtime-group:<group_id>`
  - `runtime-event:<run_id>:<event>:<seq>`

2. Create `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/hooks/useAgentRuntimeGraph.ts`.
- Inputs:
  - static nodes/edges
  - run id
  - typed execution events
  - run status
- Outputs:
  - runtime nodes/edges
  - taken static edge ids
  - runtime status map
  - loading/error for tree reconcile

3. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/hooks/useAgentRunController.ts`.
- Preserve current chat and `executionSteps` behavior.
- Add `executionEvents` stream state.
- Parse orchestration events and append to `executionEvents`.

4. Update `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/components/agent-builder/AgentBuilder.tsx`.
- Execute mode:
  - instantiate runtime overlay hook
  - merge static + runtime graph for render
  - keep runtime nodes non-draggable, non-connectable
- Build mode:
  - unchanged static editable graph

## 6.5 Event mapping rules (must implement exactly)
1. `orchestration.spawn_decision`
- Create/update a runtime decision node linked from source static node (`span_id`/node id).
- Create runtime child-run nodes for `spawned_run_ids`.

2. `orchestration.child_lifecycle`
- Update runtime child node status.

3. `orchestration.join_decision`
- Create/update join decision runtime node with counts/status.

4. `orchestration.cancellation_propagation`
- Mark listed runtime child nodes as cancelled.
- Annotate reason.

5. `orchestration.policy_deny`
- Mark originating static node as error/denied in execute view.

6. `node_end` with output routing
- If `event.data.output.next` exists, highlight matching static edge via `source_handle == next`.

7. Unknown or malformed events
- Ignore safely and log development warning.

## 6.6 Run-tree reconciliation behavior
1. Poll `getRunTree(runId)` every 2 seconds while run status is running/paused.
2. Force final reconcile on terminal run status.
3. Tree is authoritative for lineage/status.
4. SSE can enrich labels/details but must not overwrite authoritative terminal status from tree.
5. On tree fetch failure:
- keep stream-only rendering
- retry next poll
- do not break chat/token stream.

## 7. UX Rules
1. Runtime nodes/edges must be visually distinct from static graph.
2. Runtime overlay never enters save payload.
3. Runtime overlay reset on:
- new chat/run
- switching agent
- explicit clear action in execute mode
4. Build mode must not show runtime artifacts.

## 8. Test Plan

## 8.1 New frontend feature test directory (required)
Create:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/agent_builder_v2/`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/agent_builder_v2/test_state.md`

## 8.2 Required tests
1. `graphspec_v2_serialization.test.ts`
- preserve loaded v2 version
- auto-set v2 when v2 nodes exist
- never downgrade v2 to v1

2. `orchestration_node_rendering.test.tsx`
- v2 nodes use custom renderer
- branch handles render for join/router/judge/replan

3. `runtime_overlay_reducer.test.ts`
- spawn/lifecycle/join/cancel/policy events mutate overlay correctly

4. `run_tree_reconcile.test.ts`
- tree snapshot corrects stream-only overlay divergence

5. `execute_mode_merge_graph.test.tsx`
- execute mode merged graph
- build mode static-only

## 8.3 Existing test-state update
Update:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/agent_builder/test_state.md`
- new `agent_builder_v2/test_state.md` with latest command/date/result/gaps

## 8.4 Suggested validation commands
1. `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet`
2. `npm test -- agent_builder_v2`
3. `npm test -- agent_builder`
4. `npm run lint`

## 9. Documentation & Architecture Update Requirements
1. Update architecture tree for new file additions/deletions:
- `/Users/danielbenassaya/Code/personal/talmudpedia/code_architect/architecture_tree.md`
2. Update relevant summary docs with `Last Updated`:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/summary/agent_builder_runtime_adapter_summary.md`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/platform_current_state.md` (if behavior descriptions are updated)

## 10. Known Contradiction to Resolve
There is a docs contradiction:
1. `agent_builder_runtime_adapter_summary.md` frames GraphSpec v1 as canonical baseline.
2. `platform_current_state.md` and seeding/runtime code clearly include GraphSpec v2 orchestration surface.

When implementation is done, update docs to reflect coexistence: v1 baseline + v2 orchestration extension.

## 11. Step-by-Step Execution Checklist (for fresh chat)
1. Implement static v2 node/category/handle support.
2. Implement save/version guardrails for v2.
3. Add shared service types + run-tree API methods.
4. Add execution event capture for orchestration in run controller.
5. Build runtime overlay reducer + hook.
6. Integrate merged execute-mode graph rendering.
7. Implement run-tree polling/reconciliation.
8. Add tests + `test_state.md` updates.
9. Run tests/lint and capture exact results.
10. Update docs and architecture tree.

## 12. Fresh Context Prompt (copy/paste)
Read this file first:
`/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/summary/agent_builder_v2_frontend_refactor_handoff.md`

Then execute in this strict order:
1. Static GraphSpec v2 support in Agent Builder rendering/catalog/config.
2. Save pipeline spec_version hardening (no v2 downgrade).
3. Runtime overlay graph in Builder Execute mode driven by SSE orchestration events.
4. Run-tree reconciliation via `/agents/runs/{run_id}/tree`.
5. Frontend tests in `src/__tests__/agent_builder_v2/` + `test_state.md` updates.
6. Docs and architecture tree updates.

Guardrails:
1. Do not create page-local `types.ts` or `api.ts`.
2. Keep shared API/types in `src/services/`.
3. Do not persist runtime overlay nodes/edges to `graph_definition`.
4. Preserve legacy v1 build-mode UX behavior.
