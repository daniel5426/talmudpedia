# Coding Agent API Tests

Last Updated: 2026-02-23

## Scope of the feature
- v2 coding-agent admin API under `/admin/apps/{app_id}/coding-agent/v2/*`.
- OpenCode-only execution path.
- Durable queue + monitor-driven dispatch/finalization behavior.

## Test files present
- `backend/tests/coding_agent_api/test_v2_api.py`
- `backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`

## Key scenarios covered
- Prompt submission starts a run when no active run exists for the chat session.
- Prompt submission returns queued response when a run is active for the chat session.
- Queue dispatch starts next run after terminal completion without any client stream attached.
- Stream layer emits one `assistant.delta` per upstream chunk (no backend coalescing).
- Terminal transitions are persisted and old non-v2 route is removed (`/coding-agent/runs` => 404).
- Cancel endpoint marks run `cancelled` and unblocks queued dispatch.
- OpenCode apply-patch recovery/fail-closed semantics remain covered in engine-level tests.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api tests/coding_agent_chat_history_api tests/coding_agent_checkpoints tests/coding_agent_sandbox_isolation`
- Date: 2026-02-23
- Result: PASS (15 passed, 6 warnings)

## Known gaps / follow-ups
- No migration-integration test in this feature folder yet (alembic head convergence and downgrade schema recreation should be validated in migration-focused tests).
- Frontend end-to-end chat workspace test suite still needs full contract-level v2 sweep beyond the focused stream-speed test.
