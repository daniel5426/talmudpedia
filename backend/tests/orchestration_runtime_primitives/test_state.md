# Test State: Orchestration Runtime Primitives

Last Updated: 2026-02-08

**Scope**
Event parity and feature-flag gating for GraphSpec v2 orchestration executors (Option A) and Platform SDK runtime primitives (Option B).

**Test Files**
- `test_runtime_events_and_flags.py`

**Scenarios Covered**
- Spawn execution emits standardized orchestration events (`spawn_decision`, `child_lifecycle`).
- Policy denies emit standardized `policy_deny` events.
- Join execution emits `join_decision` and cancellation propagation events.
- Option A feature flag blocks graph orchestration execution paths.
- Option B feature flag blocks Platform SDK primitive actions.

**Last Run**
- Command: `pytest -q backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py backend/tests/orchestration_join_policies/test_join_policies.py backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
- Date: 2026-02-08
- Result: Pass (`29 passed`)

**Known Gaps / Follow-ups**
- Add integration tests that assert streamed SSE payloads from `/agents/{id}/stream` include orchestration events.
- Add parity tests that compare Option A graph execution and Option B internal API outputs on identical scenarios.
