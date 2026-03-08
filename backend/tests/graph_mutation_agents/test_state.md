# Agent Graph Mutation Tests

Last Updated: 2026-03-07

## Scope
- Safe graph mutation primitives and agent-specific config-path validation.
- Apply-path validation gating before persistence.

## Test files present
- test_agent_graph_mutation_service.py
- test_agent_graph_mutation_routes.py

## Key scenarios covered
- Generic graph operations patch agent-node config without rebuilding edges.
- Unknown agent config fields are rejected by schema-aware path validation.
- Invalid preview validation blocks persistence in `AgentGraphMutationService.apply_patch`.
- Route-level failures return structured HTTP errors with `request_id`, operation name, and mutation phase.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/graph_mutation_agents`
- Date/Time: 2026-03-07
- Result: pass (`3 passed`)

## Known gaps or follow-ups
- Add DB-backed API tests for the new `/agents/{agent_id}/graph/*` routes.
