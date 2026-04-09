# Test State: Event Normalization and Traces

Last Updated: 2026-04-09

**Scope**
EventEmitter emission behavior and execution-event logging persistence/querying.

**Test Files**
- `test_event_normalization_and_traces.py`

**Scenarios Covered**
- EventEmitter enqueues platform events
- Point-in-time events are persisted with chronological sequence metadata
- Scheduled trace persistence now commits in enqueue order, so detached persisted streams cannot skip earlier child/tool events behind later node-end events
- Repeated events remain visible instead of being collapsed away
- Stored run events can be queried back in execution order

**Last Run**
- Command: `cd backend && pytest -q tests/event_traces/test_event_normalization_and_traces.py`
- Date: 2026-03-07
- Result: Pass (`1 passed, 2 skipped`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/event_traces/test_event_normalization_and_traces.py`
- Date: 2026-04-09 Asia/Hebron
- Result: PASS (`4 passed, 1 warning`)

**Known Gaps / Follow-ups**
- No endpoint-level coverage yet for `/agents/runs/{run_id}/events`
- No concurrency or high-volume trace persistence stress tests
