# Agent Tool Loop Tests

Last Updated: 2026-03-25

## Scope
Tests for ReasoningNodeExecutor tool-call loop behavior with streaming tool-call deltas, safe parallel execution, timeouts, and fallback parsing.

## Test Files
- test_tool_loop.py

## Key Scenarios Covered
- Streaming tool-call deltas trigger tool execution and follow-up model iteration
- Streamed tool-call chunks that start with `id` and continue with `index` are stitched into one logical call
- Parallel-safe batching respects tool metadata and preserves deterministic ordering
- Tool timeouts are enforced with per-tool metadata and agent defaults
- JSON tool-call fallback path still works
- Max tool iterations are enforced
- Max tool iterations now emit an explicit terminal run-failure marker for higher-level runtime reconciliation

## Last Run
- Command: `pytest -q backend/tests/agent_tool_loop/test_tool_loop.py -vv`
- Date/Time: 2026-02-12 01:19 EET
- Result: pass (`7 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_tool_loop`
- Date/Time: 2026-03-20 Asia/Hebron
- Result: pass (`7 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_tool_loop/test_tool_loop.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date/Time: 2026-03-25 17:53 EET
- Result: pass (`25 passed, 6 warnings`)

## Known Gaps / Follow-ups
- Integration coverage with real LangChain providers (OpenAI/Gemini)
- End-to-end execution trace verification
