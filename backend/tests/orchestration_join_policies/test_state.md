# Test State: Orchestration Join Policies

Last Updated: 2026-02-08

**Scope**
Deterministic join semantics for orchestration groups across `best_effort`, `fail_fast`, `quorum`, and `first_success`.

**Test Files**
- `test_join_policies.py`

**Scenarios Covered**
- `fail_fast` completes immediately on first failure and cancels active siblings.
- `first_success` completes on first success and cancels remaining active siblings.
- `quorum` stays running while still reachable and fails when quorum becomes impossible.
- `best_effort` returns `completed_with_errors` when all children finish with mixed outcomes.

**Last Run**
- Command: `pytest -q backend/tests/orchestration_graphspec_v2/test_graphspec_v2_orchestration.py backend/tests/orchestration_runtime_primitives/test_runtime_events_and_flags.py backend/tests/orchestration_join_policies/test_join_policies.py backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
- Date: 2026-02-08
- Result: Pass (`29 passed`)

**Known Gaps / Follow-ups**
- Add explicit assertions for member-table status transitions (`orchestration_group_members.status`).
- Add coverage for group-level `failure_policy=fail_fast` when `join.mode` is omitted.
