# Agent Tool Usecases Tests

Last Updated: 2026-02-14

## Scope
Covers end-to-end agent tool-call execution flows for built-in tools through the real agent runtime path (`AgentExecutorService` -> `ReasoningNodeExecutor` -> `ToolNodeExecutor`).

## Test files present
- test_agent_builtin_tool_flow.py
- test_agent_tool_reasoning_stream.py
- test_agent_execution_panel_stream_api.py

## Key scenarios covered
- Web search built-in executes from an agent tool call with scalar/non-JSON args.
- Retrieval built-in executes from an agent tool call using a tenant visual retrieval pipeline.
- Agent reasoning loop executes `agent_call` tools and consumes compact child-run payloads.
- Agent run completes and persists tool outputs in final run state.
- Debug stream emits synthesized reasoning step events (`active`/`complete`) for each successful tool invocation.
- Production stream includes internal tool lifecycle events (`on_tool_start`/`on_tool_end`) and synthesized reasoning events.
- Debug stream error path keeps reasoning state accurate (active without false completion) when a tool fails.
- Parallel-safe multi-tool calls emit reasoning steps per tool call with consistent per-step lifecycle states.
- Multiple agents with web-search/retrieval/mixed tools execute in production mode, with assertions for correct tool invocation and reasoning lifecycle per run.
- API-level execution-panel parity tests (`/agents/{id}/stream?mode=debug`) cover the simplest user path (`gpt-5.2` + web search tool + user message), including:
  - successful call path with emitted tool lifecycle/reasoning events
  - failure path where model emits empty tool args and runtime raises `web_search requires query ...`

## Last run command + date/time + result
- Command: `pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_runtime_guardrails.py backend/tests/tool_execution/test_agent_call_tool_execution.py backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py`
- Date/Time: 2026-02-14 20:47 EET
- Result: pass (`16 passed`)

## Manual Real-Provider Validation (No Mocks)
- Date/Time: 2026-02-12 01:18 EET
- Environment: real `DATABASE_URL`, real OpenAI model binding, real Serper key in runtime env.
- Path: `/agents/{id}/stream?mode=debug` with simple agent graph (`agent` node + `web_search` tool).
- Result: `6/6` live runs produced non-empty `query` in `on_tool_start.data.input`; `0/6` had `web_search requires query`; some runs hit `Max tool iterations reached` as expected with `max_tool_iterations=2`.

## Known gaps or follow-ups
- Add automated CI gate for live-provider checks in an isolated environment (currently manual because it requires real secrets/network).
