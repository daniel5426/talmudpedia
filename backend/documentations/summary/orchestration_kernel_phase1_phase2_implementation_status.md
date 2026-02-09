# Orchestration Kernel Phase 1-2 Implementation Status (Historical Snapshot)

Last Updated: 2026-02-08

> Note: This file describes the Phase 1-2 checkpoint only.  
> Current multi-phase status (including Phases 3-7) is tracked in:
> `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/summary/multi_agent_orchestration_v2_phase1_phase2_handoff_prompt.md`.

## Scope Implemented
- Added a kernel-backed orchestration runtime path for primitive operations:
  - `spawn_run`
  - `spawn_group`
  - `join`
  - `cancel_subtree`
  - `evaluate_and_replan`
  - `query_tree`
- Added internal orchestration API router under `/internal/orchestration/*`.
- Wired Platform SDK runtime primitive actions to the internal orchestration API.

## Data Model and Persistence
- Extended `agent_runs` with run-tree lineage and idempotency fields:
  - `root_run_id`, `parent_run_id`, `parent_node_id`, `depth`, `spawn_key`, `orchestration_group_id`
- Added orchestration tables:
  - `orchestrator_policies`
  - `orchestrator_target_allowlists`
  - `orchestration_groups`
  - `orchestration_group_members`
- Added migration: `e6f1a9b4c2d0_add_orchestration_kernel_tables_and_lineage.py`.

## Policy and Security Semantics Implemented
- Default enforcement via policy service:
  - published-only target eligibility
  - orchestrator allowlist enforcement
  - limit ceilings (`max_depth`, `max_fanout`, `max_children_total`)
  - scope subset enforcement against caller grant + orchestrator policy
- Child runs use delegated scoped tokens minted through existing grant/token broker services.

## Runtime Integration
- Execution context now propagates lineage metadata into runtime config/context:
  - `root_run_id`, `parent_run_id`, `parent_node_id`, `depth`, `spawn_key`, `orchestration_group_id`

## Tests Added
- `backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py`
- `backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`

## Remaining Work Against Master Plan
- GraphSpec v2 native orchestration nodes (schema/IR/compiler/executors) are not implemented yet.
- Advanced deterministic join/cancel semantics and richer orchestration event telemetry are partial.
- Capability-manifest grant model is represented through existing workload policy/grant primitives, not a dedicated new grant table.
