# Custom Coding Agent

Last Updated: 2026-02-23

## Current State: Hard Cut v2 (OpenCode-Only)

The coding-agent stack is now hard-cut to an OpenCode-first architecture:
- OpenCode is the only execution engine.
- Backend is a thin product adapter for auth, sandbox binding, queue durability, chat history, and checkpoint promotion.
- Run lifecycle authority is based on OpenCode terminal events (`run.completed`, `run.failed`, `run.cancelled`, `run.paused`).
- Old replay/event-log orchestration has been removed.

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
- `GET /coding-agent/v2/chat-sessions/{session_id}/queue`
- `DELETE /coding-agent/v2/chat-sessions/{session_id}/queue/{queue_item_id}`
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

Response union:
- `submission_status = "started"` with `run`
- `submission_status = "queued"` with `active_run_id` and `queue_item`

## Backend Runtime Architecture

### 1) Run Monitor (`published_app_coding_run_monitor.py`)

Responsibilities:
- Single monitor task per run in-process
- PostgreSQL advisory lock claim per `run_id` (when on PostgreSQL)
- Consume OpenCode-mapped runtime events
- Fan out mapped events to live SSE subscribers
- Terminalize fail-closed if stream ends without terminal event
- Dispatch next queued prompt after terminal completion

Design notes:
- No DB event replay table
- No seq conflict reconciliation layer
- SSE `seq` is connection-local and assigned per stream response

### 2) Queue Service (`published_app_coding_queue_service.py`)

Responsibilities:
- Submit prompt (start immediately if idle, queue if active)
- List queue
- Remove queued item
- Dispatch next queued prompt after terminal run

Queue behavior:
- DB durable queue table is retained (`published_app_coding_prompt_queue`)
- Serial dispatch is scoped by chat session

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
- Checkpoint promotion remains on successful terminal runs with write-tool activity

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

Upgrade behavior:
- Terminalize in-flight coding-agent runs (`queued`/`running` -> `failed`)
- Clear draft run locks
- Drop orchestration artifacts and obsolete columns
- Ensure queue dispatch index `(chat_session_id, status, position)`
- Normalize coding-agent execution engine data/default to `opencode`

Downgrade behavior:
- Recreate dropped schema objects/columns (schema-only restore)

## Frontend Contract Changes

Implemented frontend service updates:
- Service endpoints switched to `/coding-agent/v2/*`
- `submitCodingAgentPrompt` now consumes started/queued union response
- Engine resolver and engine selection path removed from send flow
- Stream call no longer accepts replay params
- Stream rendering now handles assistant chunks without frontend coalescing

## Test Coverage (v2)

Backend v2 test file:
- `backend/tests/coding_agent_api/test_v2_api.py`

Covered scenarios:
- Prompt submission started vs queued
- Queue dispatch after terminal run without attached stream
- Per-chunk assistant delta emission at stream layer
- Cancel terminalization and queue unblocking
- Legacy route removal (`/coding-agent/runs` returns 404)

Retained engine-level test file:
- `backend/tests/coding_agent_api/test_opencode_apply_patch_recovery.py`

## Operational Expectations

Monitor/log focus for v2:
- Runs stuck in non-terminal states
- Queue entries not advancing after terminal runs
- Draft lock not cleared after terminal paths
- Stream disconnect/error rates
