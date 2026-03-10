# Custom Coding Agent

Last Updated: 2026-03-10

## Current State: Hard Cut v2 (OpenCode-Only)

The coding-agent stack is now hard-cut to an OpenCode-first architecture:
- OpenCode is the only execution engine.
- Backend is a thin product adapter for auth, sandbox binding, chat history, and checkpoint promotion.
- Run lifecycle authority converges from OpenCode session state (`session.status`) and assistant finish semantics (not only explicit `run.completed`).
- Old replay/event-log orchestration has been removed.
- Prompt queueing is frontend-owned (no backend durable queue orchestration).

## Latest Applied Update (2026-02-25)

This doc now reflects the current thin-wrapper defaults that were implemented in code:
- Wrapper terminal policy is less aggressive by default (`fail_on_unrecovered_apply_patch` off unless explicitly enabled).
- Tool event passthrough defaults to raw OpenCode semantics, with normalized remap available by env flag.
- Runtime and monitor missing-terminal/inactivity fail-close behavior is opt-in, not default.
- Frontend stream stall handling is non-destructive by default and reconciles backend state before any cancel action.
- v2 stream is live-only (no wrapper reconnect/replay cursor path).
- Non-terminal disconnects are reconcile-first: transport closure triggers status reconciliation against backend run status rather than immediate failed terminalization.
- Permission prompts from OpenCode (`permission.asked`) are mapped into question flow, with stage-sandbox auto-approval by default policy.
- Mid-run assistant text no longer implies terminal completion: `session.idle` does not force `run.completed` in default reconcile-first mode.

## Latest Applied Update (2026-03-01)

The coding-agent/revision pipeline now integrates directly with async app-build readiness for version publish and preview:
- Batch finalization now auto-enqueues revision build jobs for coding-run-created revisions (`origin_kind="coding_run"`), when build automation is enabled.
- Build enqueue failures no longer break finalization; revision rows are preserved and marked `build_status=failed` with enqueue error diagnostics.
- Finalizer result payload now includes per-run build enqueue diagnostics (`build_enqueue_by_run`) in addition to created revision ids.
- Publish wait failures that are build-related can now trigger a best-effort automatic coding-agent fix request:
  - target = latest existing coding-agent chat session for the publishing user/app scope
  - no new session is auto-created
  - diagnostics include either `auto_fix_run_id`, `auto_fix_skipped`, or `auto_fix_error`

## Latest Applied Update (2026-03-07)

Local embedded draft-dev/runtime cleanup was hardened for development setups:
- Draft-dev Vite processes are now tracked with per-sandbox metadata and reclaimed on app boot if a previous backend process exited without clean shutdown.
- Draft-dev shutdown now terminates the full spawned process group, not only the parent process, to avoid lingering `vite`/`tsserver`/`esbuild` children.
- Dev-shim per-sandbox `opencode serve` processes are now tracked with per-sandbox metadata and reclaimed on app boot when stale.
- Dev-shim OpenCode shutdown now terminates the full spawned process group, reducing orphaned local `opencode` helpers after restarts/crashes.

## Latest Applied Update (2026-03-10)

App Builder runtime assumptions were hard-cut again for incremental preview-build architecture:
- Draft runtime still uses one shared Sprite per app.
- Coding-agent now writes directly into the canonical shared workspace; stage/live workspace separation is removed from the main App Builder path.
- Post-run version creation now waits for the next successful preview build and materializes revisions from that exact preview-build snapshot.
- Publish now reuses or materializes the current visible preview build instead of waiting on separate revision build jobs.
- Builder state hydration now heartbeats the active draft session so the frontend can see the newest preview build id immediately after a run ends and reload the static iframe to that build.
- Frontend chat send/reconcile now treats a local draft chat as an alias for the attached server `chat_session_id` once the first run has created it, so follow-up prompts in a brand-new chat do not get stuck behind stale local-session sending state.
- Frontend sending-state reconcile now explicitly skips “no active run” cleanup while a prompt submission request is still in flight, preventing a race where the second prompt in a new chat is cleared before the backend returns its new `run_id`.

## Latest Applied Update (2026-03-09)

Sprite-backed OpenCode transport is now provider-native:
- OpenCode continues to run inside the shared app Sprite as a long-lived service.
- Backend reaches that private service port through the Sprite proxy websocket API and exposes it locally as a short-lived `127.0.0.1:<port>` tunnel.
- The inner OpenCode HTTP client stays on standard localhost HTTP semantics, while the outer Sprite sandbox backend remains the only workspace bootstrap owner.
- This replaced the temporary direct/public-port assumption and improves live event smoothness versus the earlier polling-heavy fallback path.

## OpenCode Protocol Evidence (2026-02-25 Deep-Dive)

Local direct protocol probes against `opencode-ai serve` confirmed:
- Global SSE commonly ends runs with `session.status={type:\"idle\"}` + `session.idle`, without explicit `run.completed`.
- Tool-interleaved runs split into multiple assistant messages:
  - intermediate assistant can complete with `info.finish=\"tool-calls\"` (non-terminal),
  - follow-up assistant later completes with `info.finish=\"stop\"` (terminal-candidate).
- Therefore, wrapper logic must not terminalize on assistant text completion or `finish=\"tool-calls\"`.
- Wrapper completion convergence should treat explicit run terminal events as preferred, but reconcile using OpenCode idle/message-finish semantics when terminal events are missing.

Reference notes:
- `backend/documentations/summary/OpenCodeProtocolInvestigation_2026-02-25.md`

## Pipeline Trace Logging (JSONL, New)

To support postmortems of intermittent multi-run failures (stall/cancel races, missing terminal signals, tool-failure chains), the coding-agent stack now emits structured JSON lines to a dedicated trace sink.

Default output file:
- `/tmp/talmudpedia-coding-agent-pipeline-trace.jsonl`

Primary environment controls:
- `APPS_CODING_AGENT_PIPELINE_TRACE_ENABLED` (`1/0`, defaults to enabled)
- `APPS_CODING_AGENT_PIPELINE_TRACE_FILE` (absolute file path override)

Backward compatibility aliases:
- `APPS_CODING_AGENT_DEBUG_TRACE_ENABLED`
- `APPS_CODING_AGENT_DEBUG_TRACE_FILE`

Pipelines now traced:
- `api_v2` (prompt submit / stream open-close / cancel / question answer)
- `runtime` (run creation, sandbox init, cancellation lifecycle, answer-question lifecycle)
- `runtime_stream` (engine event mapping, terminalization, forced failure reasons, stream close)
- `monitor` (subscriber/emit lifecycle, synthetic terminalization, timeout enforcement)
- `opencode_engine` (mapped tool/run events, apply_patch recovery policy outcomes)
- `opencode_client` (start/cancel/answer requests + results, official stream closure stats)

Event model:
- One JSON object per line, with `ts`, `pipeline`, `event`, `pid`, and run correlation fields (`run_id`, `app_id`, optional session/tool identifiers).
- Logging is best-effort and non-blocking with failure swallow semantics (trace writes never break run execution).

## Thin-Wrapper Behavior Controls (Current Defaults)

To stay closer to OpenCode-native semantics, aggressive wrapper policies are now opt-in:
- `APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH` defaults to disabled (`0`)
  - when enabled, wrapper can still fail-close a run that terminal-completes after unrecovered `apply_patch` failures
- `APPS_CODING_AGENT_OPENCODE_TOOL_EVENT_MODE` defaults to `raw`
  - `raw`: preserves OpenCode tool event shape (`tool.completed` may include diagnostics when output contains `error`)
  - `normalized`: maps `tool.completed` with `output.error` into `tool.failed` for legacy UI behavior
- `APPS_CODING_AGENT_MONITOR_FORCE_TERMINAL_ON_INACTIVITY` defaults to disabled (`0`)
  - monitor no longer force-fails long silent windows by default
- `APPS_CODING_AGENT_MONITOR_FORCE_TERMINAL_ON_STREAM_END_WITHOUT_TERMINAL` defaults to disabled (`0`)
  - monitor prefers stream reopen/reconciliation over immediate fail-close on non-terminal EOF

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

## Chat Session Detail Pagination (v2, Breaking Contract)

Endpoint:
- `GET /coding-agent/v2/chat-sessions/{session_id}`

Query params:
- `before_message_id` (optional UUID cursor)
- `limit` (optional, default `10`, min `1`, max `100`)

Response shape:
- `session`
- `messages` (chronological within the returned page: oldest -> newest)
- `run_events` (only for runs referenced by messages in the returned page)
- `paging`:
  - `has_more`
  - `next_before_message_id`

Semantics:
- No cursor: returns latest page (newest activity slice).
- With cursor: returns strictly older messages than cursor row.
- Cursor chaining for older fetches uses the current page oldest message id.
- Reverse paging query order is `created_at DESC, id DESC`, then page is reversed before response.
- Backend default page size is fixed to `10`.

## Prompt Submission Contract (v2)

`POST /coding-agent/v2/prompts` request:
- `input` (required)
- `chat_session_id` (optional)
- `model_id` (optional, OpenCode model string such as `opencode/big-pickle`)
- `client_message_id` (optional)

Response:
- `submission_status = "started"` with `run`

Active-run conflict:
- Returns `409` with detail `{ code: "CODING_AGENT_RUN_ACTIVE", active_run_id, chat_session_id }`

Model selection behavior (current):
- Coding-agent model selection is decoupled from tenant/client `model_registry`.
- Backend no longer resolves coding runs through logical model registry/provider bindings.
- Auto model resolves to `opencode/big-pickle`.
- Selected model IDs are passed as OpenCode model strings and persisted in run context.

## Backend Runtime Architecture

### 1) Run Monitor (`published_app_coding_run_monitor.py`)

Responsibilities:
- Single monitor task per run in-process
- PostgreSQL advisory lock claim per `run_id` (when on PostgreSQL)
- Consume OpenCode-mapped runtime events
- Fan out mapped events to live SSE subscribers
- Reopen/reconcile on non-terminal stream EOF by default; fail-close policies are env-gated

Design notes:
- No DB event replay table
- No seq conflict reconciliation layer
- SSE `seq` is run-global monotonic and assigned in monitor emit path
- No cursor-based replay path in v2 stream endpoint

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
- Missing-terminal stream endings are non-fatal by default (runtime defers terminal authority to persisted run status and monitor reconciliation)
- Tool-call activity is persisted on the run (`output_result.tool_events`) so historical chat reload can reconstruct tool timeline rows (including inputs/results)
- Write-intent telemetry is persisted per run (`has_workspace_writes=true` when write tools are observed)

### 5) Canonical Workspace + Preview-Build Finalization (Current)

Coding-agent runs now use the same canonical workspace that the preview builder watches:
- `opencode_workspace_path` resolves directly to the app workspace
- there is no stage workspace preparation/promotion step in the main App Builder path

Post-run finalization behavior:
- terminal completed runs are marked as waiting for the next successful preview build
- when a successful preview build is visible, the backend materializes a revision from that exact source/dist snapshot
- overlapping completed runs may resolve to the same revision if they are both waiting when the same successful build lands
  - mark all processed completed runs finalized (`batch_finalized_at=now()`)
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
- Coding model selector uses an internal OpenCode catalog (no `modelsService.listModels(...)` dependency)
- Selector includes OpenCode free-model options and paid OpenCode coding models
- Auto selection submits `opencode/big-pickle`
- Engine resolver and engine selection path removed from send flow
- Stream call is live-only and does not use reconnect/replay cursor semantics
- Stream rendering now handles assistant chunks without frontend coalescing
- Frontend stall watchdog is non-destructive by default:
  - no implicit cancel on stall/max-duration unless `NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_AUTO_CANCEL_RECOVERY_ENABLED=1`
  - missing-terminal stream endings reconcile with backend status first and avoid forced cancel in default mode
- Generic assistant fallback text is suppressed after non-terminal disconnect or tool-only progress to avoid misleading "mid-run stopped" UX
- Builder lock state now uses:
  - `draft_dev.has_active_coding_runs`
  - `draft_dev.active_coding_run_count`
  instead of `active_coding_run_id` pointer fields
- Post-run refresh avoids per-run revision polling and only triggers preview refresh once no active runs remain in scope
- Expected post-run `CODING_AGENT_RUN_ACTIVE` during parallel flow is treated as non-fatal
- Chat history detail uses reverse pagination from newest activity with backend `paging` object (`limit=10` default)
- Scroll-up pagination loads older pages via `before_message_id` and prepends while preserving viewport anchor

### Frontend Session Container Model (UI Runtime)

The chat UI now uses per-session runtime containers keyed by `sessionId` plus `__draft__`:
- Timeline and page-cached history per session
- Prompt queue and pending question per session
- Sending/stopping/thinking state per session
- Run attachment refs and stream refs per session

Behavior guarantees:
- Switching tabs renders immediately from container state (no forced cold refetch for initialized tabs)
- Streaming continues in background for inactive tabs, but writes are scoped to owning session container only
- Stale stream attachment writes are blocked per session
- Draft-to-real migration moves `__draft__` runtime state to the returned `chat_session_id`

### Draft Tab + Sending State UX Fix

Resolved UI regression where "sending..." state caused draft/new tabs to disappear or reappear incorrectly:
- Draft tab persistence is now independent from active tab selection during send/stream
- Activating the draft tab no longer resets the draft state
- Switching tabs while a message is sending no longer leaks stream/tool activity into other tabs
- New-session tab remains visible throughout send lifecycle (including while `isSending=true`)

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
