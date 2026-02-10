# Platform Architect Seeded Multi-Agent System — Current Architecture

Last Updated: 2026-02-09

## Purpose
This document describes the current runtime architecture of the seeded `Platform Architect` system as implemented in code today. It focuses on the actual seeded graph, orchestration kernel behavior, policy/security model, execution lifecycle, and known limitations.

## System Classification
The seeded Platform Architect is a **GraphSpec v2 node-orchestration agent**.

- It is not a free-form tool loop that dynamically invents topology at runtime.
- It uses a predetermined orchestration graph with orchestration node types:
  - `spawn_run`
  - `spawn_group`
  - `join`
  - `router`
  - `judge`
  - `replan`
  - `cancel_subtree`
- Sub-agents may use tools internally (for example, Platform SDK), but orchestration structure is fixed by graph definition.

## Startup and Seeding Path
At app startup, the seeded architect is created/updated by the lifecycle bootstrap:

1. `seed_global_models(db)`
2. `seed_platform_sdk_tool(db)`
3. `seed_platform_architect_agent(db)`

Code path:
- `backend/main.py`
- `backend/app/services/registry_seeding.py`

### Seeded Agent Set
The seeding routine creates/updates these tenant-scoped agents:

- Orchestrator:
  - `platform-architect`
- Sub-agents:
  - `architect-catalog`
  - `architect-planner`
  - `architect-builder`
  - `architect-coder`
  - `architect-tester`

The orchestrator and sub-agents are seeded as `published`, `is_active=true`, and `is_public=false`.

## Seeded Graph Topology (Platform Architect)
The orchestrator graph is seeded with `spec_version: "2.0"` and includes this control flow:

1. `start`
2. `spawn_catalog` (`spawn_run` -> catalog sub-agent)
3. `spawn_core_group` (`spawn_group` -> planner + builder + coder + tester)
4. `join_core_group` (`join`)
5. branch handling:
   - `completed` / `completed_with_errors` -> `judge_core`
   - `failed` -> `replan_core`
   - `timed_out` -> `cancel_subtree`
   - `pending` -> self-loop back to `join_core_group`
6. `judge_core`:
   - `pass` -> `final_report`
   - `fail` -> `replan_core`
7. `replan_core`:
   - `continue` -> `final_report`
   - `replan` -> `route_replan`
8. `route_replan`:
   - `replan` -> `spawn_replanner`
   - `continue` / `default` -> `final_report`
9. `spawn_replanner` -> `cancel_subtree`
10. `cancel_subtree` -> `final_report`
11. `final_report` (`agent` node)
12. `end`

## Node-Level Semantics
### `spawn_catalog`
- Spawns `architect-catalog` as a background child run.
- Uses fixed idempotency key: `platform-architect:catalog:v2`.
- Uses orchestration scope subset from seeded list.

### `spawn_core_group`
- Spawns planner/builder/coder/tester in one orchestration group.
- Group join mode: `best_effort`.
- Timeout: 180 seconds.
- Uses idempotency key prefix: `platform-architect:core-group:v2`.

### `join_core_group`
- Computes status (`running`, `completed`, `completed_with_errors`, `failed`, `timed_out`) based on member run states and join policy.
- Can trigger cancellation propagation for active members in specific modes/outcomes.

### `judge_core`
- Converts join-style status signals into pass/fail branching.
- Uses `outcomes: ["pass", "fail"]` in seeded graph.

### `replan_core`
- Calls kernel `evaluate_and_replan` over a resolved run context.
- Produces `suggested_action` and routes to `replan` or `continue`.

### `route_replan`
- Routes on `suggested_action`.
- Exists as a routing node abstraction over replan output.

### `spawn_replanner`
- Spawns planner sub-agent with replan prompt.
- Uses idempotency key: `platform-architect:replanner:v2`.

### `cancel_subtree`
- Cancels queued/running/paused runs in target subtree for cleanup.
- Seeded reason: `platform_architect_orchestration_cleanup`.

### `final_report`
- Final `agent` node with JSON output target.
- Instructions explicitly summarize orchestration outcomes from `state._node_outputs`.
- Guardrail: do not claim publish/promote unless shown in node outputs.

## Sub-Agent Architecture
Each sub-agent is seeded as a simple 3-node graph:

- `start -> agent -> end`

### Sub-Agent Roles and Tooling
- `architect-catalog`
  - Uses Platform SDK tool.
  - Prompt requires a single `fetch_catalog` call and JSON catalog output.
- `architect-planner`
  - No tool attached by seed.
  - Outputs plan-oriented JSON structure.
- `architect-builder`
  - No tool attached by seed.
  - Outputs deploy payload JSON.
- `architect-coder`
  - No tool attached by seed.
  - Outputs artifact/tool draft JSON.
- `architect-tester`
  - Uses Platform SDK tool.
  - Prompt requests `run_tests` and report JSON.

## Orchestration Kernel and Policy Architecture
All orchestration actions go through `OrchestrationKernelService`.

### Supported Kernel Actions
- `spawn_run`
- `spawn_group`
- `join`
- `cancel_subtree`
- `evaluate_and_replan`
- `query_tree`

### Policy Enforcement
`OrchestrationPolicyService` enforces:

- allowlist target restrictions
- published-only target checks (if enabled)
- spawn limits:
  - `max_depth`
  - `max_fanout`
  - `max_children_total`
- scope subset checks:
  - requested subset must be within caller effective scopes
  - requested subset must be within policy allowed scope subset

### Seeded Policy Defaults for Platform Architect
The seeding routine creates/updates:

- `OrchestratorPolicy` for orchestrator agent
- `OrchestratorTargetAllowlist` entries for each sub-agent

Seeded values:
- `enforce_published_only = true`
- `default_failure_policy = best_effort`
- `max_depth = 3`
- `max_fanout = 8`
- `max_children_total = 32`
- `join_timeout_s = 180`
- `capability_manifest_version = 2`

## Identity, Delegation, and Token Flow
The runtime model is delegated workload identity end-to-end.

### Parent Run Context
Parent run must have:
- `workload_principal_id`
- `delegation_grant_id`

### Child Spawn Security Flow
For each spawn:
1. kernel verifies caller grant context
2. kernel mints child delegation grant
3. kernel mints short-lived workload token from child grant
4. kernel injects token + grant/principal/run lineage into child payload context/state
5. child run starts with lineage metadata and scoped grant

## Runtime Execution Architecture
### Compiler and Runtime
- `AgentCompiler` validates graph and compiles to GraphIR.
- `LangGraphAdapter` executes graph with routing maps.
- Node factory injects execution context (run_id, tenant_id, grant_id, lineage).

### Orchestration Event Model
Executors emit orchestration-specific events for observability:
- `orchestration.spawn_decision`
- `orchestration.child_lifecycle`
- `orchestration.join_decision`
- `orchestration.policy_deny`
- `orchestration.cancellation_propagation`

### Run Tree Visibility
Run tree is queryable via:
- `/agents/runs/{run_id}?include_tree=true`
- `/agents/runs/{run_id}/tree`
- `/internal/orchestration/runs/{run_id}/tree`

## Platform SDK in Architect Context
Platform SDK tool includes orchestration primitive actions and builder/test actions.

Actions include:
- `fetch_catalog`
- `validate_plan`
- `execute_plan`
- `create_artifact_draft`
- `promote_artifact`
- `create_tool`
- `run_agent`
- `run_tests`
- `spawn_run`
- `spawn_group`
- `join`
- `cancel_subtree`
- `evaluate_and_replan`
- `query_tree`
- `respond`

In current seed usage:
- Catalog and Tester sub-agents are the primary seeded Platform SDK users.

## Data Model Surface
### `agent_runs` lineage fields
- `root_run_id`
- `parent_run_id`
- `parent_node_id`
- `depth`
- `spawn_key`
- `orchestration_group_id`

### orchestration tables
- `orchestrator_policies`
- `orchestrator_target_allowlists`
- `orchestration_groups`
- `orchestration_group_members`

These support policy enforcement, allowlisting, group join semantics, lineage queries, and idempotency.

## Feature Flag Surfaces
Two orchestration surfaces are gated:

- Option A: GraphSpec v2 orchestration nodes
  - env: `ORCHESTRATION_OPTION_A_ENABLED`
  - optional tenant allowlists supported
- Option B: Runtime primitive/internal API orchestration actions
  - env: `ORCHESTRATION_OPTION_B_ENABLED`
  - optional tenant allowlists supported

## Current Behavior vs Intended Capability
The seeded system provides a robust orchestration skeleton and policy/security kernel.

Important current-state characteristics:
- Topology is fixed and deterministic at orchestrator level.
- Dynamic reasoning occurs inside agent nodes/sub-agents.
- Replan path currently behaves as advisory/cleanup path, not full in-loop re-execution of a rebuilt core group.
- Catalog stage is separated from core group by control flow, but strict payload dependency wiring from catalog output to all core targets is limited in seed definition.

## Validation and Test Status
Recent orchestration suites (GraphSpec v2, runtime primitives/events, join policies, limits/cancellation, platform SDK orchestration actions) are passing in targeted runs.

Legacy architect integration tests under `backend/tests_legacy/test_platform_architect_integration.py` are currently drifted from modern delegated-token and current seed assumptions.

## Related Files
- `backend/main.py`
- `backend/app/services/registry_seeding.py`
- `backend/app/services/orchestration_kernel_service.py`
- `backend/app/services/orchestration_policy_service.py`
- `backend/app/services/orchestration_lineage_service.py`
- `backend/app/agent/executors/orchestration.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/agent/runtime/langgraph_adapter.py`
- `backend/artifacts/builtin/platform_sdk/handler.py`
- `backend/app/db/postgres/models/agents.py`
- `backend/app/db/postgres/models/orchestration.py`
