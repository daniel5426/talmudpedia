# Agent Tool Usecases Tests

Last Updated: 2026-02-11

## Scope
Covers end-to-end agent tool-call execution flows for built-in tools through the real agent runtime path (`AgentExecutorService` -> `ReasoningNodeExecutor` -> `ToolNodeExecutor`).

## Test files present
- test_agent_builtin_tool_flow.py

## Key scenarios covered
- Web search built-in executes from an agent tool call with scalar/non-JSON args.
- Retrieval built-in executes from an agent tool call using a tenant visual retrieval pipeline.
- Agent run completes and persists tool outputs in final run state.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/agent_tool_usecases backend/tests/agent_tool_loop backend/tests/builtin_tool_execution`
- Date/Time: 2026-02-11 16:07 EET
- Result: pass (15 passed)

## Known gaps or follow-ups
- Add real external provider integration checks for web_search credentials resolution in an isolated environment.
