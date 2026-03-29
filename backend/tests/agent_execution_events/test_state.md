# Test State: Agent Execution Events

Last Updated: 2026-03-29

**Scope**
Execution event emission coverage for core nodes in debug streaming runs.

**Test Files**
- `test_node_event_emission.py`
- `test_runtime_error_recovery.py`
- `test_tool_event_metadata.py`

**Scenarios Covered**
- `start`, `human_input`, and `end` emit `node_start` and `node_end` events in debug mode
- Graph Spec 3.0 workflow-contract runs emit inventory snapshot, start seeding, set-state write, node output publication, and End materialization events
- Node executor exceptions are converted into recoverable state updates (no node re-raise)
- Run setup failures emit stream error events and persist failed thread turns/output text
- Tool lifecycle stream normalization preserves platform tool action/display metadata for shared chat rendering
- Failed tool calls now emit terminal `tool.failed` lifecycle events and failed reasoning steps so UI traces do not leave tool calls spinning indefinitely
- Generic runtime `error` events stay non-terminal in the v2 stream contract; only explicit run terminal events should end a client stream
- `UI Blocks` tool events preserve `renderer_kind` on tool start/end and emit `output_kind=ui_blocks_bundle` on completion
- In-flight context telemetry advances from shared tool-event payloads and normalizes to `context.status` SSE events

**Last Run**
- Command: `PYTHONPATH=. pytest -q backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`8 passed, 1 warning`)
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
