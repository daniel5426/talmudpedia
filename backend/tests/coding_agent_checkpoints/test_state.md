# Coding Agent Checkpoint Tests

Last Updated: 2026-02-16

## Scope of the feature
- Admin coding-agent checkpoint APIs under `/admin/apps/{app_id}/coding-agent/checkpoints*`.
- Checkpoint listing and restore behavior tied to app draft revisions.

## Test files present
- `backend/tests/coding_agent_checkpoints/test_checkpoint_restore.py`

## Key scenarios covered
- Checkpoint listing returns metadata from completed coding-agent runs.
- Checkpoint restore creates a new draft revision and updates app draft pointer.
- Restore with `run_id` updates run linkage fields (`result_revision_id`, `checkpoint_revision_id`).
- Restore returns 404 for missing checkpoint revisions.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_checkpoints`
- Date: 2026-02-16 19:58 UTC
- Result: PASS (2 passed)

## Known gaps or follow-ups
- Add coverage for restoring a checkpoint without `run_id` payload.
- Add negative tests for cross-app checkpoint restore attempts.
