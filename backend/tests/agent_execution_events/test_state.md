# Test State: Agent Execution Events

Last Updated: 2026-02-05

**Scope**
Execution event emission coverage for core nodes in debug streaming runs.

**Test Files**
- `test_node_event_emission.py`

**Scenarios Covered**
- `start`, `human_input`, and `end` emit `node_start` and `node_end` events in debug mode

**Last Run**
- Command: `pytest -q backend/tests/agent_execution_events`
- Date: 2026-02-05
- Result: Skipped (real_db tests not executed)

**Known Gaps / Follow-ups**
- Extend to classify/if_else once handle-driven routing events are normalized
