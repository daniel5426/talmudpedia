# Coding Agent Chat History API Tests

Last Updated: 2026-04-21

## Scope of the feature
- Admin coding-agent chat history APIs:
  - `GET /admin/apps/{app_id}/coding-agent/chat-sessions`
  - `GET /admin/apps/{app_id}/coding-agent/chat-sessions/{session_id}`
- Per-user session isolation and ordered message retrieval.

## Test files present
- `backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py`

## Key scenarios covered
- secondary-user fixtures now derive access from canonical `SecurityBootstrapService` owner assignments instead of membership-role fields
- Session listing returns only the current user’s sessions for the target app.
- Session detail returns persisted turns in chronological order.
- Session detail includes persisted per-run tool events (`tool.started` / `tool.completed` / `tool.failed`) from run history.
- Session detail blocks cross-user access and returns `404` for foreign sessions.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/coding_agent_chat_history_api/test_chat_history_endpoints.py`
- Date: 2026-03-15
- Result: PASS (6 passed, 6 warnings)
- Command: `python3 -m pytest backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py -q`
- Date: 2026-02-25
- Result: PASS (3 passed)
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_artifact_versions_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Fail early in `backend/tests/artifact_runtime/test_execution_service.py` on live artifact creation (`invalid input value for enum artifactownertype: "organization"`), so this feature did not get an isolated rerun in the combined pass.

## Known gaps or follow-ups
- Add pagination edge-case tests for large histories (`limit` boundaries, overflow behavior).
