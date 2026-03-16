# Agent Threads Tests State

Last Updated: 2026-03-16

## Scope of the feature
Thread turn sequencing, repair, and retrieval behavior for persisted agent conversations.

## Test files present
- `test_thread_service.py`

## Key scenarios covered
- Starting a new turn on a thread with an existing `turn_index=0` turn increments to `1` instead of repeating `0`.
- Repair logic resequences historically corrupted duplicate turn indices using stable chronological ordering.
- Thread reads return repaired turns in deterministic order for replay consumers.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py`
- Date/Time: 2026-03-16 15:18 EET
- Result: PASS (`2 passed`)

## Known gaps or follow-ups
- Add route-level coverage for admin and published-app thread detail endpoints after a broader thread-history API pass.
