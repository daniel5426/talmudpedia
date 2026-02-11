# Tools Guardrails Tests

Last Updated: 2026-02-10

## Scope
Covers tool control-plane guardrails and tenant-isolation behavior.

## Test files present
- test_tools_api_guardrails.py
- test_tool_tenant_scoping.py
- test_tools_runtime_guardrails.py

## Key scenarios covered
- `POST /tools` rejects non-tenant scope requests.
- `POST /tools` rejects direct `PUBLISHED` status creation.
- `PUT /tools/{id}` rejects direct publish attempts; `POST /tools/{id}/publish` remains valid.
- Tool resolver and tool executor enforce tenant scoping while allowing global tools.
- Tool resolver supports production-style `require_published` checks.
- Built-in instances are tenant-isolated in `/tools/builtins/instances` routes.

## Last run command + result
- Command: `pytest -q backend/tests/builtin_tools_registry backend/tests/builtin_tool_execution backend/tests/tools_guardrails`
- Date/Time: 2026-02-10 22:44 EET
- Result: pass (18 passed)

## Known gaps / follow-ups
- Add coverage for workload-principal publish/delete approval gates on `/tools` routes.
