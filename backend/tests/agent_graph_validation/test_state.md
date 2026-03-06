# Agent Graph Validation Test State

Last Updated: 2026-03-06

## Scope of the feature
Hard-cut graph validation on agent write paths (`create_agent`, `update_agent`, `update_graph`) and API mapping to `422 VALIDATION_ERROR`.

## Test files present
- `test_agent_graph_validation.py`

## Key scenarios covered
- Service rejects missing `graph_definition`.
- Service rejects empty or structurally invalid graphs.
- Service allows non-graph updates when graph is unchanged.
- API returns canonical `VALIDATION_ERROR` payload on create/update validation failures.
- Service validation (`validate_agent`) now runs real compiler + runtime reference checks and returns structured errors/warnings.
- Node intelligence endpoints are covered: `/agents/nodes/catalog` and bulk `/agents/nodes/schema`.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/agent_graph_validation/test_agent_graph_validation.py`
- Date/Time: 2026-03-06 (local run during this change set)
- Result: pass (`13 passed`)

## Known gaps or follow-ups
- No dedicated frontend unit test yet for new-agent starter graph payload wiring.
