# Agent Tool Usecases Tests

Last Updated: 2026-03-20

## Scope
Covers end-to-end agent tool-call execution flows for built-in tools through the real agent runtime path (`AgentExecutorService` -> `ReasoningNodeExecutor` -> `ToolNodeExecutor`).

## Test files present
- test_agent_builtin_tool_flow.py
- test_agent_tool_reasoning_stream.py
- test_agent_execution_panel_stream_api.py

## Key scenarios covered
- Web search built-in executes from an agent tool call with scalar/non-JSON args.
- Retrieval built-in executes from an agent tool call using a tenant visual retrieval pipeline and the canonical `rag_pipeline` authored metadata.
- Agent reasoning loop executes `agent_call` tools and consumes compact child-run payloads.
- Agent run completes and persists tool outputs in final run state.
- Debug stream emits synthesized reasoning step events (`active`/`complete`) for each successful tool invocation.
- Production stream includes internal tool lifecycle events (`on_tool_start`/`on_tool_end`) and synthesized reasoning events.
- Debug stream error path emits a terminal `tool.failed` event and marks the synthesized reasoning step as `failed` without inventing a successful completion.
- Parallel-safe multi-tool calls emit reasoning steps per tool call with consistent per-step lifecycle states.
- Multiple agents with web-search/retrieval/mixed tools execute in production mode, with assertions for correct tool invocation and reasoning lifecycle per run.
- API-level execution-panel parity tests (`/agents/{id}/stream?mode=debug`) cover the simplest user path (`gpt-5.2` + web search tool + user message), including:
  - successful call path with emitted tool lifecycle/reasoning events
  - failure path where model emits empty tool args and runtime raises `web_search requires query ...`
- Workload-delegation strict mode compatibility for test fixtures:
  - seed users use privileged actor role to auto-approve provisioning-time policy
  - stream API tests pass explicit `context.requested_scopes=["agents.execute"]` to avoid wildcard scope overflow against approved agent policy

## Last run command + date/time + result
- Command: `pytest -q backend/tests/agent_tool_usecases`
- Date/Time: 2026-03-05 (local)
- Result: pass (`12 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/agent_tool_usecases/test_agent_tool_reasoning_stream.py -k 'tool_error_emits_failed_terminal_tool_event'`
- Date/Time: 2026-03-13 (local run during this change set)
- Result: pass (`1 passed, 11 deselected`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py backend/tests/agent_tool_usecases/test_agent_tool_reasoning_stream.py`
- Date/Time: 2026-03-18 19:08 Asia/Hebron
- Result: pass (`12 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_tool_usecases`
- Date/Time: 2026-03-20 Asia/Hebron
- Result: pass (`11 passed`)

## Manual Real-Provider Validation (No Mocks)
- Date/Time: 2026-02-12 01:18 EET
- Environment: real `DATABASE_URL`, real OpenAI model binding, real Serper key in runtime env.
- Path: `/agents/{id}/stream?mode=debug` with simple agent graph (`agent` node + `web_search` tool).
- Result: `6/6` live runs produced non-empty `query` in `on_tool_start.data.input`; `0/6` had `web_search requires query`; some runs hit `Max tool iterations reached` as expected with `max_tool_iterations=2`.

## Known gaps or follow-ups
- Add automated CI gate for live-provider checks in an isolated environment (currently manual because it requires real secrets/network).
