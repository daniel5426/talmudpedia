# Multi-Agent Orchestration v2 Handoff Prompt (Post Phase 1-7)

Last Updated: 2026-02-14

## 1. Purpose
Use this file as the start prompt for a fresh-context implementation chat.  
It summarizes what is already implemented and provides a detailed next-step execution plan.

## 2. What Has Been Done

### 2.1 Kernel and Runtime Primitive Surface (Implemented)
The following has been implemented and wired:

1. Core orchestration kernel services:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/orchestration_kernel_service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/orchestration_policy_service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/orchestration_lineage_service.py`

2. Internal orchestration API endpoints:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/orchestration_internal.py`
- router registration in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/main.py`

3. DB model + migration for lineage/policy/group tracking:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/orchestration.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/agents.py` (lineage columns added to `AgentRun`)
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/e6f1a9b4c2d0_add_orchestration_kernel_tables_and_lineage.py`

4. Runtime context lineage propagation:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/execution/service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/runtime/langgraph_adapter.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/graph/node_factory.py`

5. Platform SDK runtime primitive actions now call kernel-backed internal APIs:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/artifacts/builtin/platform_sdk/handler.py`
- Added actions:
  - `spawn_run`
  - `spawn_group`
  - `join`
  - `cancel_subtree`
  - `evaluate_and_replan`
  - `query_tree`

### 2.2 Policy Semantics Already Enforced
Current kernel path enforces:
- allowlist restrictions per orchestrator
- published-only target eligibility (default policy)
- spawn safety limits (`max_depth`, `max_fanout`, `max_children_total`)
- scope subset checks against caller delegation and orchestrator policy
- idempotent spawn behavior via `(parent_run_id, spawn_key)`

### 2.3 Test Coverage Already Added
New tests:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`

State tracking:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/orchestration_kernel/test_state.md`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/platform_sdk_tool/test_state.md`

Latest validated command and result:
- `pytest -q backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py backend/tests/workload_delegation_auth/test_phase2_runtime_propagation.py`
- Result: `13 passed`

### 2.4 Phase 3 + 4 Baseline (Implemented in this continuation)
The following baseline implementation is now in place:

1. GraphSpec v2 orchestration node surface is recognized:
- `backend/app/agent/graph/schema.py`
- `backend/app/agent/graph/ir.py`

2. Compiler now supports GraphSpec v2 and validates orchestration invariants:
- `backend/app/agent/graph/compiler.py`
- Includes:
  - v2 version gating for orchestration nodes (`spec_version = "2.0"`)
  - policy-aware compile checks (allowlist, published-only when DB context exists)
  - scope subset capability checks
  - static safety checks (`max_depth`, `max_fanout`, `max_children_total`)
  - join/replan/cancel structural contract checks

3. Graph-native orchestration executors added and registered:
- `backend/app/agent/executors/orchestration.py`
- `backend/app/agent/executors/standard.py`
- Implemented executors:
  - `SpawnRunNodeExecutor`
  - `SpawnGroupNodeExecutor`
  - `JoinNodeExecutor`
  - `RouterNodeExecutor`
  - `JudgeNodeExecutor`
  - `ReplanNodeExecutor`
  - `CancelSubtreeNodeExecutor`
- All orchestration actions route through `OrchestrationKernelService`.

4. New test feature directory for GraphSpec v2 orchestration:
- `backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py`
- `backend/tests/orchestration_graphspec_v2/test_state.md`
- Targeted run currently passing (`12 passed` across targeted suites).

### 2.5 Phase 5 + 6 + 7 Baseline (Implemented in this continuation)
The following hardening is now in place:

1. Runtime/event parity and deterministic cancellation semantics:
- standardized orchestration events (`spawn_decision`, `child_lifecycle`, `join_decision`, `policy_deny`, `cancellation_propagation`)
- deterministic join behavior for `best_effort`, `fail_fast`, `quorum`, and `first_success`
- timeout-driven cancellation propagation for active group members

2. Feature-flagged rollout hardening:
- Option A (GraphSpec v2 orchestration surface) feature gate with tenant-scoped enablement
- Option B (runtime primitives/internal API + SDK primitive actions) feature gate with tenant-scoped enablement
- run-tree debug support exposed on `/agents/runs/{run_id}` (`include_tree`) and `/agents/runs/{run_id}/tree`

3. Expanded test matrix with feature-level `test_state.md` tracking:
- `backend/tests/orchestration_graphspec_v2/`
- `backend/tests/orchestration_runtime_primitives/`
- `backend/tests/orchestration_join_policies/`
- `backend/tests/orchestration_limits_and_cancellation/`
- Latest targeted validation:
  - `pytest -q backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py backend/tests/orchestration_join_policies/test_join_policies.py backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
  - Result: `29 passed`

### 2.6 Tool-Based Agent-to-Agent Calls (Current Scope Update)
The platform now also supports a first-class tool subtype for synchronous agent-to-agent calls:

1. New tool implementation type:
- `implementation_type = agent_call`

2. Runtime contract:
- tool config accepts `target_agent_id` or `target_agent_slug`
- optional timeout via `execution.timeout_s`
- target must be published and in tenant scope
- execution returns compact sync payload (`mode`, target metadata, `run_id`, `status`, optional `output/context/error`)

3. Retrieval pipeline tools:
- retrieval is now selected through regular tool creation (`implementation_type = rag_retrieval`) with tenant pipeline validation
- built-in instance management API/UI paths are removed; built-in templates remain read-only catalog data

## 3. What Is Not Done Yet (Critical Next Work)
Remaining gaps are now mostly scale and production-burn-in focused:
1. Add deeper stress tests (hundreds/thousands of children) for cancellation storms.
2. Add integration parity tests that compare Option A graph execution and Option B primitive outputs for identical scenarios.
3. Add optional UI-specific assertions for orchestration event rendering in debug streams.

## 4. Detailed Next Steps (Execution Order)
1. Extend stress harnesses for high fanout and deep trees under realistic DB/worker settings.
2. Add cross-surface parity suite that executes equivalent scenarios through both entry points and asserts identical policy outcomes.
3. Add rollout dashboards/alerts around feature-flag usage and denied-call rates per tenant.

## 5. Fresh-Chat Prompt (Copy This)
Use this exact prompt in a new chat:

1. "Read `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/summary/multi_agent_orchestration_v2_phase1_phase2_handoff_prompt.md` first."
2. "Implement Phase 3 first: GraphSpec v2 schema/IR/compiler orchestration nodes with compile-time policy invariants."
3. "Then implement Phase 4: orchestration node executors and registry wiring, ensuring all orchestration logic routes through `orchestration_kernel_service.py`."
4. "After that, implement Phase 5 runtime/event parity and deterministic join/cancel semantics for best-effort, fail-fast, quorum, and first-success."
5. "Before coding, provide a file-by-file checklist; then execute and run tests with updated `test_state.md` files."

## 6. Guardrails
- Do not reopen locked product decisions from the v2 master plan.
- Keep Graph-first canonical; runtime primitives must remain kernel-backed.
- Do not add page-local frontend `types.ts` or `api.ts`; keep shared types/services centralized.
