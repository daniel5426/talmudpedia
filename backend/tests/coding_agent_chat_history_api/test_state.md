# Coding Agent Chat History API Tests

Last Updated: 2026-02-25

## Scope of the feature
- Admin coding-agent chat history APIs:
  - `GET /admin/apps/{app_id}/coding-agent/chat-sessions`
  - `GET /admin/apps/{app_id}/coding-agent/chat-sessions/{session_id}`
- Per-user session isolation and ordered message retrieval.

## Test files present
- `backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py`

## Key scenarios covered
- Session listing returns only the current user’s sessions for the target app.
- Session detail returns persisted turns in chronological order.
- Session detail includes persisted per-run tool events (`tool.started` / `tool.completed` / `tool.failed`) from run history.
- Session detail blocks cross-user access and returns `404` for foreign sessions.

## Last run command + date/time + result
- Command: `python3 -m pytest backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py -q`
- Date: 2026-02-25
- Result: PASS (3 passed)

## Known gaps or follow-ups
- Add pagination edge-case tests for large histories (`limit` boundaries, overflow behavior).
