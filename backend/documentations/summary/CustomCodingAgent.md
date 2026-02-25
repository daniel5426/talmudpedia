# Custom Coding Agent

Last Updated: 2026-02-25

## Current State: Hard Cut v2 (OpenCode-Only)

The coding-agent stack is now hard-cut to an OpenCode-first architecture:
- OpenCode is the only execution engine.
- Backend is a thin product adapter for auth, sandbox binding, chat history, and checkpoint promotion.
- Run lifecycle authority is based on OpenCode terminal events (`run.completed`, `run.failed`, `run.cancelled`, `run.paused`).
- Old replay/event-log orchestration has been removed.
- Prompt queueing is frontend-owned (no backend durable queue orchestration).

## v2 API Surface

All coding-agent endpoints now live under:
- `/admin/apps/{app_id}/coding-agent/v2/*`

Implemented routes:
- `POST /coding-agent/v2/prompts`
- `GET /coding-agent/v2/runs/{run_id}`
- `GET /coding-agent/v2/runs/{run_id}/stream`
- `POST /coding-agent/v2/runs/{run_id}/cancel`
- `GET /coding-agent/v2/chat-sessions`
- `GET /coding-agent/v2/chat-sessions/{session_id}`
- `GET /coding-agent/v2/chat-sessions/{session_id}/active-run`
- `GET /coding-agent/v2/checkpoints`
- `POST /coding-agent/v2/checkpoints/{checkpoint_id}/restore`

Removed from public API:
- Non-v2 `/coding-agent/*` endpoints
- Run `resume` endpoint
- Capabilities endpoint
- Stream replay query semantics (`from_seq`, `replay`)

## Prompt Submission Contract (v2)

`POST /coding-agent/v2/prompts` request:
- `input` (required)
- `chat_session_id` (optional)
- `model_id` (optional)
- `client_message_id` (optional)

Response:
- `submission_status = "started"` with `run`

Active-run conflict:
- Returns `409` with detail `{ code: "CODING_AGENT_RUN_ACTIVE", active_run_id, chat_session_id }`

## Backend Runtime Architecture

### 1) Run Monitor (`published_app_coding_run_monitor.py`)

Responsibilities:
- Single monitor task per run in-process
- PostgreSQL advisory lock claim per `run_id` (when on PostgreSQL)
- Consume OpenCode-mapped runtime events
- Fan out mapped events to live SSE subscribers
- Terminalize fail-closed if stream ends without terminal event

Design notes:
- No DB event replay table
- No seq conflict reconciliation layer
- SSE `seq` is connection-local and assigned per stream response

### 2) Prompt Queue Ownership

Queue behavior:
- Frontend owns prompt queue UX/state.
- Backend rejects active-run prompt submissions with `CODING_AGENT_RUN_ACTIVE` instead of persisting queue items.

### 3) Runtime (`published_app_coding_agent_runtime.py`)

Key updates:
- OpenCode-only execution (`execution_engine = "opencode"`)
- Native engine path removed
- Cancellation terminalizes run immediately and releases draft lock
- Checkpoint and restore flow preserved

### 4) Streaming (`published_app_coding_agent_runtime_streaming.py`)

Key updates:
- Assistant deltas are passed through chunk-by-chunk
- No assistant-delta coalescing in backend stream layer
- Terminal path persists assistant message and releases lock
- Tool-call activity is persisted on the run (`output_result.tool_events`) so historical chat reload can reconstruct tool timeline rows (including inputs/results)
- Write-intent telemetry is persisted per run (`has_workspace_writes=true` when write tools are observed)

### 5) Shared Stage Workspace + Idle-Batch Finalization (Current)

Coding-agent runs now use a shared stage workspace per `(published_app_id, initiator_user_id)` scope:
- Shared stage path inside sandbox: `.talmudpedia/stage/shared/workspace`
- All parallel runs in the same scope write into the same stage workspace
- Stage APIs no longer require `run_id` for snapshot/promote operations

Stage API contract changes:
- `prepare_stage_workspace(reset: bool)`:
  - `reset=true` when starting a new batch (no active runs in scope)
  - `reset=false` when joining an active batch (do not reset stage)
- `snapshot_workspace(stage)` and `promote_stage_workspace()` are scope-based and run-agnostic

Batch finalization behavior:
- Finalization is triggered on run terminal transitions by monitor path
- If active runs remain in scope, finalizer exits (no promotion)
- When active run count reaches zero:
  - collect unfinalized completed runs (`batch_finalized_at IS NULL`)
  - if none, exit
  - promote shared stage once (if diff exists) and create one revision/checkpoint
  - owner run = latest completed run by `completed_at` (fallback `created_at`)
  - assign `result_revision_id` and `checkpoint_revision_id` only to owner run
  - mark all processed completed runs finalized (`batch_finalized_at=now()`)
  - set `batch_owner=true` on owner and `false` on others
- If no stage-vs-live diff exists, runs are still finalized (no revision/checkpoint assignment)

New `agent_runs` fields used by this flow:
- `has_workspace_writes BOOLEAN NOT NULL DEFAULT FALSE`
- `batch_finalized_at TIMESTAMPTZ NULL`
- `batch_owner BOOLEAN NOT NULL DEFAULT FALSE`

Locking source-of-truth change:
- Active-run lock semantics are now count-based from `agent_runs` non-terminal statuses
- `published_app_draft_dev_sessions.active_coding_run_id` pointer semantics were removed

## Removed Components

Deleted backend modules:
- `published_app_coding_run_orchestrator.py`
- `published_app_coding_run_orchestrator_queue.py`
- `published_app_coding_agent_engines/native_engine.py`
- `published_app_coding_agent_capabilities.py`

Removed DB model usage:
- `published_app_coding_run_events` (event replay table)
- `agent_runs` runner lease/cancel columns (`runner_owner_id`, `runner_lease_expires_at`, `runner_heartbeat_at`, `is_cancelling`)
- `published_app_draft_dev_sessions.active_coding_run_client_message_id`

## Migration

Added migration:
- `backend/alembic/versions/c2f7a9d8e1b4_coding_agent_v2_hard_cut_drop_orchestration.py`
- `backend/alembic/versions/f9b4e1c2d3a6_shared_stage_batch_finalization.py`

Upgrade behavior:
- Terminalize in-flight coding-agent runs (`queued`/`running` -> `failed`)
- Clear draft run locks
- Drop orchestration artifacts and obsolete columns
- Normalize coding-agent execution engine data/default to `opencode`
- Add batch-finalization columns on `agent_runs`
- Backfill terminal coding-agent runs with `batch_finalized_at=now()` and `batch_owner=false`
- Add active-scope query index on `agent_runs` for count-based lock checks
- Drop obsolete draft-dev lock pointer columns:
  - `active_coding_run_id`
  - `active_coding_run_locked_at`

Downgrade behavior:
- Recreate dropped schema objects/columns (schema-only restore)

## Frontend Contract Changes

Implemented frontend service updates:
- Service endpoints switched to `/coding-agent/v2/*`
- `submitCodingAgentPrompt` handles `started` response and `CODING_AGENT_RUN_ACTIVE` conflict
- Engine resolver and engine selection path removed from send flow
- Stream call no longer accepts replay params
- Stream rendering now handles assistant chunks without frontend coalescing
- Builder lock state now uses:
  - `draft_dev.has_active_coding_runs`
  - `draft_dev.active_coding_run_count`
  instead of `active_coding_run_id` pointer fields
- Post-run refresh avoids per-run revision polling and only triggers preview refresh once no active runs remain in scope
- Expected post-run `CODING_AGENT_RUN_ACTIVE` during parallel flow is treated as non-fatal

## Test Coverage (v2)

Backend v2 test file:
- `backend/tests/coding_agent_api/test_v2_api.py`

Covered scenarios:
- Prompt submission started vs active-run conflict (`CODING_AGENT_RUN_ACTIVE`)
- Per-chunk assistant delta emission at stream layer
- Cancel terminalization
- Legacy route removal (`/coding-agent/runs` returns 404)
- Shared-stage + batch-finalization scenarios:
  - parallel runs share workspace path
  - no promotion while any run remains active
  - single promotion when scope becomes idle
  - owner assignment to latest completed run
  - non-owner completed runs remain without revision/checkpoint IDs
  - processed batches are not re-finalized
- Chat history timeline restore scenarios:
  - persisted tool events are returned in chat-session detail responses
  - frontend reconstructs tool timeline rows from stored run events on reload

Retained engine-level test file:
- `backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`

## Operational Expectations

Monitor/log focus for v2:
- Runs stuck in non-terminal states
- Draft lock not cleared after terminal paths
- Stream disconnect/error rates
- Batch finalizer contention/lock errors per scope
- Unexpected repeated finalization of already-finalized completed runs
