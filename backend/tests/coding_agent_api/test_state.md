# Coding Agent API Tests

Last Updated: 2026-04-18

## Scope of the feature
- v2 coding-agent admin API under `/admin/apps/{app_id}/coding-agent/v2/*`.
- Session-native OpenCode chat contract (`/chat-sessions/*`) for apps-builder coding chat.
- OpenCode-only execution path.

## Test files present
- `backend/tests/coding_agent_api/test_v2_api.py`
- `backend/tests/coding_agent_api/test_v2_chat_sessions_api.py`
- `backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`

## Key scenarios covered
- Chat session creation/listing uses the session-native v2 contract.
- Message submission uses `POST /coding-agent/v2/chat-sessions/{session_id}/messages` and returns accepted user-message metadata without `run_id`.
- History/detail loading comes from `GET /coding-agent/v2/chat-sessions/{session_id}` and `.../messages`.
- SSE events come from `GET /coding-agent/v2/chat-sessions/{session_id}/events` and always prepend `session.connected`.
- Session SSE waits for remote OpenCode session initialization instead of failing with `409`, so the browser can attach before the first prompt creates the remote session.
- Session SSE emits a one-time assistant/message snapshot plus `session.idle` when the remote OpenCode turn already completed before live SSE attachment, preventing infinite local "Thinking..." state after a late attach.
- Session SSE emits one attach-time catch-up snapshot only; it does not replay progressively more complete assistant snapshots on heartbeat while a live turn is still streaming.
- Chat-session lookups in long-lived request DB sessions repopulate from Postgres, so the SSE route sees `opencode_session_id` updates committed by the submit route instead of waiting forever on a stale ORM object.
- Session detail history reload survives ORM-expired `updated_at` state after remote message fetches, so the browser post-idle hydration path does not crash with `MissingGreenlet`.
- Abort and request reply use the chat-session routes (`.../abort`, `.../permissions/{permission_id}`), with the backend now handling both OpenCode permission requests and general question requests behind the same session chat contract.
- Removed legacy v2 route `/coding-agent/v2/prompts` returns `404`.
- OpenCode-backed coding-agent runs skip model-registry receipt resolution, so provider/model refs like `opencode/gpt-5` do not trip `ModelResolver`.
- First chat turn persists `PublishedAppCodingChatSession.opencode_session_id`.
- Follow-up turns reuse the persisted OpenCode session instead of creating a new one.
- Follow-up turns in the coding-agent engine defer `POST /session/{id}/message` until the official event stream is attached, avoiding missed fast terminal events on reused sessions.
- Follow-up turns do not let stale same-session assistant history satisfy a new run before the new assistant message arrives.
- Stream/cancel/answer paths attach via persisted `opencode_session_id + engine_run_ref` rather than process-local run routing.
- Stream layer emits one `assistant.delta` per upstream chunk (no backend coalescing).
- Coding-agent run payloads and accepted stream events carry canonical `context_window` and `run_usage` contracts.
- Published-app coding-agent streams preserve live `context_window.updated` events when the engine emits canonical context-window updates.
- Tool-event history persistence appends safely under stale-session conditions (external updates are preserved; no JSON overwrite/lost update).
- Stream endpoint is live-only (no replay cursor contract) and session-scoped.
- Terminal transitions for the new session flow are driven by official session events/history reload, not run-stream EOF heuristics.
- OpenCode apply-patch recovery/fail-closed semantics remain covered in engine-level tests.
- Engine-level fake OpenCode clients in this feature folder stay compatible with explicit `sandbox_id` stream attachment used by cross-worker sandbox run streaming.

## Last run command + date/time + result
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/backend && ./.venv-codex-tests/bin/python -m pytest -q tests/coding_agent_api/test_v2_chat_sessions_api.py`
- Date: 2026-04-18 21:52 EEST
- Result: PASS (`9 passed, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/coding_agent_api/test_v2_chat_sessions_api.py -k 'v2_chat_session_events_abort_and_permission_routes'`
- Date: 2026-04-19 Asia/Hebron
- Result: PASS (`1 passed, 8 deselected, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/backend && ./.venv-codex-tests/bin/python -m pytest -q tests/coding_agent_api/test_v2_chat_sessions_api.py`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`7 passed, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/coding_agent_api/test_v2_chat_sessions_api.py`
- Date: 2026-04-17 16:18 EEST
- Result: PASS (`6 passed, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/backend && ./.venv-codex-tests/bin/python -m pytest -q tests/coding_agent_api/test_v2_chat_sessions_api.py`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`8 passed, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/coding_agent_api/test_v2_chat_sessions_api.py`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`7 passed, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/coding_agent_api/test_v2_chat_sessions_api.py backend/tests/coding_agent_api/test_v2_api.py`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`5 passed, 12 skipped, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/coding_agent_api/test_v2_chat_sessions_api.py`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`3 passed, 8 warnings`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/opencode_server_client/test_opencode_server_client.py backend/tests/sandbox_controller/test_opencode_controller_proxy.py backend/tests/coding_agent_api/test_v2_api.py backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- Date: 2026-04-16 18:41 Asia/Hebron
- Result: PASS (63 passed, 8 warnings)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/opencode_server_client/test_opencode_server_client.py backend/tests/sandbox_controller/test_opencode_controller_proxy.py backend/tests/coding_agent_api/test_v2_api.py backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- Date: 2026-04-16 18:25 EEST
- Result: PASS (62 passed, 8 warnings)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py backend/tests/sandbox_controller/test_opencode_controller_proxy.py backend/tests/sandbox_controller/test_dev_shim.py backend/tests/opencode_server_client/test_opencode_server_client.py backend/tests/coding_agent_api/test_v2_api.py backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- Date: 2026-04-16 18:25 EEST
- Result: PASS (71 passed, 8 warnings)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/coding_agent_api/test_v2_api.py backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- Date: 2026-04-16 18:29 Asia/Hebron
- Result: PASS (18 passed, 8 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`8 passed, 7 warnings`)
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-03-15
- Result: PASS (7 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py`
- Date: 2026-02-25
- Result: PASS (7 passed, 6 warnings)
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
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/opencode_server_client/test_opencode_server_client.py -k 'sandbox_mode_stream_can_use_explicit_sandbox_id_without_in_memory_mapping or sprite_start_opencode_run_retries_after_refreshable_disconnect or sprite_inner_opencode_client_skips_host_workspace_bootstrap' tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
- Date: 2026-04-16 05:34 EEST
- Result: PASS (3 passed, 46 deselected, 2 warnings)

## Known gaps / follow-ups
- No migration-integration test in this feature folder yet (alembic head convergence and downgrade schema recreation should be validated in migration-focused tests).
- The legacy `test_v2_api.py` file still contains run-route coverage that should be replaced by session-route coverage as follow-up cleanup.
- Frontend end-to-end chat workspace test suite still needs full contract-level session-chat coverage beyond the focused stream/history tests.
