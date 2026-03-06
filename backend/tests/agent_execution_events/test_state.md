# Test State: Agent Execution Events

Last Updated: 2026-03-06

**Scope**
Execution event emission coverage for core nodes in debug streaming runs.

**Test Files**
- `test_node_event_emission.py`
- `test_runtime_error_recovery.py`
- `test_tool_event_metadata.py`

**Scenarios Covered**
- `start`, `human_input`, and `end` emit `node_start` and `node_end` events in debug mode
- Node executor exceptions are converted into recoverable state updates (no node re-raise)
- Run setup failures emit stream error events and persist failed thread turns/output text
- Tool lifecycle stream normalization preserves platform tool action/display metadata for shared chat rendering

**Last Run**
- Command: `pytest -q backend/tests/agent_execution_events/test_runtime_error_recovery.py backend/tests/agent_execution_events/test_tool_event_metadata.py`
- Date: 2026-03-06
- Result: Pass (4 passed)

**Known Gaps / Follow-ups**
- Extend event-emission assertions to classify/if_else once handle-driven routing events are normalized
- Add integration coverage for streaming-time LLM provider failures to verify end-to-end recovery messaging in Architect playground flows
- Add end-to-end streaming assertions that platform metadata survives the full executor-to-SSE path in a real run
