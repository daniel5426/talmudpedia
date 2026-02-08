# Tool Execution Tests

Last Updated: 2026-02-06

## Scope
Validate MCP and function tool execution paths in the ToolNodeExecutor.

## Test Files
- test_mcp_tool_execution.py
- test_function_tool_execution.py

## Key Scenarios Covered
- MCP JSON-RPC request shape and successful result handling
- MCP error handling on missing result
- Function tool execution via registry allowlist
- Missing function tool name raises a clear error

## Last Run
- Command: Not run (new tests)
- Date: 2026-02-06
- Result: Not run

## Known Gaps / Follow-ups
- Add coverage for timeout behavior with a slow MCP server.
