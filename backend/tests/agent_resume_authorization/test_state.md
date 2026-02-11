# Agent Resume Authorization Tests

Last Updated: 2026-02-11

## Scope
Covers authorization guardrails for `POST /agents/runs/{run_id}/resume` across tenant and user boundaries.

## Test files present
- test_resume_authorization.py

## Key scenarios covered
- Same-tenant non-owner users cannot resume another user’s run.
- Cross-tenant principals cannot resume runs.
- Run owner can resume successfully.

## Last run command + result
- Command: `pytest -q backend/tests/legacy_chat_bootstrap backend/tests/agent_resume_authorization backend/tests/tools_guardrails -vv`
- Date/Time: 2026-02-11 22:17:10 EET
- Result: pass (11 passed)

## Known gaps or follow-ups
- Add workload-principal coverage for runs with `workload_principal_id` set.
