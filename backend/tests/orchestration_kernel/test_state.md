# Orchestration Kernel Tests

Last Updated: 2026-02-08

Scope:
- Kernel-backed runtime orchestration primitives and run-tree lineage behavior.
- Policy enforcement for allowlist and scope-constrained spawn decisions.

Test files present:
- test_kernel_spawn_and_tree.py

Key scenarios covered:
- `spawn_run` idempotency (same `parent_run_id` + `spawn_key` returns existing child run).
- Run tree query includes spawned descendants under the root run.
- Non-allowlisted target spawn is denied.

Last run command: `pytest -q backend/tests/orchestration_kernel/test_kernel_spawn_and_tree.py`
Last run date: 2026-02-08
Last run result: pass (2 passed)

Known gaps / follow-ups:
- Add tests for `spawn_group`, `join` modes (`all`, `quorum`, `first_success`), and timeout behavior.
- Add tests for subtree cancellation propagation semantics.
