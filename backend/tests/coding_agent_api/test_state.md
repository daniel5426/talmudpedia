# Coding Agent API Tests

Last Updated: 2026-03-29

## Scope of the feature
- v2 coding-agent admin API under `/admin/apps/{app_id}/coding-agent/v2/*`.
- OpenCode-only execution path.
- Frontend-owned queue behavior (backend rejects active-run prompt submissions with `CODING_AGENT_RUN_ACTIVE`).

## Test files present
- `backend/tests/coding_agent_api/test_v2_api.py`
- `backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- `backend/tests/coding_agent_api/test_batch_finalizer.py`

## Key scenarios covered
- Prompt submission starts a run when no active run exists for the chat session.
- Prompt submission rejects with `CODING_AGENT_RUN_ACTIVE` when a run is active for the chat session.
- Stream layer emits one `assistant.delta` per upstream chunk (no backend coalescing).
- Coding-agent run payloads and accepted stream events carry `context_status` telemetry for the current run budget snapshot.
- Published-app coding-agent streams emit live `context.status` updates after tool events so the UI can update the context meter mid-run.
- Tool-event history persistence appends safely under stale-session conditions (external updates are preserved; no JSON overwrite/lost update).
- Stream endpoint is live-only (no replay cursor contract) with reconcile-first missing-terminal handling.
- Terminal transitions are persisted and old non-v2 route is removed (`/coding-agent/runs` => 404).
- Removed backend queue routes return `404` (`/coding-agent/v2/chat-sessions/{session_id}/queue*`).
- Cancel endpoint marks run `cancelled`.
- Cancel endpoint now force-closes stream subscribers even when runtime keeps emitting non-terminal events.
- Question-answer endpoint routes user answers to active OpenCode runs (`POST /coding-agent/v2/runs/{run_id}/answer-question`).
- OpenCode apply-patch recovery/fail-closed semantics remain covered in engine-level tests.
- Batch finalizer auto-enqueues coding-run revision builds and records enqueue outcomes per run.
- Batch finalizer marks created revisions as `build_status=failed` when build enqueue fails, without breaking run finalization.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`8 passed, 7 warnings`)
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-03-15
- Result: PASS (7 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_batch_finalizer.py tests/app_versions/test_coding_run_versions.py`
- Date: 2026-03-15
- Result: FAIL during collection (`ModuleNotFoundError: app.services.published_app_coding_batch_finalizer`)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-02-25
- Result: PASS (7 passed, 6 warnings)
- Command: `cd backend && pytest tests/coding_agent_api/test_batch_finalizer.py`
- Date: 2026-03-01
- Result: PASS (3 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py::test_v2_submit_prompt_started_then_run_active tests/coding_agent_api/test_v2_api.py::test_v2_stream_missing_terminal_does_not_force_fail_by_default tests/coding_agent_api/test_v2_api.py::test_v2_cancel_marks_cancelled tests/coding_agent_api/test_v2_api.py::test_v2_cancel_closes_stream_when_runtime_keeps_non_terminal_events`
- Date: 2026-02-25
- Result: PASS (4 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-02-24
- Result: PASS (5 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py::test_v2_cancel_closes_stream_when_runtime_keeps_non_terminal_events tests/coding_agent_api/test_v2_api.py::test_v2_cancel_marks_cancelled_and_dispatches_next tests/sandbox_controller/test_dev_shim.py`
- Date: 2026-02-23
- Result: PASS (9 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py tests/sandbox_controller/test_dev_shim.py`
- Date: 2026-02-23
- Result: PASS (11 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api tests/coding_agent_chat_history_api tests/coding_agent_sandbox_isolation`
- Date: 2026-02-23
- Result: PASS (15 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py::test_v2_answer_question_endpoint tests/sandbox_controller/test_dev_shim.py::test_dev_shim_opencode_question_answer`
- Date: 2026-02-24
- Result: PASS (2 passed, 6 warnings)

## Known gaps / follow-ups
- No migration-integration test in this feature folder yet (alembic head convergence and downgrade schema recreation should be validated in migration-focused tests).
- Frontend end-to-end chat workspace test suite still needs full contract-level v2 sweep beyond the focused stream-speed test.
