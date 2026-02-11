# Built-in Tools Registry Tests

Last Updated: 2026-02-10

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
- Command: `pytest -q backend/tests/builtin_tools_registry backend/tests/builtin_tool_execution backend/tests/tools_guardrails`
- Date/Time: 2026-02-10 22:44 EET
- Result: pass (18 passed)

## Known gaps or follow-ups
- Add negative coverage for feature flag disabled mode (`BUILTIN_TOOLS_V1=0`).
