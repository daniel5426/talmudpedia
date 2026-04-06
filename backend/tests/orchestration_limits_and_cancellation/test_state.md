# Test State: Orchestration Limits and Cancellation

Last Updated: 2026-04-04

**Scope**
Runtime safety limits, timeout behavior, subtree cancellation propagation, and idempotency stress for orchestration kernel operations.

**Test Files**
- `test_limits_and_cancellation.py`

**Scenarios Covered**
- Repeated `spawn_run` calls with the same idempotency key collapse into one child run.
- Runtime fanout and depth limits are enforced by policy (`max_fanout`, `max_depth`).
- Join timeout deterministically transitions to `timed_out` and cancels active members.
- Repeated subtree cancellation calls are idempotent after first propagation.
- `spawn_run` now rejects cancelled caller runs so cancelled parents cannot keep fanning out new descendants.

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_resume_authorization backend/tests/orchestration_limits_and_cancellation/test_limits_and_cancellation.py backend/tests/tool_execution/test_agent_call_tool_execution.py`
- Date: 2026-04-04 Asia/Hebron
- Result: Pass (`18 passed, 8 warnings`)

**Known Gaps / Follow-ups**
- Add heavier stress loops (hundreds of children) for cancellation storms.
- Add assertions for propagation behavior on deeper multi-level trees.
