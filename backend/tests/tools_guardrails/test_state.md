# Tools Guardrails Tests

Last Updated: 2026-02-14

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
- Removed built-in instance routes now return `404` (no instance management API surface).

## Last run command + result
- Command: `pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_runtime_guardrails.py backend/tests/tool_execution/test_agent_call_tool_execution.py backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py`
- Date/Time: 2026-02-14 20:47 EET
- Result: pass (`16 passed`)

## Known gaps / follow-ups
- Add coverage for workload-principal publish/delete approval gates on `/tools` routes.
