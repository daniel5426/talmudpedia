# Agent Graph Validation Test State

Last Updated: 2026-03-05

## Scope of the feature
Hard-cut graph validation on agent write paths (`create_agent`, `update_agent`, `update_graph`) and API mapping to `422 VALIDATION_ERROR`.

## Test files present
- `test_agent_graph_validation.py`

## Key scenarios covered
- Service rejects missing `graph_definition`.
- Service rejects empty or structurally invalid graphs.
- Service allows non-graph updates when graph is unchanged.
- API returns canonical `VALIDATION_ERROR` payload on create/update validation failures.

## Last run command + date/time + result
- Command: `cd backend && pytest -q tests/agent_graph_validation -q`
- Date/Time: 2026-03-05 (local run during this change set)
- Result: pass (`8 passed`)

## Known gaps or follow-ups
- No dedicated frontend unit test yet for new-agent starter graph payload wiring.
