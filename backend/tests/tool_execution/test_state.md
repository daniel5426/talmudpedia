# Tool Execution Tests

Last Updated: 2026-02-14

## Scope
Validate MCP/function/agent-call execution paths in the `ToolNodeExecutor`.

## Test Files
- test_mcp_tool_execution.py
- test_function_tool_execution.py
- test_agent_call_tool_execution.py

## Key Scenarios Covered
- MCP JSON-RPC request shape and successful result handling
- MCP error handling on missing result
- Function tool execution via registry allowlist
- Missing function tool name raises a clear error
- `agent_call` success returns compact sync payload with child output/context
- `agent_call` rejects draft/unpublished targets
- `agent_call` enforces cross-tenant target isolation
- `agent_call` timeout returns failed payload and marks child run failed

## Last Run
- Command: `pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_runtime_guardrails.py backend/tests/tool_execution/test_agent_call_tool_execution.py backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py`
- Date/Time: 2026-02-14 20:47 EET
- Result: pass (`16 passed`)

## Known Gaps / Follow-ups
- Add coverage for `agent_call` payload mode variants beyond sync (`spawn`/future orchestration modes).
