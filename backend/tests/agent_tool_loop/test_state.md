# Agent Tool Loop Tests

Last Updated: 2026-02-05

## Scope
Tests for ReasoningNodeExecutor tool-call loop behavior with streaming tool-call deltas, safe parallel execution, timeouts, and fallback parsing.

## Test Files
- test_tool_loop.py

## Key Scenarios Covered
- Streaming tool-call deltas trigger tool execution and follow-up model iteration
- Parallel-safe batching respects tool metadata and preserves deterministic ordering
- Tool timeouts are enforced with per-tool metadata and agent defaults
- JSON tool-call fallback path still works
- Max tool iterations are enforced

## Last Run
- Command: `pytest /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_loop`
- Date/Time: 2026-02-06 00:32:17 EET
- Result: pass

## Known Gaps / Follow-ups
- Integration coverage with real LangChain providers (OpenAI/Gemini)
- End-to-end execution trace verification
