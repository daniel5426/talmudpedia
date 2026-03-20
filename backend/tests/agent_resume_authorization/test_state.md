# Agent Resume Authorization Tests

Last Updated: 2026-03-20

## Scope
Covers authorization guardrails for `POST /agents/runs/{run_id}/resume` across tenant and user boundaries.

## Test files present
- test_resume_authorization.py

## Key scenarios covered
- Same-tenant non-owner users cannot resume another user’s run.
- Cross-tenant principals cannot resume runs.
- Run owner can resume successfully.

## Last run command + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_resume_authorization`
- Date/Time: 2026-03-20 Asia/Hebron
- Result: pending

## Known gaps or follow-ups
- Add workload-principal coverage for runs with `workload_principal_id` set.
