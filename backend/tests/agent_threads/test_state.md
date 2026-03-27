# Agent Threads Tests State

Last Updated: 2026-03-27

## Scope of the feature
Thread turn sequencing, repair, and retrieval behavior for persisted agent conversations.

## Test files present
- `test_thread_service.py`

## Key scenarios covered
- Starting a new turn on a thread with an existing `turn_index=0` turn increments to `1` instead of repeating `0`.
- Repair logic resequences historically corrupted duplicate turn indices using stable chronological ordering.
- Thread reads return repaired turns in deterministic order for replay consumers.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py backend/tests/admin_monitoring/test_admin_monitoring_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-27 Asia/Hebron
- Result: PASS (`17 passed`)

## Known gaps or follow-ups
- Does not yet cover embedded-runtime thread detail serialization.
