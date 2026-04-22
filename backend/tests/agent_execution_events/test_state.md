# Test State: Agent Execution Events

Last Updated: 2026-04-13

**Scope**
Execution event emission coverage for core nodes in debug streaming runs.

**Test Files**
- `test_chat_response_blocks.py`
- `test_node_event_emission.py`
- `test_runtime_error_recovery.py`
- `test_tool_event_metadata.py`

**Scenarios Covered**
- `start`, `user_approval`, and `end` emit `node_start` and `node_end` events in debug mode
- Graph Spec 3.0 workflow-contract runs emit inventory snapshot, start seeding, set-state write, node output publication, and End materialization events
- Node executor exceptions are converted into recoverable state updates (no node re-raise)
- Run setup failures emit stream error events and persist failed thread turns/output text
- Tool lifecycle stream normalization preserves platform tool action/display metadata for shared chat rendering
- Tool lifecycle stream normalization now preserves explicit `source_node_id` attribution separately from the unique tool-call `span_id`
- Production streaming now preserves hidden `tool.child_run_started` events so the runtime overlay can render spawned child-agent nodes live without adding a visible trace row
- Failed tool calls now emit terminal `tool.failed` lifecycle events and failed reasoning steps so UI traces do not leave tool calls spinning indefinitely
- Generic runtime `error` events stay non-terminal in the v2 stream contract; only explicit run terminal events should end a client stream
- `UI Blocks` tool events preserve `renderer_kind` on tool start/end and emit `output_kind=ui_blocks_bundle` on completion
- Canonical chat-response normalization now promotes `UI Blocks` tool lifecycle events into explicit `ui_blocks` assistant blocks instead of generic tool-call inference
- Context-window estimation is now prompt-snapshot-based and ignores runtime-only scaffolding like nested `context_window`
- `context_window.updated` SSE events preserve the canonical input-window contract in the v2 stream
- Invocation accounting now prefers prompt-estimated input for `context_window` even when exact provider usage exists for `run_usage`
- Dedicated `artifact.draft.updated` client events still survive normalization unchanged
- Executor accounting now reads nested exact usage payloads emitted from shared node-end metadata
- Streamed usage payloads are merged cumulatively instead of letting the last non-null chunk overwrite the total
- Backend canonical chat-response block normalization strips provider tool delta text, preserves tool timelines, and keeps streamed markdown when flatter final output arrives later

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_execution_events/test_chat_response_blocks.py backend/tests/agent_execution_events/test_tool_event_metadata.py backend/tests/agent_threads/test_thread_service.py`
- Date: 2026-04-12 Asia/Hebron
- Result: PASS (`26 passed, 3 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_execution_events/test_chat_response_blocks.py`
- Date: 2026-04-13 Asia/Hebron
- Result: PASS (`5 passed, 1 warning`)
- Command: `PYTHONPATH=. pytest -q tests/agent_execution_events/test_tool_event_metadata.py tests/tool_execution/test_llm_provider_content_blocks.py`
- Date: 2026-03-30 19:49 EEST
- Result: PASS (`19 passed, 2 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_execution/test_agent_call_tool_execution.py backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-04-04 Asia/Hebron
- Result: PASS (`18 passed, 7 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-04-09 Asia/Hebron
- Result: PASS (`13 passed, 3 warnings`)
- Command: `PYTHONPATH=. pytest -q tests/agent_execution_events/test_tool_event_metadata.py tests/tool_execution/test_llm_provider_content_blocks.py tests/context_window/test_token_counter_service.py`
- Date: 2026-03-30 19:49 EEST
- Result: PASS (`24 passed, 2 warnings`)
- Command: `PYTHONPATH=. pytest -q tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-03-30 Asia/Hebron
- Result: PASS (`12 passed, 2 warnings`)
- Command: `PYTHONPATH=. pytest -q tests/agent_execution_events/test_tool_event_metadata.py tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-30 Asia/Hebron
- Result: PASS (`46 passed, 5 warnings`)
- Command: `PYTHONPATH=. pytest -q backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`10 passed, 5 warnings`)
- Command: `PYTHONPATH=. pytest -q backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`9 passed, 1 warning`)
- Command: `pytest -q backend/tests/agent_execution_events/test_runtime_error_recovery.py backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-03-06
- Result: Pass (4 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/agent_execution_events/test_tool_event_metadata.py backend/tests/agent_execution_events/test_runtime_error_recovery.py`
- Date: 2026-03-13 (local run during this change set)
- Result: Pass (`7 passed, 3 warnings`)
- Command: `pytest -q backend/tests/agent_execution_events/test_node_event_emission.py`
- Date: 2026-03-22
- Result: Pass (2 tests)

**Known Gaps / Follow-ups**
- Extend event-emission assertions to classify/if_else once handle-driven routing events are normalized
- Add integration coverage for streaming-time LLM provider failures to verify end-to-end recovery messaging in Architect playground flows
- Add end-to-end streaming assertions that platform metadata survives the full executor-to-SSE path in a real run
