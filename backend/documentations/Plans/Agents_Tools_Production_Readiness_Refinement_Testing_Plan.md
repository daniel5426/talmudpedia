# Agents + Tools Production Readiness Refinement & Testing Plan

Last Updated: 2026-02-11

## Objective
Move Agents + Tools from partially stable to production-ready by closing security/policy gaps, eliminating order-dependent failures, hardening runtime reliability, and expanding deterministic test coverage.

## Current Snapshot
- Overall readiness (current): Agents `5/10`, Tools `6/10`, fresh-user UX `4/10`.
- Major blocker fixed in this cycle: legacy chat import-time bootstrap side effects (Pinecone call on import) were removed via lazy initialization.
- Major blocker fixed in this cycle: run resume endpoint now enforces tenant and ownership checks before resuming.
- Major blocker fixed in this continuation: order-dependent failures in tools/builtin clusters were eliminated by eager SQLite metadata type normalization in `backend/tests/conftest.py`.

## Findings (Consolidated)
1. Import-time side effects previously caused external dependency calls during app import.
- Evidence path: `backend/main.py` includes legacy router import chain ending in legacy agent construction.
- Impact: flaky setup, non-deterministic tests, startup fragility.
- Status: fixed this cycle with lazy init in `app/api/routers/agent.py`.

2. Resume authorization was previously incomplete.
- Evidence path: `app/api/routers/agents.py` had TODO for ownership verification.
- Impact: potential cross-user resume access within tenant, weak run-level boundary enforcement.
- Status: fixed this cycle with explicit tenant/user/principal checks in `POST /agents/runs/{run_id}/resume`.

3. Agent publish/validation guardrails are still incomplete.
- `AgentService.validate_agent()` is still placeholder-only.
- Published-agent mutation behavior remains under-defined/inconsistent.
- `/agents/{id}/execute` path does not enforce an explicit published-only policy despite endpoint intent text.

4. Runtime durability is not production-grade.
- Agent execution checkpointing currently uses in-memory saver (`MemorySaver`), not durable store.
- Multi-instance and restart durability risks remain.

5. Debug/production auth hardening remains incomplete.
- Stream mode switching still has TODO around stronger principal-type enforcement for debug access.

6. Frontend contract/UX gaps remain.
- `agentService.executeAgent` payload mismatch (`input_params` vs backend schema) remains.
- Builder fetches only published tools, limiting debug iteration against draft tools.
- Tools creation UX is still schema-heavy for first-time users.

7. Testing maturity improved and deterministic mixed-suite stability is now restored for the targeted cluster.
- New targeted tests pass for lazy bootstrap + resume auth.
- Root cause: UUID/enum/jsonb SQLite type coercion ran too late (at `before_create`), allowing early ORM expression construction to cache incompatible bind behavior.
- Fix: eager metadata coercion at test bootstrap (`backend/tests/conftest.py`) before any test-level ORM expressions.
- Validation: mixed suite passes consistently across 5 consecutive runs.

## What Was Implemented In This Cycle
### Backend changes
- Lazy legacy chat agent initialization:
  - `backend/app/api/routers/agent.py`
- Resume run authorization checks:
  - `backend/app/api/routers/agents.py`
- Production stream adapter now forwards tool lifecycle events and synthesized reasoning steps:
  - `backend/app/agent/execution/adapter.py`

### New test features
- `backend/tests/legacy_chat_bootstrap/`
  - `test_lazy_agent_initialization.py`
  - `test_state.md`
- `backend/tests/agent_resume_authorization/`
  - `test_resume_authorization.py`
  - `test_state.md`
- `backend/tests/agent_tool_usecases/`
  - `test_agent_builtin_tool_flow.py`
  - `test_agent_tool_reasoning_stream.py`
  - `test_agent_execution_panel_stream_api.py`
  - `test_state.md`
  - Added real-user style multi-step tool flows and stream-adapter assertions for:
    - debug reasoning-step synthesis (`active`/`complete`) per tool call
    - production tool lifecycle + reasoning visibility
    - tool failure lifecycle correctness (active step + error, no false completion)
    - parallel-safe dual-tool reasoning lifecycle coverage
    - multi-agent production runs (web-search only, retrieval only, mixed) with per-run tool-call and reasoning lifecycle assertions
    - execution-panel API parity (`/agents/{id}/stream?mode=debug`) for simplest user setup (`gpt-5.2` + web search), including the empty-tool-args failure mode seen in manual usage

### Validation runs
- Passed:
  - `pytest -q backend/tests/legacy_chat_bootstrap backend/tests/agent_resume_authorization backend/tests/tools_guardrails -vv`
  - Result: `11 passed`
- Passed:
  - `pytest -q backend/tests/agent_tool_usecases -vv`
  - Result: `7 passed`
- Passed:
  - `pytest -q backend/tests/agent_tool_usecases backend/tests/agent_tool_loop backend/tests/builtin_tool_execution backend/tests/tool_execution -vv`
  - Result: `25 passed`
- Historical unstable run (now resolved):
  - `pytest -q backend/tests/agent_execution_events backend/tests/agent_tool_loop backend/tests/builtin_tool_execution backend/tests/tools_guardrails backend/tests/tool_execution backend/tests/agent_api_context backend/tests/builtin_tools_registry`
  - Result: `7 failed, 23 passed, 1 skipped`
  - Pattern: order-dependent failures across tool resolver/executor and builtin registry scenarios.
- Determinism validation (current):
  - `for i in 1 2 3 4 5; do pytest -q backend/tests/agent_execution_events backend/tests/agent_tool_loop backend/tests/builtin_tool_execution backend/tests/tools_guardrails backend/tests/tool_execution backend/tests/agent_api_context backend/tests/builtin_tools_registry || exit 1; done`
  - Result: 5/5 successful runs (`30 passed, 1 skipped` each run).

## Recommended Continuation Plan
## Phase 1: Deterministic Test Bed (Immediate)
Goal: eliminate order dependence and hidden shared state.
Status: completed for the targeted mixed suite cluster.

Tasks:
1. Isolate mutation points in tests that monkeypatch shared classes/services (`ToolNodeExecutor`, resolver paths, model resolver).
2. Add explicit teardown/reset guards for patched globals and module-level caches.
3. Add focused reproduction tests for ordering:
- Run A then B vs B then A across:
  - `agent_tool_loop`
  - `tools_guardrails`
  - `builtin_tools_registry`
4. Harden UUID typing in API test assertions to avoid string-vs-UUID mismatch regressions (seen in builtin registry tests).

Exit criteria:
- No failures when running targeted mixed suite 5 consecutive runs.
- Current status: met (5/5 consecutive successful runs).

## Phase 2: Policy/Authorization Completion
Goal: close security and lifecycle ambiguity.

Tasks:
1. Finalize published lifecycle rules:
- Define allowed/disallowed updates for published agents/tools.
- Enforce in service layer and API layer consistently.
2. Replace `validate_agent` placeholder with real graph validation pipeline and actionable errors.
3. Enforce execution policy explicitly:
- If endpoint states “published-only”, make it hard-enforced for production mode.
4. Complete debug-mode auth hardening:
- allow debug only for authorized internal principals.

Exit criteria:
- Policy tests exist for every boundary (publish/update/execute/debug access) and all pass.

## Phase 3: Runtime Durability Hardening
Goal: production-safe execution persistence.

Tasks:
1. Replace in-memory checkpoint saver with durable backend (Postgres-based checkpoint saver).
2. Add restart-resume integration tests:
- pause run -> simulate process restart -> resume run.
3. Add multi-run concurrency tests for checkpoint consistency and lineage integrity.

Exit criteria:
- Resume/restart reliability proven by integration tests and trace verification.

## Phase 4: UX + Service Contract Alignment
Goal: reduce fresh-user friction and eliminate contract drift.

Tasks:
1. Fix frontend execute payload contract in `agentService.executeAgent`.
2. Builder tool selection policy:
- show draft + published in debug authoring contexts with clear badges/warnings.
3. Improve tool creation UX:
- templates/wizards for common tool types (HTTP/MCP/function/retrieval).
- inline schema helpers instead of raw JSON-only workflow.
4. Promote user-facing error surfaces (not console-only) in Agents/Tools pages.

Exit criteria:
- New-user smoke flow can create agent, attach tool, run debug, publish, execute production without hidden errors.

## Phase 5: Test Expansion Program (Broad)
Goal: materially expand test depth and coverage.

Add/expand feature directories under `backend/tests/` with `test_state.md` updates:
1. `agent_publish_policies/`
- Published update restrictions, validation gating, execute-mode policy.
2. `agent_resume_authorization/` (extend)
- workload principal mismatch, admin override behavior, null-user edge cases.
3. `agent_checkpoint_durability/`
- restart-resume and lineage integrity.
4. `tools_registry_consistency/`
- deterministic resolver/executor behavior across mixed test order.
5. `tools_builder_contracts/` (frontend)
- payload schema alignment and builder tool filtering behavior.
6. `first_time_user_journeys/` (frontend integration)
- create agent -> add tool -> run debug -> publish -> production run.

Quality gates:
- PR gate must run deterministic subset:
  - tools guardrails
  - builtin tools registry
  - agent resume auth
  - agent tool loop
- Nightly gate must run extended mixed suite + order-variation runs.

## Proposed Next Execution Order
1. Implement agent publish/validation policy hardening.
2. Land durable checkpointing path and restart-resume tests.
3. Align frontend execute contract and builder tool filtering for debug workflows.
4. Expand first-time-user flow tests (backend + frontend).

## Risks If Deferred
- Hidden cross-tenant/user resume risks resurface in other endpoints.
- Production incidents from non-durable checkpointing.
- Regression churn from order-dependent tests reducing deploy confidence.
- Fresh users fail silently during setup due to UX+contract mismatch.

## Success Definition
Agents + Tools are “production ready” when:
1. No critical auth/policy TODOs remain in execution pathways.
2. Deterministic test suites pass repeatedly under mixed-order execution.
3. Checkpointing is durable across restarts.
4. Frontend contracts are aligned and verified by tests.
5. First-time-user end-to-end flows are covered by stable automated tests.
