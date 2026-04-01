# Agent Graph Mutation Tests

Last Updated: 2026-04-01

## Scope
- Safe graph mutation primitives and agent-specific config-path validation.
- Apply-path legality checks with advisory diagnostics after persistence.

## Test files present
- test_agent_graph_mutation_service.py
- test_agent_graph_mutation_routes.py

## Key scenarios covered
- Generic graph operations patch agent-node config without rebuilding edges.
- Unknown agent config fields are rejected by schema-aware path validation.
- Incomplete agent drafts still persist through `AgentGraphMutationService.apply_patch`.
- Route-level failures return structured HTTP errors with `request_id`, operation name, and mutation phase.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py backend/tests/graph_mutation_rag/test_rag_graph_mutation_service.py backend/tests/agent_graph_validation/test_agent_graph_validation.py backend/tests/rag_execution_state/test_stale_executable_state.py`
- Date/Time: 2026-04-01
- Result: pass (`22 passed` across the targeted draft-legal backend suites)

## Known gaps or follow-ups
- Add DB-backed API tests for the new `/agents/{agent_id}/graph/*` routes.
