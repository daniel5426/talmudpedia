# Agent Tool Loop Tests

Last Updated: 2026-02-12

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

## Last Run
- Command: `pytest -q backend/tests/agent_tool_loop/test_tool_loop.py -vv`
- Date/Time: 2026-02-12 01:19 EET
- Result: pass (`7 passed`)

## Known Gaps / Follow-ups
- Integration coverage with real LangChain providers (OpenAI/Gemini)
- End-to-end execution trace verification
