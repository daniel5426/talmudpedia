# Agent Graph Validation Test State

Last Updated: 2026-04-01

## Scope of the feature
Draft-legal agent graph persistence on write paths (`create_agent`, `update_agent`, `update_graph`) with compiler validation moved to explicit analysis/execution flows.

## Test files present
- `test_agent_graph_validation.py`

## Key scenarios covered
- Service rejects missing `graph_definition`.
- Service accepts incomplete draft graphs that are still legal graph documents.
- Service allows non-graph updates when graph is unchanged.
- API persists incomplete drafts on create/update and only rejects illegal graph documents.
- Service validation (`validate_agent`) now runs real compiler + runtime reference checks and returns structured errors/warnings.
- Node intelligence endpoints are covered: `/agents/nodes/catalog` and bulk `/agents/nodes/schema`.
- Runtime config inside `node.data.config` is rejected; top-level `node.config` is the only accepted source of truth.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/agent_graph_validation/test_agent_graph_validation.py`
- Date/Time: 2026-04-01
- Result: pass (`14 passed`)

## Known gaps or follow-ups
- No dedicated frontend unit test yet for new-agent starter graph payload wiring.
