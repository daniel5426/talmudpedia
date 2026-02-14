# Built-in Tools Registry Tests

Last Updated: 2026-02-14

## Scope
Covers built-in template catalog behavior and retrieval validation guardrails in the tools control-plane.

## Test files present
- test_builtin_registry_api.py

## Key scenarios covered
- Global template listing excludes tenant instances.
- Removed built-in instance routes return `404`.
- Generic update/publish/delete reject legacy built-in instance rows (`404`).
- Regular `rag_retrieval` tool create/update reject cross-tenant retrieval pipeline IDs.
- Regular `rag_retrieval` publish validates tenant pipeline scope and creates a `ToolVersion` on success.

## Last run command + result
- Command: `pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_runtime_guardrails.py backend/tests/tool_execution/test_agent_call_tool_execution.py backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py`
- Date/Time: 2026-02-14 20:47 EET
- Result: pass (`16 passed`)

## Known gaps or follow-ups
- Add disabled-flag coverage for template list endpoint (`BUILTIN_TOOLS_V1=0`).
