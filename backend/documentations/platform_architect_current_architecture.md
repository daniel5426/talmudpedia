# Platform Architect Current Architecture

Last Updated: 2026-02-10

## Scope
This document describes the current seeded Platform Architect multi-agent architecture as implemented in backend runtime code.

It covers:
- where and how the architect is seeded
- current orchestrator topology
- sub-agent design
- orchestration kernel and policy layers
- delegated security model
- runtime behavior and eventing
- data model support
- intentional behavior vs current limitations

## High-Level Classification
The seeded Platform Architect is a **GraphSpec v2 staged orchestration agent**.

It is not topology-dynamic at runtime.  
Control-flow is predefined in graph JSON and executed by the agent runtime.

## Seeding and Bootstrapping
At app startup, the lifecycle bootstrap runs:
1. `seed_global_models(db)`
2. `seed_platform_sdk_tool(db)`
3. `seed_platform_architect_agent(db)`

Main entry:
- `backend/main.py`

Seed implementation:
- `backend/app/services/registry_seeding.py`

### Seeded agents
- orchestrator:
  - `platform-architect`
- sub-agents:
  - `architect-catalog`
  - `architect-planner`
  - `architect-builder`
  - `architect-coder`
  - `architect-tester`

All are upserted and kept active/published by seed logic.

## Orchestrator Graph (Current Topology)
The orchestrator uses `spec_version: "2.0"` and these orchestration node types:
- `spawn_group`
- `join`
- `replan`
- `cancel_subtree`

### Control-flow stages (linear)
1. `start`
2. `spawn_catalog_stage` -> `join_catalog_stage`
3. `spawn_planner_stage` -> `join_planner_stage`
4. `spawn_builder_stage` -> `join_builder_stage`
5. `spawn_coder_stage` -> `join_coder_stage`
6. `spawn_tester_stage` -> `join_tester_stage`
7. `replan_core`
8. if `replan_core=continue` -> `final_report`
9. if `replan_core=replan`:
   - `spawn_replanner_stage` -> `join_replanner_stage`
   - `cancel_subtree`
   - `final_report`
10. `end`

### Join branching behavior in stage joins
For each stage join (`join_*_stage`):
- `pending` loops back to the same join node
- terminal handles (`completed`, `completed_with_errors`, `failed`, `timed_out`) advance to the next stage

This keeps execution strictly stage-by-stage while tolerating partial failures (`best_effort`) and deferring retry decisions to `replan_core`.

## Why the flow is structured this way
The flow is intentionally linear and easier to reason about:
1. one stage at a time
2. explicit wait barriers (`join`) between stages
3. single replan decision near the end instead of mid-graph branch fanout

## Node Semantics
### Stage spawns (`spawn_*_stage`)
Each stage is a single-target `spawn_group` with:
- `join_mode: best_effort`
- `failure_policy: best_effort`
- `start_background: true`
- stage-specific `idempotency_key_prefix`:
  - `platform-architect:catalog-stage:v3`
  - `platform-architect:planner-stage:v3`
  - `platform-architect:builder-stage:v3`
  - `platform-architect:coder-stage:v3`
  - `platform-architect:tester-stage:v3`
  - `platform-architect:replanner-stage:v3`

### Stage joins (`join_*_stage`)
Each join blocks on its stage group and returns:
- `complete` flag
- `status` (`running`, `completed`, `completed_with_errors`, `failed`, `timed_out`)
- success/failure/running counts
- cancellation propagation metadata (if any)

### `replan_core`
Calls kernel `evaluate_and_replan` and returns branch handle:
- `replan`
- `continue`

### `cancel_subtree`
Performs cleanup cancellation for active descendants before final reporting.
- includes root: `false`
- reason: `platform_architect_orchestration_cleanup`

### `final_report`
Final reasoning node summarizes stage outputs from `state._node_outputs` into JSON and avoids over-claiming side effects.

## Sub-Agent Architecture
All sub-agents are seeded with:
- `start -> agent -> end`

Differences are prompt intent, tool attachments, and output schema:
- `architect-catalog`: catalog introspection (`fetch_catalog` via Platform SDK tool)
- `architect-planner`: strict plan JSON
- `architect-builder`: deploy payload JSON
- `architect-coder`: artifact/tool draft JSON
- `architect-tester`: test execution report JSON (Platform SDK tool)

## Orchestration Kernel Architecture
Canonical orchestration layer:
- `backend/app/services/orchestration_kernel_service.py`

Supported actions:
- `spawn_run`
- `spawn_group`
- `join`
- `cancel_subtree`
- `evaluate_and_replan`
- `query_tree`

Used by:
- GraphSpec v2 orchestration node executors (Option A)
- internal orchestration API + SDK primitive actions (Option B)

## Policy and Governance
Policy service:
- `backend/app/services/orchestration_policy_service.py`

Enforced controls:
- target allowlist
- published-only target eligibility
- spawn safety limits (`max_depth`, `max_fanout`, `max_children_total`)
- scope subset validation against:
  - caller effective scopes
  - orchestrator allowed scope subset

Seeded policy values:
- `default_failure_policy = best_effort`
- `max_depth = 8`
- `max_fanout = 8`
- `max_children_total = 32`
- `join_timeout_s = 180`
- `allowed_scope_subset` includes catalog/write/execute/test capabilities

Allowlist rows are auto-seeded for the five architect sub-agents.

## Delegated Identity and Security Flow
For each orchestration spawn:
1. parent run must carry principal/grant context
2. kernel mints child delegation grant
3. kernel mints short-lived workload token
4. token + lineage metadata are injected into child payload
5. child run executes with scoped identity context

This is the basis for secure internal API access in sub-agent tool/artifact actions.

## Runtime Execution and Eventing
Graph compile/runtime:
- compiler validates orchestration invariants
- runtime adapter executes via LangGraph
- node factory injects run/tenant/grant/lineage context

Orchestration events:
- `orchestration.spawn_decision`
- `orchestration.child_lifecycle`
- `orchestration.join_decision`
- `orchestration.policy_deny`
- `orchestration.cancellation_propagation`

Run tree visibility:
- `/agents/runs/{run_id}?include_tree=true`
- `/agents/runs/{run_id}/tree`
- `/internal/orchestration/runs/{run_id}/tree`

## Data Model Support
### Agent run lineage fields (`agent_runs`)
- `root_run_id`
- `parent_run_id`
- `parent_node_id`
- `depth`
- `spawn_key`
- `orchestration_group_id`

### Orchestration tables
- `orchestrator_policies`
- `orchestrator_target_allowlists`
- `orchestration_groups`
- `orchestration_group_members`

### Idempotency model
Idempotency is enforced by:
- `(parent_run_id, spawn_key)`

`spawn_group` derives per-target keys from `idempotency_key_prefix:{index}`.

## Feature Flags and Surfaces
Option A:
- GraphSpec v2 orchestration nodes in agent graphs
- env gate: `ORCHESTRATION_OPTION_A_ENABLED`

Option B:
- runtime primitive internal API + Platform SDK primitive actions
- env gate: `ORCHESTRATION_OPTION_B_ENABLED`

Both support tenant allowlist-style gating via env configuration.

## Current Strengths
- clear staged flow that is easier to reason about than the prior parallel core fanout
- centralized orchestration semantics in kernel service
- explicit policy boundary for allowlist/scope/safety controls
- delegated least-privilege workload token model
- deterministic lineage/run-tree introspection

## Current Limitations
- topology remains static and not planner-generated
- stage-to-stage payload contracts are prompt-driven, not hard schema-wired across all stages
- replan remains a single late-stage retry path (not full multi-iteration closed-loop orchestration)
- startup seed still selects one tenant for initial seeding behavior

## Primary Source Files
- `backend/main.py`
- `backend/app/services/registry_seeding.py`
- `backend/app/services/orchestration_kernel_service.py`
- `backend/app/services/orchestration_policy_service.py`
- `backend/app/services/orchestration_lineage_service.py`
- `backend/app/agent/executors/orchestration.py`
- `backend/app/agent/executors/standard.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/agent/runtime/langgraph_adapter.py`
- `backend/app/agent/graph/node_factory.py`
- `backend/artifacts/builtin/platform_sdk/handler.py`
- `backend/app/db/postgres/models/agents.py`
- `backend/app/db/postgres/models/orchestration.py`
