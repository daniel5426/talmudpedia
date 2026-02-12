# Built-in Tools Registry Tests

Last Updated: 2026-02-11

## Scope
Covers built-in template and tenant instance control-plane behavior in `/tools/builtins/*` routes.

## Test files present
- test_builtin_registry_api.py

## Key scenarios covered
- Global template listing excludes tenant instances.
- Tenant instance creation from a global template.
- Built-in instance schema/type immutability through generic update endpoint.
- Built-in retrieval instance publish flow with tenant pipeline validation.
- Cross-tenant retrieval pipeline IDs are rejected.

## Last run command + result
- Command: `for i in 1 2 3 4 5; do pytest -q backend/tests/agent_execution_events backend/tests/agent_tool_loop backend/tests/builtin_tool_execution backend/tests/tools_guardrails backend/tests/tool_execution backend/tests/agent_api_context backend/tests/builtin_tools_registry || exit 1; done`
- Date/Time: 2026-02-11 22:38 EET
- Result: pass (5 consecutive runs; each run `30 passed, 1 skipped`)

## Known gaps or follow-ups
- Add negative coverage for feature flag disabled mode (`BUILTIN_TOOLS_V1=0`).
