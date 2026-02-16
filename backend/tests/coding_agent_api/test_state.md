# Coding Agent API Tests

Last Updated: 2026-02-16

## Scope of the feature
- Admin coding-agent run lifecycle APIs under `/admin/apps/{app_id}/coding-agent/runs*`.
- Request/response contract coverage for create/list/get/stream/resume/cancel.

## Test files present
- `backend/tests/coding_agent_api/test_run_lifecycle.py`

## Key scenarios covered
- Run creation through new coding-agent endpoint with app/revision linkage.
- Stale `base_revision_id` conflict contract (`REVISION_CONFLICT`).
- Stream endpoint returns SSE response type and executes coding-agent stream generator.
- Resume endpoint accepts paused runs and rejects non-paused runs.
- Cancel endpoint transitions active runs to `cancelled`.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api`
- Date: 2026-02-16 19:58 UTC
- Result: PASS (4 passed)

## Known gaps or follow-ups
- Add richer event-envelope assertions with a deterministic stream harness that avoids ASGI transport buffering differences.
- Add authorization-negative coverage for cross-tenant run access.
