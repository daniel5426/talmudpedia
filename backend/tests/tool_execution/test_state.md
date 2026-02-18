# Tool Execution Tests

Last Updated: 2026-02-18

## Scope
Validate MCP/function/agent-call execution paths in the `ToolNodeExecutor`.

## Test Files
- test_mcp_tool_execution.py
- test_function_tool_execution.py
- test_agent_call_tool_execution.py
- test_reasoning_tool_input_aliases.py
- test_reasoning_tool_call_chunk_buffering.py
- test_coding_agent_tool_path_resolution.py

## Key Scenarios Covered
- MCP JSON-RPC request shape and successful result handling
- MCP error handling on missing result
- Function tool execution via registry allowlist
- Missing function tool name raises a clear error
- Reasoning-node tool input coercion maps file/path aliases (`file_path`, `filePath`, `fromPath`, `toPath`) to canonical tool schema keys.
- Reasoning-node input coercion also maps aliases inside wrapper payloads (`parameters`, `payload`, `args`) for path-bearing tools.
- Reasoning-node input coercion decodes JSON-string `value` payloads and maps embedded path aliases.
- Reasoning-node tool-call chunk buffering merges dict-style partial args (`path` + `content`) into one valid write payload.
- Reasoning-node tool-call finalization prefers provider fallback tool-calls when chunked args cannot be parsed as JSON.
- Function tool execution merges `args` payload with top-level execution context (preserves runtime metadata like `run_id`).
- Function tool execution also decodes JSON-string `args` payloads before merge.
- Coding-agent function tools fail fast with deterministic `TOOL_INPUT_VALIDATION_FAILED` when required fields are missing.
- Coding-agent policy failures are normalized into stable error envelopes (`code/message/field`) instead of raw exception text.
- Coding-agent path resolution supports nested alias shapes (for example nested `relativePath`, `source.path`, `destination.toPath`).
- Coding-agent path resolution also supports JSON-string wrappers (`args`, `input`, `parameters`, `payload`, `value`).
- Coding-agent patch resolution supports nested/wrapped patch aliases (`patch`, `diff`, `unifiedDiff`, JSON-string `value`).
- Required-field validation accepts patch-first tools (`coding_agent_apply_patch`) and range-read tools (`coding_agent_read_file_range`) with nested aliases.
- Targeted-test command payload normalization accepts string commands (for example `"npm run build"`) and rejects invalid command payload types.
- Coding-agent content resolution now supports nested/wrapped aliases (`code`, `text`, `body`, `fileContent`) for write-file calls.
- Required-field validation for coding-agent string fields now resolves wrappers/aliases before reporting missing fields.
- Function-tool execution now flattens wrapper payloads (`args`, `input`, `parameters`, `payload`, `data`, `arguments`, `value`) before validation and dispatch.
- Reasoning tool-call normalization now preserves direct argument fields when no `input/args/parameters` wrapper is present.
- `agent_call` success returns compact sync payload with child output/context
- `agent_call` rejects draft/unpublished targets
- `agent_call` enforces cross-tenant target isolation
- `agent_call` timeout returns failed payload and marks child run failed

## Last Run
- Command: `pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_runtime_guardrails.py backend/tests/tool_execution/test_agent_call_tool_execution.py backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py`
- Date/Time: 2026-02-14 20:47 EET
- Result: pass (`16 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date/Time: 2026-02-16 23:31 UTC
- Result: PASS (`5 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py`
- Date/Time: 2026-02-16 23:57 UTC
- Result: PASS (`9 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py`
- Date/Time: 2026-02-17 00:01 UTC
- Result: PASS (`12 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py`
- Date/Time: 2026-02-17 12:26 UTC
- Result: PASS (`14 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date/Time: 2026-02-17 22:52 UTC
- Result: PASS (`17 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date/Time: 2026-02-17 23:36 UTC
- Result: PASS (`17 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date/Time: 2026-02-17 20:38 UTC
- Result: PASS (`18 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution`
- Date/Time: 2026-02-17 20:38 UTC
- Result: PASS (`25 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date/Time: 2026-02-17 23:31 UTC
- Result: PASS (`21 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_runtime_editing/test_patch_runtime.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date/Time: 2026-02-18 00:25 UTC
- Result: PASS (`26 passed`)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py`
- Date/Time: 2026-02-18 00:45 UTC
- Result: PASS (`11 passed`)

## Known Gaps / Follow-ups
- Add coverage for `agent_call` payload mode variants beyond sync (`spawn`/future orchestration modes).
