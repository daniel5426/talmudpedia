# Test State: Orchestration GraphSpec v2

Last Updated: 2026-04-14

**Scope**
GraphSpec v2 orchestration compiler/runtime contract coverage and orchestration node executor behavior.

**Test Files**
- `test_graphspec_v2_orchestration.py`

**Scenarios Covered**
- Current compiler behavior for unknown GraphSpec version strings.
- Feature-flag gate for Option A (`ORCHESTRATION_OPTION_A_ENABLED`) at compile validation.
- Current compiler behavior defers allowlist/published/scope/limit policy checks to runtime orchestration services.
- Join routing/branch-edge validation and support for `fail_fast` / `best_effort` mode values.
- Executor dispatch to orchestration kernel (`spawn_run`, `join`, `replan`).

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py backend/tests/orchestration_join_policies/test_join_policies.py backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
- Date: 2026-04-14 Asia/Hebron
- Result: Pass (`29 passed, 17 warnings`)

**Known Gaps / Follow-ups**
- Add stress tests for cancellation storms and deep fanout under real DB mode.
- Add integration tests that execute end-to-end graphs with mixed v1 + v2 nodes.
