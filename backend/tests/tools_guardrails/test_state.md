# Tools Guardrails Tests

Last Updated: 2026-02-11

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
- Command: `for i in 1 2 3 4 5; do pytest -q backend/tests/agent_execution_events backend/tests/agent_tool_loop backend/tests/builtin_tool_execution backend/tests/tools_guardrails backend/tests/tool_execution backend/tests/agent_api_context backend/tests/builtin_tools_registry || exit 1; done`
- Date/Time: 2026-02-11 22:38 EET
- Result: pass (5 consecutive runs; each run `30 passed, 1 skipped`)

## Known gaps / follow-ups
- Add coverage for workload-principal publish/delete approval gates on `/tools` routes.
