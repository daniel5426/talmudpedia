# Tools Guardrails Tests

Last Updated: 2026-03-19

## Scope
Covers tool control-plane guardrails and tenant-isolation behavior.

## Test files present
- test_tools_api_guardrails.py
- test_tool_tenant_scoping.py
- test_tools_runtime_guardrails.py

## Key scenarios covered
- `POST /tools` rejects non-tenant scope requests.
- `POST /tools` rejects direct `PUBLISHED` status creation.
- `POST /tools` rejects direct `ARTIFACT` / `RAG_PIPELINE` creation because those tool types are domain-owned.
- `PUT /tools/{id}` rejects direct publish attempts; `POST /tools/{id}/publish` remains valid.
- Agent-bound exported tools reject registry-side update / publish / delete lifecycle actions, including when ownership is provided from persisted metadata rather than config-derived binding hints.
- Tool resolver and tool executor enforce tenant scoping while allowing global tools.
- Tool resolver supports production-style `require_published` checks.
- Removed built-in instance routes now return `404` (no instance management API surface).

## Last run command + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_bindings/test_agent_tool_bindings.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tool_bindings/test_domain_owned_tool_bindings.py`
- Date/Time: 2026-03-18 19:10 Asia/Hebron
- Result: pass (`14 passed`)

## Known gaps / follow-ups
- Add coverage for workload-principal publish/delete approval gates on `/tools` routes.
