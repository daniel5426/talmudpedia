# Test State: Orchestration Limits and Cancellation

Last Updated: 2026-02-08

**Scope**
Runtime safety limits, timeout behavior, subtree cancellation propagation, and idempotency stress for orchestration kernel operations.

**Test Files**
- `test_limits_and_cancellation.py`

**Scenarios Covered**
- Repeated `spawn_run` calls with the same idempotency key collapse into one child run.
- Runtime fanout and depth limits are enforced by policy (`max_fanout`, `max_depth`).
- Join timeout deterministically transitions to `timed_out` and cancels active members.
- Repeated subtree cancellation calls are idempotent after first propagation.

**Last Run**
- Command: `pytest -q backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py backend/tests/orchestration_join_policies/test_join_policies.py backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
- Date: 2026-02-08
- Result: Pass (`29 passed`)

**Known Gaps / Follow-ups**
- Add heavier stress loops (hundreds of children) for cancellation storms.
- Add assertions for propagation behavior on deeper multi-level trees.
