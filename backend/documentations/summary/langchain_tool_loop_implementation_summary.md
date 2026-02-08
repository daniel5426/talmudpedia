# LangChain Tool Loop Implementation Summary

Last Updated: 2026-02-06

## Summary
Implemented LangChain-backed providers for OpenAI and Gemini, added streaming tool-call buffering with an iterative tool loop, and introduced safe parallel tool execution governed by per-tool concurrency metadata. Added tool timeouts with agent-level fallback, plus new agent node config fields to control tool execution.

## Key Changes
- **LangChain adapter**: New `LangChainProviderAdapter` for OpenAI/Gemini, used by `ModelResolver`.
- **Streaming tool-call loop**: `ReasoningNodeExecutor` now buffers `tool_call_chunks`, executes tools, appends `ToolMessage`s in deterministic order, and repeats until completion or max iterations.
- **Safe parallelism**: Optional `parallel_safe` execution mode with batching based on tool `config_schema.execution` metadata.
- **Timeouts**: Per-tool `execution.timeout_s` with agent-node fallback `tool_timeout_s`.
- **Config schema updates**: Added agent node fields `tool_execution_mode`, `max_parallel_tools`, `tool_timeout_s`, `max_tool_iterations`.
- **Dependencies**: Added `langchain-google-genai`.

## Tool Metadata (config_schema["execution"])
- `is_pure` (bool, default false)
- `concurrency_group` (str, default "default")
- `max_concurrency` (int, default 1)
- `timeout_s` (int, optional)

## Tests Added
`backend/tests/agent_tool_loop/`
- Streaming tool-call deltas and follow-up iteration
- Parallel-safe batching and deterministic ordering
- Timeout enforcement
- JSON fallback parsing
- Max iterations enforced

## Tests Run
- `pytest /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_loop`

## Files Added/Updated
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/components/llm/langchain_provider.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/model_resolver.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/core/llm_adapter.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/executors/standard.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/requirements.txt`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_loop/test_tool_loop.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_loop/test_state.md`
- `/Users/danielbenassaya/Code/personal/talmudpedia/code_architect/architecture_tree.md`
