# Agent Run Control API Tests

Last Updated: 2026-04-21

## Scope
Covers authorization and cancellation behavior for agent run control endpoints, including `POST /agents/runs/{run_id}/resume` and `POST /agents/runs/{run_id}/cancel`.

## Test files present
- test_resume_authorization.py

## Key scenarios covered
- Same-tenant non-owner users cannot resume another user’s run.
- Cross-tenant principals cannot resume runs.
- Run owner can resume successfully.
- Cancelling a run now cascades through descendant runs in the same run tree.
- Cancelling a run no longer writes thread turns directly from the cancel endpoint, avoiding deadlocks with the active run worker.
- A cancelled run does not restart if the execution worker enters after the cancel was already persisted.
- Cancelling a run also cancels any live in-process run task registered for that run subtree, so abort interrupts active execution instead of only updating DB rows.
- The obsolete foreground-disconnect cancel helper seam is gone; route-level cancel coverage now targets `POST /agents/runs/{run_id}/cancel`.

## Last run command + result
- Command: `SECRET_KEY=test-secret-key PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/agent_resume_authorization/test_resume_authorization.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: PASS (`8 passed`)
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia backend/.venv/bin/python -m pytest -q backend/tests/agent_resume_authorization/test_resume_authorization.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: PASS (`8 passed`). Legacy membership roles are removed; bearer headers now use explicit `agents.execute` scope claims.

## Known gaps or follow-ups
- Add workload-principal coverage for runs with `workload_principal_id` set.
