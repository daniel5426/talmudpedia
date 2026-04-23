# Agent Threads Tests State

Last Updated: 2026-04-22

## Scope of the feature
Thread turn sequencing, lineage stamping/validation, retrieval behavior, and separation of persisted chat reply text from workflow-facing `final_output`.

## Test files present
- `test_thread_service.py`

## Key scenarios covered
- Starting a new turn on a thread with an existing `turn_index=0` turn increments to `1` instead of repeating `0`.
- Repair logic resequences historically corrupted duplicate turn indices using stable chronological ordering.
- Thread reads return repaired turns in deterministic order for replay consumers.
- Completing a turn preserves structured `final_output` metadata separately from `assistant_output_text`.
- Completing a turn preserves chat-facing `assistant_output_text` even when string `final_output` differs.
- Completing a turn persists canonical `response_blocks` metadata alongside the assistant text projection.
- New root threads self-stamp immutable thread lineage.
- Child threads inherit root/parent lineage from the spawning run.
- Manual continuation of an existing child thread keeps original lineage.
- Reusing a child thread from a different root thread is rejected.
- Thread create/read/list/delete behavior now enforces active-project visibility for project-scoped agent runs and child-thread lineage.
- Org-scoped thread detail reads no longer wrongly exclude project-scoped threads when no explicit project filter is requested.

## Last run command + date/time + result
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/agent_threads/test_thread_service.py`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: PASS
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/agent_threads/test_thread_service.py`
- Date/Time: 2026-04-22 Asia/Hebron
- Result: PASS (`10 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_execution_events/test_chat_response_blocks.py backend/tests/agent_execution_events/test_tool_event_metadata.py backend/tests/agent_threads/test_thread_service.py`
- Date/Time: 2026-04-12 Asia/Hebron
- Result: PASS (`26 passed, 3 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py backend/tests/admin_monitoring/test_admin_monitoring_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-27 Asia/Hebron
- Result: PASS (`17 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py backend/tests/admin_monitoring/test_admin_monitoring_api.py backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py`
- Date/Time: 2026-04-05 Asia/Hebron
- Result: PASS (`23 passed`)

## Known gaps or follow-ups
- Does not yet cover deletion semantics for large multi-level thread trees beyond route-level smoke coverage.
