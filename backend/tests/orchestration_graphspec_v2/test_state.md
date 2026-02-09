# Test State: Orchestration GraphSpec v2

Last Updated: 2026-02-08

**Scope**
GraphSpec v2 orchestration compile-time invariants and orchestration node executor behavior.

**Test Files**
- `test_graphspec_v2_orchestration.py`

**Scenarios Covered**
- GraphSpec version gate for v2 orchestration nodes.
- Feature-flag gate for Option A (`ORCHESTRATION_OPTION_A_ENABLED`) at compile validation.
- Allowlist and published-only compile-time target checks.
- Scope subset overflow validation against policy capability set.
- Static safety checks for `max_fanout`, `max_children_total`, and `max_depth`.
- Join edge/contract validation and support for `fail_fast` / `best_effort` mode values.
- Executor dispatch to orchestration kernel (`spawn_run`, `join`, `replan`).

**Last Run**
- Command: `pytest -q backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py backend/tests/orchestration_join_policies/test_join_policies.py backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
- Date: 2026-02-08
- Result: Pass (`29 passed`)

**Known Gaps / Follow-ups**
- Add stress tests for cancellation storms and deep fanout under real DB mode.
- Add integration tests that execute end-to-end graphs with mixed v1 + v2 nodes.
