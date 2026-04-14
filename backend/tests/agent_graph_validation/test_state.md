# Agent Graph Validation Test State

Last Updated: 2026-04-14

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
- Route tests now use explicit scoped bearer tokens because `/agents` read/write endpoints enforce `principal.scopes` directly.
- Create-validation assertions now match the shared `VALIDATION_ERROR` envelope with nested `details.errors`.
- Node-schema success coverage now reflects the stricter contract where unknown node types are validation errors.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/agent_graph_validation/test_agent_graph_validation.py`
- Date/Time: 2026-04-01
- Result: pass (`14 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py backend/tests/graph_mutation_agents/test_agent_graph_mutation_routes.py backend/tests/agent_graph_validation/test_agent_graph_validation.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py -k 'agents or graph or validate or publish or create_shell'`
- Date/Time: 2026-04-14 Asia/Hebron
- Result: pass (`47 passed, 55 deselected, 8 warnings`)

## Known gaps or follow-ups
- No dedicated frontend unit test yet for new-agent starter graph payload wiring.
